import type { AnalyticsTestResult, GetGhostwireConfig } from "./types"

/**
 * Server-side reporting to Ghostwire Analytics. Server code only: the config carries the error key.
 *
 * Reporting only observes. It never throws, never changes how the app handles the error, and gives
 * up after three seconds. Call it from a catch the app already has, or from onRequestError:
 *
 *   // src/instrumentation.ts
 *   export async function onRequestError(error: unknown, request: { path: string; method: string }) {
 *     if (process.env.NEXT_RUNTIME !== "nodejs") return
 *     const { reportServerError } = await import("@/components/analytics")
 *     const { getAnalyticsConfig } = await import("@/lib/analytics-config")
 *     await reportServerError(getAnalyticsConfig, error, { handled: false, request })
 *   }
 */
export async function reportServerError(
  getConfig: GetGhostwireConfig,
  error: unknown,
  context: {
    handled?: boolean
    request?: { path?: string; method?: string }
    tags?: Record<string, string>
  } = {},
): Promise<void> {
  try {
    const config = await getConfig()
    if (!config?.ingestKey) return
    const err = error instanceof Error ? error : new Error(String(error))
    await fetch(`${config.url.replace(/\/+$/, "")}/api/errors`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${config.ingestKey}` },
      body: JSON.stringify({
        website: config.websiteId,
        platform: "node",
        error: { type: err.name, message: err.message.slice(0, 2000), stack: err.stack?.slice(0, 20_000) },
        handled: context.handled ?? true,
        request: context.request ? { method: context.request.method, url: context.request.path } : undefined,
        environment: process.env.NODE_ENV,
        release: config.release,
        tags: context.tags,
        timestamp: Date.now(),
      }),
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    })
  } catch {
    // Never let reporting break the thing it reports on.
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** The same rule, and wording, in every Ghostwire app's settings validation (Python apps included). */
export const ANALYTICS_HTTP_URL_MESSAGE =
  "The Analytics URL must use https://. Plain http:// is allowed only for a private address: localhost, " +
  "a private IP address, or a name without dots or ending in .internal (such as analytics or host.docker.internal)."

function ipv4Private(host: string) {
  const parts = host.split(".").map(Number)
  if (parts.length !== 4 || parts.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return null
  const [a, b] = parts
  return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254)
}

/**
 * Whether plain http is allowed to this host. Ghostwire apps are internal tools, often on the same
 * machine or network as their Analytics: localhost, a loopback, private or link-local IP, or a name
 * without dots (a Docker service such as `analytics`) or under .internal (`host.docker.internal`).
 */
export function isHttpAllowedHost(hostname: string) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "").split("%")[0]
  if (!host) return false
  if (/^[0-9.]+$/.test(host)) return ipv4Private(host) === true
  if (host.includes(":")) {
    // An IPv4-mapped address, which URL writes in hex (::ffff:a00:1 for 10.0.0.1).
    const mapped = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(host)
    if (mapped) {
      const [hi, lo] = [parseInt(mapped[1], 16), parseInt(mapped[2], 16)]
      return ipv4Private(`${hi >> 8}.${hi & 255}.${lo >> 8}.${lo & 255}`) === true
    }
    return host === "::1" || /^f[cd][0-9a-f]{2}:/.test(host) || /^fe[89ab][0-9a-f]:/.test(host)
  }
  return host === "localhost" || host.endsWith(".localhost") || host.endsWith(".internal") || !host.includes(".")
}

/** Why the Analytics URL can't be used, or null: https, or http to a host isHttpAllowedHost accepts. */
export function analyticsUrlProblem(value: string): string | null {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return "The Analytics URL isn't a valid address."
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "The Analytics URL isn't a valid address."
  if (url.protocol === "http:" && !isHttpAllowedHost(url.hostname)) return ANALYTICS_HTTP_URL_MESSAGE
  return null
}

/**
 * For the settings card's "Test connection": checks that the Analytics URL answers and the values
 * are well-formed. It writes nothing to Analytics; the site's Realtime view confirms data arrives.
 */
export async function testGhostwireConnection(settings: {
  url: string
  websiteId: string
  ingestKey?: string | null
}): Promise<AnalyticsTestResult> {
  const problem = analyticsUrlProblem(settings.url)
  if (problem) return { ok: false, message: problem }
  if (!UUID.test(settings.websiteId.trim())) {
    return { ok: false, message: "The website ID should be a UUID, from Analytics: Settings → the site → Tracking code." }
  }
  if (settings.ingestKey && !settings.ingestKey.startsWith("gwe_")) {
    return { ok: false, message: "The ingest key should start with gwe_, from Analytics: Settings → the site → Errors." }
  }
  try {
    const response = await fetch(`${settings.url.replace(/\/+$/, "")}/api/heartbeat`, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    })
    if (!response.ok) return { ok: false, message: `Analytics answered with HTTP ${response.status}.` }
  } catch {
    return { ok: false, message: "Couldn't reach Analytics at that URL." }
  }
  return {
    ok: true,
    message: "Analytics answered. Open the site's Realtime view in Analytics to see data arrive.",
  }
}
