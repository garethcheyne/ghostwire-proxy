'use client'

import { useEffect, useState } from 'react'

/**
 * Delays a rapidly-changing value (a search box, typically) so it doesn't fire
 * a request on every keystroke.
 */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
