import { connection } from "next/server"

import type { GetGhostwireConfig } from "./types"

/**
 * The Ghostwire Analytics visitor tags (page views), for the root layout's <head>, while visitor
 * analytics is switched on. A server component (no "use client"):
 * plain <script> tags go out in the first HTML and run before hydration, so the tracker sees errors
 * thrown while the app loads. It reads the settings on every request, not at build time, so turning
 * reporting on or off in Settings applies without a rebuild. Renders nothing while it's off.
 *
 * The scripts load from this app's own /gw/ relay (relay.ts), so no Content-Security-Policy change
 * is needed for an Analytics URL that is only known at run time.
 */
export async function GhostwireTracker({ getConfig }: { getConfig: GetGhostwireConfig }) {
  await connection()
  const config = await getConfig().catch(() => null)
  if (!config?.browser) return null

  return (
    <>
      <script
        defer
        src="/gw/script.js"
        data-website-id={config.websiteId}
        data-host-url="/gw"
        data-errors="true"
        data-performance="true"
        data-exclude-search="true"
        {...(config.release ? { "data-release": config.release } : {})}
      />
      {config.replay && (
        <script defer src="/gw/recorder.js" data-website-id={config.websiteId} data-host-url="/gw" />
      )}
    </>
  )
}
