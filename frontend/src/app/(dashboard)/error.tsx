'use client'

/**
 * Dashboard-scope error boundary. Keeps the navigation chrome intact and just
 * replaces the inner page content with a recoverable error card.
 */

import { useEffect } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error('Dashboard page error:', error)
  }, [error])

  // A chunk that 404s means this client is running a build the server no longer
  // has. reset() re-renders the same stale code and fails again, so the button
  // has to clear caches and do a real reload instead.
  const isStaleBuild =
    /Failed to load chunk|ChunkLoadError|Loading chunk|Failed to find Server Action/i.test(
      error.message || '',
    )

  const handleRetry = async () => {
    if (!isStaleBuild) {
      reset()
      return
    }
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
      // Best effort — reload regardless.
    }
    window.location.reload()
  }

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-red-500" />
        <h2 className="mt-4 text-lg font-semibold">This page failed to load</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.message || 'An unexpected error occurred while rendering this page.'}
        </p>
        {error.digest && (
          <p className="mt-1 text-xs text-muted-foreground/70">
            Reference: <code>{error.digest}</code>
          </p>
        )}
        {isStaleBuild && (
          <p className="mt-2 text-xs text-muted-foreground">
            A new version was deployed. Retry will clear the cached app and reload.
          </p>
        )}
        <button
          onClick={handleRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    </div>
  )
}
