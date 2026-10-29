import {
  context,
  diag,
  isSpanContextValid,
  metrics,
  propagation,
  ROOT_CONTEXT,
  SpanKind,
  SpanStatusCode,
  trace,
  type Attributes,
  type Context,
  type Counter,
  type Histogram,
  type Link,
} from "@opentelemetry/api"
import { createRequire } from "node:module"
import { hostname } from "node:os"

import type { ExportResult } from "@opentelemetry/core"
import type { Instrumentation } from "@opentelemetry/instrumentation"
import type { AggregationTemporality, InstrumentType, PushMetricExporter, ResourceMetrics } from "@opentelemetry/sdk-metrics"
import type { ReadableSpan, Sampler, SamplingResult, Span, SpanExporter, SpanProcessor } from "@opentelemetry/sdk-trace"

import type { GetGhostwireConfig, GhostwireConfig } from "./types"

/**
 * System monitoring for a Next.js app or a Node worker: traces and metrics over OTLP/HTTP to the
 * Ghostwire Analytics site in Settings (ghostwire-suite/docs/analytics-reporting.md). Call it once
 * from instrumentation.ts, in the Node.js runtime only:
 *
 *   // src/instrumentation.ts
 *   export async function register() {
 *     if (process.env.NEXT_RUNTIME !== "nodejs") return
 *     const { registerGhostwireTelemetry } = await import("@/components/analytics/telemetry")
 *     const { getAnalyticsConfig } = await import("@/lib/analytics-config")
 *     await registerGhostwireTelemetry(getAnalyticsConfig, { serviceName: "web", serviceNamespace: "ghostwire-load" })
 *   }
 *
 * Settings are read at run time, not at start: while reporting is off (or there's no ingest key)
 * nothing is sampled or sent, and a new URL or key applies within a refresh. Reporting only
 * observes: nothing here throws into the app, and exports run in the background with short
 * timeouts, so a slow or dead Analytics never slows a request.
 *
 * Only @opentelemetry/api is imported up front. The SDK loads inside registerGhostwireTelemetry, so
 * a package that fails to load (a missing file in a standalone build, a version mismatch) leaves the
 * app running without monitoring instead of failing every request. Erasable TypeScript only, so a
 * plain Node worker can run this file with Node's type stripping.
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
  /**
   * Request paths that are counted (http.server.request.duration, with the route) but not traced
   * (prefix match), e.g. a poll endpoint that answers every few seconds. Default none.
   */
  untracedPaths?: string[]
  /** How often metrics are sent, in ms. Default 30 s. */
  metricIntervalMs?: number
  /**
   * Instrument Node's http module (incoming requests and the request duration metric; outgoing
   * http.request). Default true. Turn it off in a proxy-like worker whose traffic isn't worth a span
   * per request.
   */
  http?: boolean
  /** More instrumentations on the same providers, switch and sampling, e.g. new PrismaInstrumentation(). */
  instrumentations?: Instrumentation[]
}

