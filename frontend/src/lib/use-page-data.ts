import { useEffect, useRef } from 'react'

/**
 * Hook that replaces the common `useEffect(() => { fetchData() }, [deps])` pattern.
 * Adds automatic re-fetch when the browser tab regains focus (after being hidden > 2s).
 *
 * Usage:
 *   usePageData(fetchData)                      // fetch on mount + refetch on focus
 *   usePageData(fetchData, [activeTab, period]) // fetch on mount + deps change + refetch on focus
 */
export function usePageData(fetcher: () => void, deps: any[] = []) {
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  // Fetch on mount and when deps change
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetcherRef.current() }, deps)

  // Refetch when window regains focus after being hidden
  useEffect(() => {
    let hiddenAt = 0
    const onVisibility = () => {
      if (document.hidden) {
        hiddenAt = Date.now()
      } else if (hiddenAt && Date.now() - hiddenAt > 2000) {
        fetcherRef.current()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])
}
