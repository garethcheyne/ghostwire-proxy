export interface AnalyticsTestResult {
  ok: boolean
  message: string
}

// What an app's Settings hold for Ghostwire Analytics, and what the shared pieces need. The spec is
// ghostwire-suite/docs/analytics-reporting.md. (Below the first statement because shadcn add drops
// a file's leading comments, JSDoc included.)

/** The live configuration, while reporting is switched on. Server-side only (it carries the error key). */
export interface GhostwireConfig {
  /** The Analytics instance, e.g. https://analytics.example.com. */
  url: string
  /** The site's UUID, from Analytics: Settings → the site → Tracking code. */
  websiteId: string
  /** The site's `gwe_` ingest key, for monitoring (OTLP) and server errors. Server-side only. */
  ingestKey?: string | null
  /** Share of requests traced, 0-100. */
  traceSample: number
  /** Load the visitor tracker (page views) through /gw/. */
  browser: boolean
  /** Load the recorder for session replay and heatmaps (needs `browser`). */
  replay: boolean
  /** Tags page views and errors with the app's version (its VERSION file). */
  release?: string
}

/**
 * Returns the configuration while reporting is switched on, otherwise null. Each app implements it
 * in src/lib/analytics-config.ts over its own settings store, cached for about a minute.
 */
export type GetGhostwireConfig = () => Promise<GhostwireConfig | null>

/** What the settings card shows. The ingest key is write-only: the browser only learns whether one is set. */
export interface AnalyticsSettingsValue {
  enabled: boolean
  url: string
  websiteId: string
  traceSample: number
  browser: boolean
  replay: boolean
  ingestKeySet: boolean
}

/** What the settings card saves. `ingestKey`: undefined keeps the stored key, "" removes it. */
export interface AnalyticsSettingsChange {
  enabled: boolean
  url: string
  websiteId: string
  traceSample: number
  browser: boolean
  replay: boolean
  ingestKey?: string
}
