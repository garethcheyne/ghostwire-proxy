import { context } from "@opentelemetry/api"
import { suppressTracing } from "@opentelemetry/core"

import type { GetGhostwireConfig } from "./types"

/**
 * The internal OTLP relay: the stack's OpenTelemetry Collector (ghostwire-<app>-otel) sends its
 * container and host metrics here, and this forwards them to Analytics with the URL and ingest key
 * from Settings, so the Collector's config never holds either.
 *
 *   // src/app/internal/otlp/v1/[signal]/route.ts
 *   import { createOtlpRelay } from "@/components/analytics/otlp-relay"
 *   import { getAnalyticsConfig } from "@/lib/analytics-config"
 *   export const { POST } = createOtlpRelay(getAnalyticsConfig)
 *
 * Only POST /internal/otlp/v1/metrics and /v1/traces, only from private addresses (the stack's
 * Docker network): anything that came through the reverse proxy from outside carries a public
 * address in X-Forwarded-For and is refused. A 404 while monitoring is off, so the Collector drops
 * what it holds instead of queueing it.
 */
const SIGNALS = new Set(["metrics", "traces"])
const CONTENT_TYPES = new Set(["application/x-protobuf", "application/json"])
const MAX_BODY = 10 * 1024 * 1024
const TIMEOUT_MS = 10_000

type RouteContext = { params: Promise<{ signal: string }> }

function status(code: number) {
  return new Response(null, { status: code, headers: { "Cache-Control": "no-store" } })
}

function ipv4Private(ip: string) {
  const parts = ip.split(".").map(Number)
  if (parts.length !== 4 || parts.some((p) => !Number.isInteger(p) || p < 0 || p > 255)) return false
  const [a, b] = parts
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}

/** Loopback, RFC 1918, IPv6 loopback, unique-local and link-local; IPv4-mapped IPv6 is unwrapped. */
export function isPrivateAddress(raw: string): boolean {
  let ip = raw.trim().toLowerCase()
  if (ip.startsWith("[")) ip = ip.slice(1, ip.indexOf("]")) // [v6]:port
  else if (/^\d+\.\d+\.\d+\.\d+:\d+$/.test(ip)) ip = ip.slice(0, ip.lastIndexOf(":")) // v4:port
  if (ip.startsWith("::ffff:")) ip = ip.slice(7)
  if (ip.includes(".")) return ipv4Private(ip)
  if (ip === "::1") return true
  return /^f[cd][0-9a-f]{2}:/.test(ip) || /^fe[89ab][0-9a-f]:/.test(ip)
}

/**
 * Every address the request passed through. Next.js fills X-Forwarded-For with the socket's address
 * when no proxy set it, so a direct connection from the Collector shows up here too.
 */
function sourceAddresses(request: Request) {
  const addresses: string[] = []
  for (const value of request.headers.get("x-forwarded-for")?.split(",") ?? []) addresses.push(value)
  const realIp = request.headers.get("x-real-ip")
  if (realIp) addresses.push(realIp)
  for (const match of request.headers.get("forwarded")?.matchAll(/for="?([^";,]+)/gi) ?? []) addresses.push(match[1])
  return addresses.map((a) => a.trim()).filter(Boolean)
}

function fromInsideStack(request: Request) {
  const addresses = sourceAddresses(request)
  return addresses.length > 0 && addresses.every(isPrivateAddress)
}

export function createOtlpRelay(getConfig: GetGhostwireConfig) {
  async function POST(request: Request, { params }: RouteContext) {
    const { signal } = await params
    if (!SIGNALS.has(signal)) return status(404)
    if (!fromInsideStack(request)) return status(403)

    const config = await getConfig().catch(() => null)
    const url = config?.url?.trim().replace(/\/+$/, "")
    const key = config?.ingestKey?.trim()
    if (!url || !key) return status(404)

    const contentType = (request.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase()
    if (!CONTENT_TYPES.has(contentType)) return status(415)
    if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY) return status(413)
    const body = await request.arrayBuffer().catch(() => null)
    if (!body) return status(400)
    if (body.byteLength > MAX_BODY) return status(413)

    const headers = new Headers({ "content-type": contentType, authorization: `Bearer ${key}` })
    const encoding = request.headers.get("content-encoding")
    if (encoding) headers.set("content-encoding", encoding)

    try {
      // Not traced: forwarding monitoring data shouldn't produce more of it.
      const upstream = await context.with(suppressTracing(context.active()), () =>
        fetch(`${url}/v1/${signal}`, {
          method: "POST",
          headers,
          body,
          signal: AbortSignal.timeout(TIMEOUT_MS),
          cache: "no-store",
        }),
      )
      const responseHeaders = new Headers({ "Cache-Control": "no-store" })
      const type = upstream.headers.get("content-type")
      if (type) responseHeaders.set("content-type", type)
      return new Response(await upstream.arrayBuffer(), { status: upstream.status, headers: responseHeaders })
    } catch (error) {
      return status(error instanceof Error && error.name === "TimeoutError" ? 504 : 502)
    }
  }

  return { POST }
}
