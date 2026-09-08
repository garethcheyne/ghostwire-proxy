'use client'

import { useEffect } from 'react'

const RELOAD_GUARD_KEY = 'gw_stale_reload_at'
// Long enough that a genuinely broken build can't spin, short enough that a
// second real deployment later in the day still self-heals.
const RELOAD_GUARD_MS = 30_000

/**
 * Recovers clients left on a previous deployment.
 *
 * Two failure modes, both fixed by getting fresh code:
 *  - "Failed to find Server Action": old JS calling server action IDs that no
 *    longer exist.
 *  - "Failed to load chunk ...": the HTML the client is running references JS
 *    chunk filenames that the current build no longer contains.
 *
 * The chunk case needs the service worker caches cleared first. Otherwise the
 * reload is served the same stale HTML from cache and fails identically, which
 * is a loop the user cannot escape by refreshing.
 */
export function StaleDeploymentHandler() {
  useEffect(() => {
    const isStaleDeployment = (msg: string) =>
      msg.includes('Failed to find Server Action') ||
      msg.includes('server action') ||
      msg.includes('NEXT_NOT_FOUND') ||
      // Chunk load failures after a redeploy
      msg.includes('Failed to load chunk') ||
      msg.includes('ChunkLoadError') ||
      msg.includes('Loading chunk')

    const recover = async (msg: string) => {
      // One reload per window. Without this, a build that is genuinely broken
      // would reload forever.
      try {
        const last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || 0)
        if (Date.now() - last < RELOAD_GUARD_MS) {
          console.error('[Ghostwire] Stale-deployment recovery already attempted; not reloading again.', msg)
          return
        }
        sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()))
      } catch {
        // sessionStorage can throw in private modes; proceeding is better than
        // leaving the app broken.
      }

      console.warn('[Ghostwire] Detected stale deployment — clearing caches and reloading...', msg)

      // Drop any cached HTML pinning this client to the old build, and let the
      // newest service worker take over.
      try {
        if ('caches' in window) {
          const names = await caches.keys()
          await Promise.all(names.map((n) => caches.delete(n)))
        }
        if ('serviceWorker' in navigator) {
          const regs = await navigator.serviceWorker.getRegistrations()
          await Promise.all(regs.map((r) => r.update().catch(() => r.unregister())))
        }
      } catch {
        // Cache/SW teardown is best effort; reload regardless.
      }

      window.location.reload()
    }

    const handler = (event: ErrorEvent) => {
      const msg = event.message || ''
      if (isStaleDeployment(msg)) void recover(msg)
    }

    const rejectionHandler = (event: PromiseRejectionEvent) => {
      const reason = event.reason
      const msg = typeof reason === 'string' ? reason : reason?.message || reason?.digest || ''
      if (isStaleDeployment(msg)) void recover(msg)
    }

    window.addEventListener('error', handler)
    window.addEventListener('unhandledrejection', rejectionHandler)
    return () => {
      window.removeEventListener('error', handler)
      window.removeEventListener('unhandledrejection', rejectionHandler)
    }
  }, [])

  return null
}