export interface GhostwireTelemetry {
  /** False when the SDK couldn't load and the app runs without monitoring. */
  readonly active: boolean
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
const MAX_TRACKED_REQUESTS = 10_000

type HttpModule = typeof import("@opentelemetry/instrumentation-http")

/**
 * instrumentation-http's ESM build loads forwarded-parse with createRequire(import.meta.url), which
 * neither a bundle nor Next.js's standalone file tracing can follow. A literal require() makes
 * Turbopack bundle the CommonJS build instead, whose plain require("forwarded-parse") it can. Plain
 * Node (an ES module, so no require) loads the CommonJS build from node_modules.
 */
/* eslint @typescript-eslint/no-require-imports: "off" -- the require() below is on purpose (see above). A rule
   setting rather than a disable comment, so apps that don't enable the rule get no unused-directive warning. */
function loadHttpInstrumentation(): HttpModule {
  return typeof require === "function"
    ? require("@opentelemetry/instrumentation-http")
    : createRequire(import.meta.url)("@opentelemetry/instrumentation-http")
}

/**
 * Asks for Node's http and https again, so the HTTP instrumentation patches them now: it patches a
 * module the next time it's asked for, and Next.js loaded both before register() ran. Through
 * process.getBuiltinModule, which bundlers leave alone. (webpack compiles a createRequire() with a
 * run-time argument to nothing, so the patch used to wait for the first export, and by then a server
 * whose request handler something else had wrapped, as Sentry does, was never measured.)
 */
function loadHttpModulesAgain() {
  try {
    const getBuiltin = (process as { getBuiltinModule?: (id: string) => unknown }).getBuiltinModule
    if (typeof getBuiltin === "function") {
      getBuiltin("node:http")
      getBuiltin("node:https")
    } else {
      const load = createRequire(`${process.cwd()}/`)
      load("node:http")
      load("node:https")
    }
  } catch {}
}

async function loadSdk(withHttp: boolean) {
  const [core, asyncHooks, traceExporter, metricExporter, instrumentation, undici, pg, resources, sdkMetrics, sdkTrace] =
    await Promise.all([
      import("@opentelemetry/core"),
      import("@opentelemetry/context-async-hooks"),
      import("@opentelemetry/exporter-trace-otlp-proto"),
      import("@opentelemetry/exporter-metrics-otlp-proto"),
      import("@opentelemetry/instrumentation"),
      import("@opentelemetry/instrumentation-undici"),
      import("@opentelemetry/instrumentation-pg"),
      import("@opentelemetry/resources"),
      import("@opentelemetry/sdk-metrics"),
      import("@opentelemetry/sdk-trace"),
    ])
  const http = withHttp ? loadHttpInstrumentation() : null
  return { core, asyncHooks, traceExporter, metricExporter, instrumentation, undici, pg, resources, sdkMetrics, sdkTrace, http }
}

type Sdk = Awaited<ReturnType<typeof loadSdk>>
type Target = { url: string; key: string }

/** Where to send, or null while monitoring is off. Monitoring needs the ingest key, page views don't. */
function targetOf(config: GhostwireConfig | null): Target | null {
  const url = config?.url?.trim().replace(/\/+$/, "")
  const key = config?.ingestKey?.trim()
  return url && key ? { url, key } : null
}

/** A 404 is the app's relay saying monitoring is off: the batch is dropped, which is what off means. */
function isOff(error: unknown) {
  return (error as { code?: unknown } | undefined)?.code === 404
}

/** The latest settings. Exports await a fresh read; the sampler is synchronous, so it reads the last one. */
class LiveConfig {
  private value: GhostwireConfig | null = null
  private readAt = 0
  private pending: Promise<GhostwireConfig | null> | null = null
  private readonly getConfig: GetGhostwireConfig
  private readonly sdk: Sdk

  constructor(getConfig: GetGhostwireConfig, sdk: Sdk) {
    this.getConfig = getConfig
    this.sdk = sdk
  }

