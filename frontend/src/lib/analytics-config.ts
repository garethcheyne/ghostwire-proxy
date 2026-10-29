import 'server-only'

import type { GhostwireConfig } from '@/components/analytics/types'

/**
 * The Ghostwire Analytics settings for this server (its telemetry, the /gw/ relay and the tracker
 * tag), or null while monitoring is off. Server-side only: the config carries the ingest key.
 *
 * The API keeps the settings (Settings → Ghostwire Analytics); this reads them from its internal
 * endpoint on the Docker network and keeps them for a minute, so a change applies within a minute.
 * A failed read keeps the last answer (or off), and never throws.
 */
const CACHE_MS = 60_000
const FAILED_RETRY_MS = 15_000

let cached: { value: GhostwireConfig | null; until: number } | null = null
let pending: Promise<GhostwireConfig | null> | null = null

async function fetchConfig(): Promise<GhostwireConfig | null> {
  const backend = process.env.BACKEND_URL || 'http://ghostwire-proxy-api:8000'
  try {
    const response = await fetch(`${backend}/api/internal/analytics-config`, {
      headers: { 'X-Internal-Auth': process.env.INTERNAL_AUTH_TOKEN || '' },
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = (await response.json()) as Omit<GhostwireConfig, 'release'> | null
    const value = data?.url ? { ...data, release: process.env.APP_VERSION } : null
    cached = { value, until: Date.now() + CACHE_MS }
    return value
  } catch {
    const value = cached?.value ?? null
    cached = { value, until: Date.now() + FAILED_RETRY_MS }
    return value
  }
}

export async function getAnalyticsConfig(): Promise<GhostwireConfig | null> {
  if (cached && Date.now() < cached.until) return cached.value
  pending ??= fetchConfig().finally(() => {
    pending = null
  })
  return pending
}
