'use client'

import { useEffect } from 'react'

/**
 * Detects "Failed to find Server Action" errors that occur after a deployment
 * (stale clients with old JS referencing old server action IDs) and triggers
 * a full page reload to pick up the new JavaScript bundles.
 */
export function StaleDeploymentHandler() {
  useEffect(() => {
    const handler = (event: ErrorEvent) => {
      const msg = event.message || ''
      if (msg.includes('Failed to find Server Action') || msg.includes('server action')) {
        console.warn('[Ghostwire] Detected stale deployment — reloading to get updated code...')
        window.location.reload()
      }
    }

    const rejectionHandler = (event: PromiseRejectionEvent) => {
      const reason = event.reason
      const msg = typeof reason === 'string' ? reason : reason?.message || reason?.digest || ''
      if (msg.includes('Failed to find Server Action') || msg.includes('NEXT_NOT_FOUND')) {
        console.warn('[Ghostwire] Detected stale deployment — reloading to get updated code...')
        window.location.reload()
      }
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
