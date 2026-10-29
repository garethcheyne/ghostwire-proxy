import {
  context,
  diag,
  metrics,
  propagation,
  ROOT_CONTEXT,
  SpanStatusCode,
  trace,
  type Attributes,
  type Context,
  type Counter,
  type Histogram,
  type Link,
  type SpanKind,
} from "@opentelemetry/api"
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks"
import {
  CompositePropagator,
  ExportResultCode,
  getRPCMetadata,
  RPCType,
  suppressTracing,
  W3CBaggagePropagator,
  W3CTraceContextPropagator,
  type ExportResult,
} from "@opentelemetry/core"
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-proto"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto"
import { registerInstrumentations } from "@opentelemetry/instrumentation"
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http"
import { PgInstrumentation } from "@opentelemetry/instrumentation-pg"
import { UndiciInstrumentation } from "@opentelemetry/instrumentation-undici"
import { resourceFromAttributes } from "@opentelemetry/resources"
import {
  AggregationTemporality,
  InstrumentType,
  MeterProvider,
  PeriodicExportingMetricReader,
  type PushMetricExporter,
  type ResourceMetrics,
} from "@opentelemetry/sdk-metrics"
import {
  BatchSpanProcessor,
  ParentBasedSampler,
  SamplingDecision,
  TraceIdRatioBasedSampler,
  TracerProvider,
  type ReadableSpan,
  type Sampler,
  type SamplingResult,
  type Span,
  type SpanExporter,
  type SpanProcessor,
} from "@opentelemetry/sdk-trace"
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions"
import { createRequire } from "node:module"
import { hostname } from "node:os"

import type { GetGhostwireConfig, GhostwireConfig } from "./types"

/**
 * System monitoring for a Next.js app: traces and metrics over OTLP/HTTP to the Ghostwire Analytics
 * site in Settings (ghostwire-suite/docs/analytics-reporting.md). Call it once from
 * instrumentation.ts, in the Node.js runtime only:
 *
 *   // src/instrumentation.ts
 *   export async function register() {
 *     if (process.env.NEXT_RUNTIME !== "nodejs") return
 *     const { registerGhostwireTelemetry } = await import("@/components/analytics/telemetry")
 *     const { getAnalyticsConfig } = await import("@/lib/analytics-config")
 *     registerGhostwireTelemetry(getAnalyticsConfig, { serviceName: "web", serviceNamespace: "ghostwire-load" })
 *   }
 *
 * Settings are read at run time, not at start: while reporting is off (or there's no ingest key)
 * nothing is sampled or sent, and a new URL or key applies within a refresh. Reporting only
 * observes: nothing here throws into the app, and exports run in the background with short
 * timeouts, so a slow or dead Analytics never slows a request.
 */

export interface GhostwireTelemetryOptions {
  /** This process within the app, e.g. "web", "runner". */
  serviceName: string
  /** The app, e.g. "ghostwire-load". */
  serviceNamespace: string
  /** Defaults to process.env.APP_VERSION (the VERSION file, read at build time). */
  serviceVersion?: string
  /** Defaults to DEPLOYMENT_ENVIRONMENT, then NODE_ENV. */
  environment?: string
  /** Request paths that are neither traced nor counted (prefix match). Defaults to IGNORED_PATHS. */
  ignorePaths?: string[]
  /** How often metrics are sent, in ms. Default 30 s. */
  metricIntervalMs?: number
}

export interface GhostwireTelemetry {
  /** Sends what's queued now (e.g. before a short-lived script exits). Never rejects. */
  forceFlush(): Promise<void>
  /** Flushes and stops. Never rejects. */
  shutdown(): Promise<void>
}

/** Health checks, the relay and static files: frequent, uninteresting, and the relay would echo. */
export const IGNORED_PATHS = ["/api/heartbeat", "/internal/otlp/", "/gw/", "/_next/static/", "/_next/image", "/favicon"]

const EXPORT_TIMEOUT_MS = 10_000
const CONFIG_REFRESH_MS = 5000 // how stale the sampler's view may get; the app's own getter caches for about a minute
const WARN_EVERY_MS = 10 * 60_000
const INSTANCE = Symbol.for("ghostwire.telemetry")

type Target = { url: string; key: string }

/** Where to send, or null while monitoring is off. Monitoring needs the ingest key, page views don't. */
function targetOf(config: GhostwireConfig | null): Target | null {
  const url = config?.url?.trim().replace(/\/+$/, "")
  const key = config?.ingestKey?.trim()
  return url && key ? { url, key } : null
}

/** The latest settings. Exports await a fresh read; the sampler is synchronous, so it reads the last one. */
class LiveConfig {
  private value: GhostwireConfig | null = null
  private readAt = 0
  private pending: Promise<GhostwireConfig | null> | null = null

