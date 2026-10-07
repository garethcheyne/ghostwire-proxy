export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(i ? 1 : 0))} ${sizes[i]}`
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return '–'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`
}

export function formatCount(n: number | null | undefined): string {
  if (n == null) return '–'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString()
}

export function formatPct(n: number | null | undefined): string {
  if (n == null) return '–'
  return `${n < 10 ? n.toFixed(2) : n.toFixed(1)}%`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleString()
}

/** Text colour for a status code, readable in light and dark. */
export function statusTone(status: number): string {
  if (status >= 500) return 'text-red-600 dark:text-red-400 bg-red-500/10'
  if (status >= 400) return 'text-amber-700 dark:text-amber-400 bg-amber-500/10'
  if (status >= 300) return 'text-sky-700 dark:text-sky-400 bg-sky-500/10'
  if (status >= 200) return 'text-green-600 dark:text-green-400 bg-green-500/10'
  return 'text-muted-foreground bg-muted'
}

export function methodTone(method: string): string {
  switch (method) {
    case 'GET':
      return 'text-green-600 dark:text-green-400 bg-green-500/10'
    case 'POST':
      return 'text-sky-700 dark:text-sky-400 bg-sky-500/10'
    case 'PUT':
    case 'PATCH':
      return 'text-amber-700 dark:text-amber-400 bg-amber-500/10'
    case 'DELETE':
      return 'text-red-600 dark:text-red-400 bg-red-500/10'
    default:
      return 'text-muted-foreground bg-muted'
  }
}

/** Chart series colours (status classes, latency). */
export const SERIES = {
  s2xx: '#22c55e',
  s3xx: '#0ea5e9',
  s4xx: '#f59e0b',
  s5xx: '#ef4444',
  s1xx: '#94a3b8',
  p50: '#0ea5e9',
  p95: '#a855f7',
} as const
