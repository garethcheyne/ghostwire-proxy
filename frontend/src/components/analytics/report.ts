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

/**
 * For the settings card's "Test connection": checks that the Analytics URL answers and the values
 * are well-formed. It writes nothing to Analytics; the site's Realtime view confirms data arrives.
 */
export async function testGhostwireConnection(settings: {
  url: string
  websiteId: string
  ingestKey?: string | null
}): Promise<AnalyticsTestResult> {
  let url: URL
  try {
    url = new URL(settings.url)
  } catch {
    return { ok: false, message: "The Analytics URL isn't a valid address." }
  }
  const local = ["localhost", "127.0.0.1", "::1"].includes(url.hostname)
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    return { ok: false, message: "The Analytics URL must use https://." }
  }
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