  constructor(private readonly getConfig: GetGhostwireConfig) {}

  /** Reads through the app's getter, without tracing the read (it may query the database). */
  refresh(): Promise<GhostwireConfig | null> {
    // new Promise turns a getter that throws instead of rejecting into "off", not an error in the app.
    this.pending ??= new Promise<GhostwireConfig | null>((resolve) =>
      resolve(context.with(suppressTracing(ROOT_CONTEXT), () => this.getConfig())),
    )
      .catch(() => null)
      .then((value) => {
        this.value = value
        this.readAt = Date.now()
        this.pending = null
        return value
      })
    return this.pending
  }

  peek(): GhostwireConfig | null {
    if (Date.now() - this.readAt > CONFIG_REFRESH_MS) void this.refresh()
    return this.value
  }
}

/** Export failures say so in the log now and then, never per batch and never as an exception. */
function makeWarner() {
  let last = 0
  return (what: string, error?: unknown) => {
    if (Date.now() - last < WARN_EVERY_MS) return
    last = Date.now()
    const reason = error instanceof Error ? error.message : error ? String(error) : "no answer"
    console.warn(`[ghostwire] Couldn't send ${what} to Ghostwire Analytics (${reason}). Retrying quietly.`)
  }
}

/** One inner OTLP exporter per URL and key, rebuilt when Settings change; the old one is closed in the background. */
class ExporterSlot<T extends { shutdown(): Promise<void>; forceFlush(): Promise<void> }> {
  private current: { id: string; exporter: T } | null = null

  constructor(private readonly build: (target: Target) => T) {}

  get(target: Target): T {
    const id = `${target.url}\n${target.key}`
    if (this.current?.id !== id) {
      const old = this.current?.exporter
      this.current = { id, exporter: this.build(target) }
      old?.shutdown().catch(() => {})
    }
    return this.current.exporter
  }

  async flush(): Promise<void> {
    await this.current?.exporter.forceFlush().catch(() => {})
  }

  async close(): Promise<void> {
    const old = this.current?.exporter
    this.current = null
    await old?.shutdown().catch(() => {})
  }
}

function headers(target: Target) {
  return { Authorization: `Bearer ${target.key}` }
}

/** Sends spans to <url>/v1/traces with the key from Settings, or drops them while monitoring is off. */
class SwitchableSpanExporter implements SpanExporter {
  private readonly slot = new ExporterSlot(
    (target) =>
      new OTLPTraceExporter({ url: `${target.url}/v1/traces`, headers: headers(target), timeoutMillis: EXPORT_TIMEOUT_MS }),
  )
  private readonly warn = makeWarner()

  constructor(private readonly live: LiveConfig) {}

  export(spans: ReadableSpan[], done: (result: ExportResult) => void): void {
    void this.live
      .refresh()
      .then((config) => {
        const target = targetOf(config)
        if (!target) return done({ code: ExportResultCode.SUCCESS }) // off: dropped on purpose
        this.slot.get(target).export(spans, (result) => {
          if (result.code !== ExportResultCode.SUCCESS) this.warn("traces", result.error)
          done(result)
        })
      })
      .catch((error: unknown) => {
        this.warn("traces", error)
        done({ code: ExportResultCode.FAILED })
      })
  }

  forceFlush(): Promise<void> {
    return this.slot.flush()
  }

  shutdown(): Promise<void> {
    return this.slot.close()
  }
}

/**
 * Delta for counters and histograms: each export says what happened in that interval, which is
 * what Analytics rolls up per minute, and a restart never looks like a counter going backwards.
 */
function deltaTemporality(type: InstrumentType): AggregationTemporality {
  return type === InstrumentType.UP_DOWN_COUNTER || type === InstrumentType.OBSERVABLE_UP_DOWN_COUNTER
    ? AggregationTemporality.CUMULATIVE
    : AggregationTemporality.DELTA
}

/** Sends metrics to <url>/v1/metrics with the key from Settings, or drops them while monitoring is off. */
class SwitchableMetricExporter implements PushMetricExporter {
  private readonly slot = new ExporterSlot(
    (target) =>
      new OTLPMetricExporter({
        url: `${target.url}/v1/metrics`,
        headers: headers(target),
        timeoutMillis: EXPORT_TIMEOUT_MS,
      }),
  )
  private readonly warn = makeWarner()

  constructor(private readonly live: LiveConfig) {}

  export(data: ResourceMetrics, done: (result: ExportResult) => void): void {
    void this.live
      .refresh()
      .then((config) => {
        const target = targetOf(config)
        if (!target) return done({ code: ExportResultCode.SUCCESS })
        this.slot.get(target).export(data, (result) => {
          if (result.code !== ExportResultCode.SUCCESS) this.warn("metrics", result.error)
          done(result)
        })
      })
      .catch((error: unknown) => {
        this.warn("metrics", error)
        done({ code: ExportResultCode.FAILED })
      })
  }

