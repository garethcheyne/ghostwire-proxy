'use client'

import { useEffect, useState } from 'react'
import {
  Boxes,
  Loader2,
  RefreshCw,
  AlertCircle,
  ShieldAlert,
  ShieldCheck,
  Globe,
  Package,
  Clock,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import api from '@/lib/api'

interface Pending {
  count: number
  security_count?: number
  packages?: {
    name: string
    current_version?: string
    available_version?: string
    security?: boolean
  }[]
  error?: string
}

interface Scan {
  name: string
  id: string
  status: string
  is_edge: boolean
  scannable?: boolean
  reason?: string
  os?: { pretty_name?: string | null }
  package_manager?: string | null
  installed_count?: number
  pending?: Pending
  auto_update?: { enabled: boolean; mechanism?: string | null; detail?: string | null }
  image_tag?: string | null
  image_age_days?: number | null
  risk?: { level: string; reasons: string[] }
}

interface Summary {
  total_containers: number
  by_level: Record<string, number>
  pending_updates_total: number
  security_updates_total: number
  edge_containers_at_risk: number
  stale_images: number
  needs_attention: number
}

const LEVEL_STYLES: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20',
  medium: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
  ok: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  unknown: 'bg-muted text-muted-foreground border-border',
}

export default function ContainersPage() {
  const [scans, setScans] = useState<Scan[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = async (refresh = false) => {
    if (refresh) setRefreshing(true)
    setError('')
    try {
      const { data } = await api.get('/api/containers/security', {
        params: refresh ? { refresh: true } : {},
        // A refresh execs into every container and refreshes each package
        // index, which is slow by nature — well past the client default.
        timeout: 180000,
      })
      setScans(data.containers || [])
      setSummary(data.summary || null)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not scan containers')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Boxes className="h-6 w-6 text-primary" />
            Container Security
          </h1>
          <p className="text-sm text-muted-foreground">
            OS packages, pending updates and image age for every container in the stack.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="h-9 px-3 rounded-md border border-input text-sm font-medium hover:bg-accent disabled:opacity-50 flex items-center gap-1.5"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {refreshing ? 'Scanning…' : 'Rescan'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Why in-container updates aren't the whole answer. Stated once, plainly,
          because acting on the numbers below without it leads people to run
          `apk upgrade` in a shell and believe they have fixed something. */}
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        <p>
          <strong className="text-foreground">Updating a container means rebuilding it.</strong>{' '}
          Packages upgraded inside a running container are discarded the next time it is
          recreated. Pending updates below show live exposure; image age shows whether the
          image itself needs rebuilding from a refreshed base. Both matter, and only the
          rebuild is durable.
        </p>
      </div>

      {summary && (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Containers</p>
            <p className="text-2xl font-semibold mt-1">{summary.total_containers}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Need attention</p>
            <p
              className={`text-2xl font-semibold mt-1 ${
                summary.needs_attention ? 'text-orange-600 dark:text-orange-400' : ''
              }`}
            >
              {summary.needs_attention}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Pending updates</p>
            <p className="text-2xl font-semibold mt-1">{summary.pending_updates_total}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Security updates</p>
            <p
              className={`text-2xl font-semibold mt-1 ${
                summary.security_updates_total ? 'text-red-600 dark:text-red-400' : ''
              }`}
            >
              {summary.security_updates_total}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Stale images</p>
            <p className="text-2xl font-semibold mt-1">{summary.stale_images}</p>
            <p className="text-xs text-muted-foreground">over 90 days old</p>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {scans.map((c) => {
          const level = c.risk?.level || 'unknown'
          const open = expanded === c.name
          const pkgs = c.pending?.packages || []

          return (
            <div key={c.name} className="rounded-xl border border-border bg-card overflow-hidden">
              <button
                onClick={() => setExpanded(open ? null : c.name)}
                className="w-full p-4 flex flex-wrap items-center gap-3 text-left hover:bg-accent/50 transition-colors"
              >
                {open ? (
                  <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                )}

                <div className="flex-1 min-w-[200px]">
                  <p className="font-medium flex items-center gap-2 flex-wrap">
                    {c.name}
                    {c.is_edge && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center gap-1">
                        <Globe className="h-3 w-3" />
                        edge
                      </span>
                    )}
                    {c.status !== 'running' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                        {c.status}
                      </span>
                    )}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {c.os?.pretty_name || 'Unknown OS'}
                    {c.package_manager ? ` · ${c.package_manager}` : ''}
                    {c.installed_count ? ` · ${c.installed_count} packages` : ''}
                  </p>
                </div>

                <div className="flex items-center gap-4 text-sm">
                  <div className="text-right">
                    <p className="font-medium tabular-nums">{c.pending?.count ?? 0}</p>
                    <p className="text-xs text-muted-foreground">pending</p>
                  </div>
                  {c.image_age_days !== null && c.image_age_days !== undefined && (
                    <div className="text-right">
                      <p
                        className={`font-medium tabular-nums ${
                          c.image_age_days > 180
                            ? 'text-red-600 dark:text-red-400'
                            : c.image_age_days > 90
                            ? 'text-amber-600 dark:text-amber-400'
                            : ''
                        }`}
                      >
                        {c.image_age_days}d
                      </p>
                      <p className="text-xs text-muted-foreground">image age</p>
                    </div>
                  )}
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
                      LEVEL_STYLES[level] || LEVEL_STYLES.unknown
                    }`}
                  >
                    {level}
                  </span>
                </div>
              </button>

              <div className="px-4 pb-3 -mt-1">
                <p className="text-xs text-muted-foreground">
                  {(c.risk?.reasons || []).join(' · ')}
                </p>
              </div>

              {open && (
                <div className="border-t border-border p-4 space-y-4 bg-muted/20">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" />
                        Image
                      </p>
                      <p className="text-sm font-mono break-all">{c.image_tag || '—'}</p>
                      {c.image_age_days !== null && c.image_age_days !== undefined && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Built {c.image_age_days} days ago
                        </p>
                      )}
                    </div>

                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
                        {c.auto_update?.enabled ? (
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                        ) : (
                          <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                        )}
                        Automatic updates
                      </p>
                      <p className="text-sm">
                        {c.auto_update?.enabled ? 'Enabled' : 'Not enabled'}
                        {c.auto_update?.mechanism ? ` — ${c.auto_update.mechanism}` : ''}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {c.auto_update?.detail}
                      </p>
                    </div>
                  </div>

                  {c.scannable === false && (
                    <p className="text-sm text-muted-foreground">{c.reason}</p>
                  )}

                  {c.pending?.error && (
                    <p className="text-sm text-amber-600 dark:text-amber-400">
                      Update check failed: {c.pending.error}
                    </p>
                  )}

                  {pkgs.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
                        <Package className="h-3.5 w-3.5" />
                        Packages with updates available ({pkgs.length})
                      </p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm min-w-[420px]">
                          <thead>
                            <tr className="border-b border-border">
                              <th className="py-1.5 text-left text-xs uppercase tracking-wide text-muted-foreground font-medium">
                                Package
                              </th>
                              <th className="py-1.5 text-left text-xs uppercase tracking-wide text-muted-foreground font-medium">
                                Installed
                              </th>
                              <th className="py-1.5 text-left text-xs uppercase tracking-wide text-muted-foreground font-medium">
                                Available
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {pkgs.map((p) => (
                              <tr key={p.name} className="border-b border-border/50 last:border-0">
                                <td className="py-1 font-mono text-xs">
                                  {p.name}
                                  {p.security && (
                                    <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-600 dark:text-red-400">
                                      security
                                    </span>
                                  )}
                                </td>
                                <td className="py-1 font-mono text-xs text-muted-foreground">
                                  {p.current_version || '—'}
                                </td>
                                <td className="py-1 font-mono text-xs">
                                  {p.available_version || '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
