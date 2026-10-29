import type { GetGhostwireConfig } from "./types"

/**
 * The /gw/ relay: serves Analytics' tracker from this app's origin and forwards what it sends.
 *
 *   // src/app/gw/[...path]/route.ts
 *   import { createGhostwireRelay } from "@/components/analytics"
 *   import { getAnalyticsConfig } from "@/lib/analytics-config"
 *   export const { GET, POST } = createGhostwireRelay(getAnalyticsConfig)
 *
 * Only these paths are relayed; everything else (and everything while reporting is off) is a 404.
 */
const SCRIPTS = new Set(["script.js", "recorder.js"])
const POST_PATHS = new Set(["api/send", "api/record"])
const GET_PATH = /^api\/websites\/[0-9a-f-]{36}\/recorder$/i // the recorder asks whether it should record
const MAX_BODY = 5 * 1024 * 1024 // replay chunks are the largest posts
const SCRIPT_CACHE_SECONDS = 3600

type RouteContext = { params: Promise<{ path: string[] }> }

function notFound() {
  return new Response("Not Found", { status: 404, headers: { "Cache-Control": "no-store" } })
}

function base(url: string) {
  return url.replace(/\/+$/, "")
}

/** The visitor's address, as the reverse proxy in front of this app passed it on. */
function clientIp(request: Request) {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
  return forwarded || request.headers.get("x-real-ip") || ""
}

function forwardHeaders(request: Request) {
  const headers = new Headers()
  for (const name of ["content-type", "user-agent", "accept-language"]) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  const ip = clientIp(request)
  if (ip) headers.set("x-forwarded-for", ip)
  return headers
}

async function passThrough(upstream: Response, cacheControl: string) {
  const headers = new Headers({ "Cache-Control": cacheControl })
  const type = upstream.headers.get("content-type")
  if (type) headers.set("content-type", type)
  return new Response(await upstream.arrayBuffer(), { status: upstream.status, headers })
}

export function createGhostwireRelay(getConfig: GetGhostwireConfig) {
  async function GET(request: Request, { params }: RouteContext) {
    const path = (await params).path.join("/")
    const config = await getConfig().catch(() => null)
    if (!config?.browser) return notFound()

    try {
      if (SCRIPTS.has(path)) {
        const upstream = await fetch(`${base(config.url)}/${path}`, {
          signal: AbortSignal.timeout(10_000),
          next: { revalidate: SCRIPT_CACHE_SECONDS },
        })
        if (!upstream.ok) return new Response(null, { status: 502 })
        return passThrough(upstream, `public, max-age=${SCRIPT_CACHE_SECONDS}`)
      }
      if (GET_PATH.test(path)) {
        const upstream = await fetch(`${base(config.url)}/${path}`, {
          headers: forwardHeaders(request),
          signal: AbortSignal.timeout(10_000),
          cache: "no-store",
        })
        return passThrough(upstream, "no-store")
      }
    } catch {
      return new Response(null, { status: 502 })
    }
    return notFound()
  }

  async function POST(request: Request, { params }: RouteContext) {
    const path = (await params).path.join("/")
    if (!POST_PATHS.has(path)) return notFound()
    const config = await getConfig().catch(() => null)
    if (!config?.browser) return notFound()

    const length = Number(request.headers.get("content-length") ?? 0)
    if (length > MAX_BODY) return new Response(null, { status: 413 })
    const body = await request.arrayBuffer()
    if (body.byteLength > MAX_BODY) return new Response(null, { status: 413 })

    try {
      const upstream = await fetch(`${base(config.url)}/${path}`, {
        method: "POST",
        headers: forwardHeaders(request),
        body,
        signal: AbortSignal.timeout(10_000),
        cache: "no-store",
      })
      return passThrough(upstream, "no-store")
    } catch {
      return new Response(null, { status: 502 })
    }
  }

  return { GET, POST }
}