  selectAggregationTemporality(type: InstrumentType): AggregationTemporality {
    return deltaTemporality(type)
  }

  forceFlush(): Promise<void> {
    return this.slot.flush()
  }

  shutdown(): Promise<void> {
    return this.slot.close()
  }
}

const NOT_SAMPLED: SamplingResult = { decision: SamplingDecision.NOT_RECORD }
const RECORD_ONLY: SamplingResult = { decision: SamplingDecision.RECORD }

/**
 * Applies the trace sampling % from Settings as it is now: follows the parent's decision when there
 * is one, otherwise keeps that share of traces by trace ID. Records nothing while monitoring is off.
 * Metrics aren't sampled; they count every request. Spans outside the sample are still recorded
 * (never exported) so NextRouteProcessor can give every request's metric its route.
 */
class GhostwireSampler implements Sampler {
  private readonly byRatio = new Map<number, Sampler>()

  constructor(
    private readonly live: LiveConfig,
    private readonly ignorePaths: string[],
  ) {}

  shouldSample(ctx: Context, traceId: string, name: string, kind: SpanKind, attributes: Attributes, links: Link[]) {
    const config = this.live.peek()
    if (!targetOf(config)) return NOT_SAMPLED
    if (this.ignored(attributes)) return NOT_SAMPLED // Next.js's own request spans for ignored paths
    const sample = Number(config?.traceSample)
    const ratio = Number.isFinite(sample) ? Math.min(100, Math.max(0, sample)) / 100 : 1
    let sampler = this.byRatio.get(ratio)
    if (!sampler) {
      sampler = new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(ratio) })
      this.byRatio.set(ratio, sampler)
    }
    const result = sampler.shouldSample(ctx, traceId, name, kind, attributes, links)
    return result.decision === SamplingDecision.NOT_RECORD ? RECORD_ONLY : result
  }

  private ignored(attributes: Attributes) {
    const path = attributes["url.path"] ?? attributes["http.target"]
    return typeof path === "string" && this.ignorePaths.some((prefix) => path.startsWith(prefix))
  }

  toString() {
    return "GhostwireSampler"
  }
}

/**
 * Gives http.server.request.duration its route. The HTTP instrumentation can't know Next.js's routes;
 * Next.js's own spans carry `next.route` (the pattern, e.g. /sites/[id]) as soon as the route is
 * resolved, so the first one hands it to the request's RPC metadata, which the instrumentation reads
 * when the response closes (it also renames the server span to "GET /sites/[id]").
 */
class NextRouteProcessor implements SpanProcessor {
  onStart(span: Span, parentContext: Context): void {
    try {
      const route = span.attributes["next.route"]
      if (typeof route !== "string" || span.instrumentationScope.name !== "next.js") return
      const rpc = getRPCMetadata(parentContext)
      if (rpc?.type === RPCType.HTTP && rpc.route === undefined) rpc.route = route
    } catch {}
  }

  onEnd(): void {}

  async forceFlush(): Promise<void> {}

  async shutdown(): Promise<void> {}
}

/**
 * Starts tracing and metrics for this process. Safe to call more than once (dev reloads): the first
 * call wins and later calls return the same handle. Never throws; if setup fails, the app runs
 * without monitoring and says so once in the log.
 */
