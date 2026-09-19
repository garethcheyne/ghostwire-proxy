'use client'

import { useEffect } from 'react'

import { registerServiceWorker } from '@/lib/push-notifications'

/**
 * Registers the service worker once, on app load.
 *
 * Previously this only happened if you opened Settings → Notifications and
 * interacted with the push controls, which meant that until you did:
 *  - the browser never offered to install the PWA (an active service worker is
 *    an install prerequisite), and
 *  - sw.js's offline caching never ran for anyone.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    // Dev serves an unbundled app; a caching SW there mostly gets in the way of
    // hot reload.
    if (process.env.NODE_ENV !== 'production') return
    if (typeof window === 'undefined') return

    let cancelled = false
    // Registration competes with the first paint for bandwidth; let the page
    // settle first.
    const timer = window.setTimeout(() => {
      if (cancelled) return
      void registerServiceWorker()
    }, 1000)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  return null
}

export default ServiceWorkerRegistrar