  /** Reads through the app's getter, without tracing the read (it may query the database). */
  refresh(): Promise<GhostwireConfig | null> {
    // new Promise turns a getter that throws instead of rejecting into "off", not an error in the app.
    this.pending ??= new Promise<GhostwireConfig | null>((resolve) =>
      resolve(context.with(this.sdk.core.suppressTracing(ROOT_CONTEXT), () => this.getConfig())),
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

type Inner = { shutdown(): Promise<void>; forceFlush(): Promise<void> }

/** One inner OTLP exporter per URL and key, rebuilt when Settings change; the old one is closed in the background. */
class ExporterSlot<T extends Inner> {
  private current: { id: string; exporter: T } | null = null
  private readonly build: (target: Target) => T

  constructor(build: (target: Target) => T) {
    this.build = build
  }

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

type Exportable<D> = Inner & { export(data: D, done: (result: ExportResult) => void): void }

/**
 * Sends to <url>/v1/<signal> with the key from Settings, or drops the batch while monitoring is off.
 * Shared by the span and metric exporters below.
 */
class Switchable<D> {
  private readonly slot: ExporterSlot<Exportable<D>>
  private readonly warn = makeWarner()
  private readonly live: LiveConfig
  private readonly sdk: Sdk
  private readonly what: string

  constructor(live: LiveConfig, sdk: Sdk, what: string, build: (target: Target) => Exportable<D>) {
    this.live = live
    this.sdk = sdk
    this.what = what
    this.slot = new ExporterSlot(build)
  }

  export(data: D, done: (result: ExportResult) => void): void {
    const { SUCCESS, FAILED } = this.sdk.core.ExportResultCode
    void this.live
      .refresh()
      .then((config) => {
        const target = targetOf(config)
        if (!target) return done({ code: SUCCESS }) // off: dropped on purpose
        this.slot.get(target).export(data, (result) => {
          if (result.code === SUCCESS || isOff(result.error)) return done({ code: SUCCESS })
          this.warn(this.what, result.error)
          done(result)
        })
      })
      .catch((error: unknown) => {
        this.warn(this.what, error)
        done({ code: FAILED })
      })
  }

  forceFlush(): Promise<void> {
    return this.slot.flush()
  }

  shutdown(): Promise<void> {
    return this.slot.close()
  }
}

class SwitchableSpanExporter implements SpanExporter {
  private readonly inner: Switchable<ReadableSpan[]>

  constructor(live: LiveConfig, sdk: Sdk) {
    this.inner = new Switchable(
      live,
      sdk,
      "traces",
      (target) =>
        new sdk.traceExporter.OTLPTraceExporter({
          url: `${target.url}/v1/traces`,
          headers: { Authorization: `Bearer ${target.key}` },
          timeoutMillis: EXPORT_TIMEOUT_MS,
        }),
    )
  }

  export(spans: ReadableSpan[], done: (result: ExportResult) => void): void {
    this.inner.export(spans, done)
  }

  forceFlush(): Promise<void> {
    return this.inner.forceFlush()
  }

  shutdown(): Promise<void> {
    return this.inner.shutdown()
  }
}

class SwitchableMetricExporter implements PushMetricExporter {
  private readonly inner: Switchable<ResourceMetrics>
  private readonly sdk: Sdk

  constructor(live: LiveConfig, sdk: Sdk) {
    this.sdk = sdk
    this.inner = new Switchable(
      live,
      sdk,
      "metrics",
      (target) =>
        new sdk.metricExporter.OTLPMetricExporter({
          url: `${target.url}/v1/metrics`,
          headers: { Authorization: `Bearer ${target.key}` },
          timeoutMillis: EXPORT_TIMEOUT_MS,
        }),
    )
  }

  export(data: ResourceMetrics, done: (result: ExportResult) => void): void {
    this.inner.export(data, done)
  }

  /**
   * Delta for counters and histograms: each export says what happened in that interval, which is
   * what Analytics rolls up per minute, and a restart never looks like a counter going backwards.
   */
  selectAggregationTemporality(type: InstrumentType): AggregationTemporality {
    const { InstrumentType: types, AggregationTemporality: temporality } = this.sdk.sdkMetrics
    return type === types.UP_DOWN_COUNTER || type === types.OBSERVABLE_UP_DOWN_COUNTER
      ? temporality.CUMULATIVE
      : temporality.DELTA
  }

  forceFlush(): Promise<void> {
    return this.inner.forceFlush()
  }

  shutdown(): Promise<void> {
    return this.inner.shutdown()
  }
}

/**
 * Applies the trace sampling % from Settings as it is now: follows the parent's decision when there
 * is one, otherwise keeps that share of traces by trace ID. Records nothing while monitoring is off.
 * Metrics aren't sampled; they count every request. Spans outside the sample are still recorded
 * (never exported) so NextRouteProcessor can give every request's metric its route.
 *
 * Counted but not traced: requests to untracedPaths, and a CLIENT span with no parent (a query or
 * call made outside any request or job, such as a poll every few seconds), which would otherwise be
 * a one-span trace each time.
 */
class GhostwireSampler implements Sampler {
  private readonly byRatio = new Map<number, Sampler>()
  private readonly live: LiveConfig
  private readonly sdk: Sdk
  private readonly ignorePaths: string[]
  private readonly untracedPaths: string[]
  private readonly notSampled: SamplingResult
  private readonly recordOnly: SamplingResult

  constructor(live: LiveConfig, sdk: Sdk, ignorePaths: string[], untracedPaths: string[]) {
    this.live = live
    this.sdk = sdk
    this.ignorePaths = ignorePaths
    this.untracedPaths = untracedPaths
    this.notSampled = { decision: sdk.sdkTrace.SamplingDecision.NOT_RECORD }
    this.recordOnly = { decision: sdk.sdkTrace.SamplingDecision.RECORD }
  }

  shouldSample(ctx: Context, traceId: string, name: string, kind: SpanKind, attributes: Attributes, links: Link[]) {
    const config = this.live.peek()
    if (!targetOf(config)) return this.notSampled
    if (matches(attributes, this.ignorePaths)) return this.notSampled // Next.js's own request spans for ignored paths
    const parent = trace.getSpanContext(ctx)
    if (!parent || !isSpanContextValid(parent)) {
      if (kind === SpanKind.CLIENT || matches(attributes, this.untracedPaths)) return this.recordOnly
    }
    const sample = Number(config?.traceSample)
    const ratio = Number.isFinite(sample) ? Math.min(100, Math.max(0, sample)) / 100 : 1
    let sampler = this.byRatio.get(ratio)
    if (!sampler) {
      const { ParentBasedSampler, TraceIdRatioBasedSampler } = this.sdk.sdkTrace
      sampler = new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(ratio) })
      this.byRatio.set(ratio, sampler)
    }
    const result = sampler.shouldSample(ctx, traceId, name, kind, attributes, links)
    return result.decision === this.sdk.sdkTrace.SamplingDecision.NOT_RECORD ? this.recordOnly : result
  }

  toString() {
    return "GhostwireSampler"
  }
}

/** Whether a request span's path starts with one of the prefixes. */
function matches(attributes: Attributes, prefixes: string[]) {
  if (prefixes.length === 0) return false
  const path = attributes["url.path"] ?? attributes["http.target"]
  return typeof path === "string" && prefixes.some((prefix) => path.startsWith(prefix))
}

/** Attributes that can hold a URL's query string; url.query is the query alone, so it's dropped. */
const URL_ATTRIBUTES = ["url.full", "url.original", "http.url", "http.target"]
const QUERY_ATTRIBUTES = ["url.query"]

function withoutQuery(value: string) {
  return value.split("?", 1)[0].split("#", 1)[0]
}

/**
 * Keeps query strings, which can carry tokens (a connector's ?token=, a signed link), out of every
 * span: the HTTP, undici and Next.js spans record them (url.query, and inside url.full, http.target,
 * http.url and the name of a request Next.js couldn't route). Cleaned when a span starts and again
 * when it ends, before the exporter sees it.
 */
class StripQueryProcessor implements SpanProcessor {
  onStart(span: Span): void {
    stripQuery(span)
  }

  onEnd(span: ReadableSpan): void {
    stripQuery(span)
  }

  async forceFlush(): Promise<void> {}

  async shutdown(): Promise<void> {}
}

function stripQuery(span: ReadableSpan) {
  try {
    // An ended span's fields are plain properties, and this is the object the exporter gets next.
    const attributes = span.attributes as Record<string, unknown>
    for (const name of QUERY_ATTRIBUTES) delete attributes[name]
    for (const name of URL_ATTRIBUTES) {
      const value = attributes[name]
      if (typeof value === "string" && /[?#]/.test(value)) attributes[name] = withoutQuery(value)
    }
    if (span.name.includes("?")) (span as { name: string }).name = withoutQuery(span.name)
  } catch {}
}

type RpcMetadata = { type: unknown; route?: string; span: { spanContext(): { spanId: string } } }

/**
 * Gives http.server.request.duration its route. The HTTP instrumentation can't know Next.js's routes;
 * Next.js's own spans carry `next.route` (the pattern, e.g. /sites/[id]). The HTTP instrumentation
 * puts its RPC metadata in the request's context, and reads `route` from it when the response
 * closes (it also renames the server span to "GET /sites/[id]"). Next.js's inner spans don't always
 * run in that context, so the metadata is remembered by trace ID from the first span that sees it,
 * filled from any later next.js span in the trace, and forgotten when the HTTP span ends.
 */
class NextRouteProcessor implements SpanProcessor {
  private readonly requests = new Map<string, RpcMetadata>()
  private readonly sdk: Sdk

  constructor(sdk: Sdk) {
    this.sdk = sdk
  }

  onStart(span: Span, parentContext: Context): void {
    try {
      const traceId = span.spanContext().traceId
      const rpc = this.sdk.core.getRPCMetadata(parentContext) as RpcMetadata | undefined
      if (rpc?.type === this.sdk.core.RPCType.HTTP && !this.requests.has(traceId)) {
        if (this.requests.size >= MAX_TRACKED_REQUESTS) this.requests.delete(this.requests.keys().next().value as string)
        this.requests.set(traceId, rpc)
      }
      const route = span.attributes["next.route"]
      if (typeof route !== "string" || span.instrumentationScope.name !== "next.js") return
      const request = this.requests.get(traceId)
      if (request && request.route === undefined) request.route = route
    } catch {}
  }

  onEnd(span: ReadableSpan): void {
    try {
      const traceId = span.spanContext().traceId
      const request = this.requests.get(traceId)
      if (request?.span.spanContext().spanId === span.spanContext().spanId) this.requests.delete(traceId)
    } catch {}
  }

  async forceFlush(): Promise<void> {}

  async shutdown(): Promise<void> {
    this.requests.clear()
  }
}

const INACTIVE: GhostwireTelemetry = { active: false, forceFlush: async () => {}, shutdown: async () => {} }

/**
 * Starts tracing and metrics for this process. Safe to call more than once (dev reloads): the first
 * call wins and later calls get the same handle. Never rejects; if the SDK can't load or start, the
 * app runs without monitoring, says so once in the log, and the handle's `active` is false.
 */
export function registerGhostwireTelemetry(
  getConfig: GetGhostwireConfig,
  options: GhostwireTelemetryOptions,
): Promise<GhostwireTelemetry> {
  const store = globalThis as unknown as Record<symbol, Promise<GhostwireTelemetry> | undefined>
  store[INSTANCE] ??= start(getConfig, options).catch((error: unknown) => {
    try {
      diag.error("ghostwire telemetry setup failed", error)
      console.warn(
        `[ghostwire] Monitoring didn't start (${error instanceof Error ? error.message : String(error)}). The app runs without it.`,
      )
    } catch {}
    return INACTIVE
  })
  return store[INSTANCE]
}

async function start(getConfig: GetGhostwireConfig, options: GhostwireTelemetryOptions): Promise<GhostwireTelemetry> {
  const sdk = await loadSdk(options.http !== false)
  const live = new LiveConfig(getConfig, sdk)
  void live.refresh()

  const environment = options.environment ?? process.env.DEPLOYMENT_ENVIRONMENT ?? process.env.NODE_ENV ?? "production"
  const version = options.serviceVersion ?? process.env.APP_VERSION
  const resource = sdk.resources.resourceFromAttributes({
    "service.name": options.serviceName,
    "service.namespace": options.serviceNamespace,
    ...(version ? { "service.version": version } : {}),
    "deployment.environment": environment, // the spec's name
    "deployment.environment.name": environment, // the current semantic-conventions name
    "host.name": hostname(),
    "process.pid": process.pid,
  })

  const ignorePaths = options.ignorePaths ?? IGNORED_PATHS
  const tracerProvider = new sdk.sdkTrace.TracerProvider({
    resource,
    sampler: new GhostwireSampler(live, sdk, ignorePaths, options.untracedPaths ?? []),
    spanProcessors: [
      new StripQueryProcessor(), // first, so nothing after it sees a query string
      new NextRouteProcessor(sdk),
      new sdk.sdkTrace.BatchSpanProcessor({
        exporter: new SwitchableSpanExporter(live, sdk),
        scheduledDelayMillis: 5000,
        exportTimeoutMillis: EXPORT_TIMEOUT_MS + 5000,
        maxQueueSize: 2048,
      }),
    ],
  })
  const metricInterval = Math.max(1000, options.metricIntervalMs ?? 30_000)
  const meterProvider = new sdk.sdkMetrics.MeterProvider({
    resource,
    readers: [
      new sdk.sdkMetrics.PeriodicExportingMetricReader({
        exporter: new SwitchableMetricExporter(live, sdk),
        exportIntervalMillis: metricInterval,
        exportTimeoutMillis: Math.min(EXPORT_TIMEOUT_MS + 5000, metricInterval), // the reader insists
      }),
    ],
  })

  const { CompositePropagator, W3CBaggagePropagator, W3CTraceContextPropagator } = sdk.core
  context.setGlobalContextManager(new sdk.asyncHooks.AsyncLocalStorageContextManager().enable())
  propagation.setGlobalPropagator(
    new CompositePropagator({ propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()] }),
  )
  trace.setGlobalTracerProvider(tracerProvider)
  metrics.setGlobalMeterProvider(meterProvider)

  const instrumentations: Instrumentation[] = [new sdk.undici.UndiciInstrumentation(), new sdk.pg.PgInstrumentation()]
  if (sdk.http) {
    const ignored = (url: string | undefined) => !!url && ignorePaths.some((prefix) => url.startsWith(prefix))
    // The OTLP exports run with tracing suppressed, so they never trace themselves.
    instrumentations.unshift(new sdk.http.HttpInstrumentation({ ignoreIncomingRequestHook: (request) => ignored(request.url) }))
  }
  sdk.instrumentation.registerInstrumentations({
    tracerProvider,
    meterProvider,
    instrumentations: [...instrumentations, ...(options.instrumentations ?? [])],
  })
  if (sdk.http) loadHttpModulesAgain()

  return {
    active: true,
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
