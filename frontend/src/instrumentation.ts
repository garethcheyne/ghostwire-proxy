// System monitoring with Ghostwire Analytics (ghostwire-suite/docs/analytics-reporting.md). Off by
// default; switched on, and pointed at a site, in Settings → Ghostwire Analytics. Nothing is sent
// while it's off.

export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return
  // Monitoring is optional: if it can't load, the admin UI starts the same without it.
  try {
    const { registerGhostwireTelemetry } = await import('@/components/analytics/telemetry')
    const { getAnalyticsConfig } = await import('@/lib/analytics-config')
    registerGhostwireTelemetry(getAnalyticsConfig, { serviceName: 'ui', serviceNamespace: 'ghostwire-proxy' })
  } catch (error) {
    console.error('monitoring.start_failed: monitoring did not start; the app runs without it', error)
  }
}

/** Server errors Next.js caught, to Ghostwire Analytics' Errors while monitoring is on. */
export async function onRequestError(error: unknown, request: { path: string; method: string }) {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return
  const { reportServerError } = await import('@/components/analytics')
  const { getAnalyticsConfig } = await import('@/lib/analytics-config')
  // Not awaited: reporting never delays the response. The path without its query string, which
  // can carry tokens.
  void reportServerError(getAnalyticsConfig, error, {
    handled: false,
    request: { method: request.method, path: request.path.split('?')[0] },
  })
}
