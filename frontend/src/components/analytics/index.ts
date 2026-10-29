export { GhostwireTracker } from "./tracker"
// Reporting to Ghostwire Analytics (ghostwire-suite/docs/analytics-reporting.md). (Below the first
// line because shadcn add drops a file's leading comments, JSDoc included.)
// Server code only (the tracker, relay and reporter). Client components import the settings card
// from its own file: import { AnalyticsSettings } from "@/components/analytics/analytics-settings"
// System monitoring is imported from its own files too, so the OpenTelemetry SDK only loads where
// it's used: "@/components/analytics/telemetry" (instrumentation.ts, workers) and
// "@/components/analytics/otlp-relay" (src/app/internal/otlp/v1/[signal]/route.ts).
export { createGhostwireRelay } from "./relay"
export { analyticsUrlProblem, ANALYTICS_HTTP_URL_MESSAGE, isHttpAllowedHost, reportServerError, testGhostwireConnection } from "./report"
export type {
  AnalyticsSettingsChange,
  AnalyticsSettingsValue,
  AnalyticsTestResult,
  GetGhostwireConfig,
  GhostwireConfig,
} from "./types"