export function registerGhostwireTelemetry(
  getConfig: GetGhostwireConfig,
  options: GhostwireTelemetryOptions,
): GhostwireTelemetry {
  const store = globalThis as unknown as Record<symbol, GhostwireTelemetry | undefined>
  const existing = store[INSTANCE]
  if (existing) return existing

  const noop: GhostwireTelemetry = { forceFlush: async () => {}, shutdown: async () => {} }
  try {
    const live = new LiveConfig(getConfig)
    void live.refresh()

    const environment = options.environment ?? process.env.DEPLOYMENT_ENVIRONMENT ?? process.env.NODE_ENV ?? "production"
    const version = options.serviceVersion ?? process.env.APP_VERSION
    const resource = resourceFromAttributes({
      [ATTR_SERVICE_NAME]: options.serviceName,
      "service.namespace": options.serviceNamespace,
      ...(version ? { [ATTR_SERVICE_VERSION]: version } : {}),
      "deployment.environment": environment, // the spec's name
      "deployment.environment.name": environment, // the current semantic-conventions name
      "host.name": hostname(),
      "process.pid": process.pid,
    })

    const ignorePaths = options.ignorePaths ?? IGNORED_PATHS
    const tracerProvider = new TracerProvider({
      resource,
      sampler: new GhostwireSampler(live, ignorePaths),
      spanProcessors: [
        new NextRouteProcessor(),
        new BatchSpanProcessor({
          exporter: new SwitchableSpanExporter(live),
          scheduledDelayMillis: 5000,
          exportTimeoutMillis: EXPORT_TIMEOUT_MS + 5000,
          maxQueueSize: 2048,
        }),
      ],
    })
    const metricInterval = Math.max(1000, options.metricIntervalMs ?? 30_000)
    const meterProvider = new MeterProvider({
      resource,
      readers: [
        new PeriodicExportingMetricReader({
          exporter: new SwitchableMetricExporter(live),
          exportIntervalMillis: metricInterval,
          exportTimeoutMillis: Math.min(EXPORT_TIMEOUT_MS + 5000, metricInterval), // the reader insists
        }),
      ],
    })

    context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable())
    propagation.setGlobalPropagator(
      new CompositePropagator({ propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()] }),
    )
    trace.setGlobalTracerProvider(tracerProvider)
    metrics.setGlobalMeterProvider(meterProvider)

    const ignoredRequest = (url: string | undefined) => !!url && ignorePaths.some((prefix) => url.startsWith(prefix))
    registerInstrumentations({
      tracerProvider,
      meterProvider,
      instrumentations: [
        // The OTLP exports run with tracing suppressed, so they never trace themselves.
        new HttpInstrumentation({ ignoreIncomingRequestHook: (request) => ignoredRequest(request.url) }),
        new UndiciInstrumentation(),
        new PgInstrumentation(),
      ],
    })
    // Next.js loads node:http before register() runs, and the instrumentation patches a module on
    // the next require() of it (Turbopack loads built-ins with import(), which it can't see). Ask for
    // them once more so the server's requests are traced and measured.
    try {
      const load = createRequire(`${process.cwd()}/`)
      load("node:http")
      load("node:https")
    } catch {}

    const handle: GhostwireTelemetry = {
      forceFlush: () =>
        Promise.all([tracerProvider.forceFlush(), meterProvider.forceFlush()]).then(
          () => {},
          () => {},
        ),
      shutdown: () =>
        Promise.all([tracerProvider.shutdown(), meterProvider.shutdown()]).then(
          () => {},
          () => {},
        ),
    }
    store[INSTANCE] = handle
    return handle
  } catch (error) {
    diag.error("ghostwire telemetry setup failed", error)
    console.warn(
      `[ghostwire] Monitoring didn't start (${error instanceof Error ? error.message : String(error)}). The app runs without it.`,
    )
    store[INSTANCE] = noop
    return noop
  }
}

const JOB_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
let workerInstruments: { duration: Histogram; runs: Counter; heartbeat: Counter } | null = null

/** Created on first use from the global meter, so they work before registration (and bind after it). */
function workerMetrics() {
  if (!workerInstruments) {
    const meter = metrics.getMeter("ghostwire")
    workerInstruments = {
      duration: meter.createHistogram("ghostwire.job.duration", {
        unit: "s",
        description: "How long each job run took",
        advice: { explicitBucketBoundaries: JOB_BUCKETS },
      }),
      runs: meter.createCounter("ghostwire.job.runs", { unit: "{run}", description: "Job runs, by outcome" }),
      heartbeat: meter.createCounter("ghostwire.heartbeat", { unit: "{beat}", description: "Worker loop heartbeats" }),
    }
  }
  return workerInstruments
}

/**
 * One run of a background job (e.g. a Load test run): a span named after it, plus
 * ghostwire.job.duration (seconds) and ghostwire.job.runs, with attributes `job` and `outcome`
 * (ok or error). The job's result or error passes through unchanged, the same as the Python
 * workers' job().
 */
export async function runGhostwireJob<T>(name: string, run: () => Promise<T> | T, attributes: Attributes = {}): Promise<T> {
  const started = performance.now()
  let outcome = "ok"
  return trace.getTracer("ghostwire").startActiveSpan(`job ${name}`, { attributes: { job: name, ...attributes } }, async (span) => {
    try {
      const result = await run()
      span.setStatus({ code: SpanStatusCode.OK })
      return result
    } catch (error) {
      outcome = "error"
      try {
        span.recordException(error instanceof Error ? error : String(error))
        span.setStatus({ code: SpanStatusCode.ERROR, message: error instanceof Error ? error.message : String(error) })
      } catch {}
      throw error
    } finally {
      try {
        const labels = { job: name, outcome }
        workerMetrics().duration.record((performance.now() - started) / 1000, labels)
        workerMetrics().runs.add(1, labels)
        span.end()
      } catch {}
    }
  })
}

/** Counts one loop of a worker (ghostwire.heartbeat). Call it every loop, busy or idle: Analytics shows a service whose heartbeat stops as down. */
export function ghostwireHeartbeat(attributes?: Attributes): void {
  try {
    workerMetrics().heartbeat.add(1, attributes)
  } catch {}
}
