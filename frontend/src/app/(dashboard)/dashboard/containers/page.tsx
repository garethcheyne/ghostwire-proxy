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

interface AutoUpdatePolicy {
  enabled: boolean
  cron: string
  security_only: boolean
  excluded: string[]
  always_excluded: string[]
  last_run?: string | null
  last_result?: string | null
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
  const [policy, setPolicy] = useState<AutoUpdatePolicy | null>(null)
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [updating, setUpdating] = useState<string | null>(null)
  const [notice, setNotice] = useState('')

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
      try {
        const p = await api.get('/api/containers/auto-update')
        setPolicy(p.data)
      } catch {
        // Policy is admin-only; a non-admin still gets the scan.
      }
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

  const savePolicy = async (patch: Partial<AutoUpdatePolicy>) => {
    setSavingPolicy(true)
    setError('')
    try {
      const { data } = await api.put('/api/containers/auto-update', patch)
      setPolicy(data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not save the update policy')
    } finally {
      setSavingPolicy(false)
    }
  }

  const runUpdate = async (container?: string) => {
    setUpdating(container || 'all')
    setError('')
    setNotice('')
    try {
      const { data } = await api.post(
        '/api/containers/auto-update/run',
        container ? { container } : {},
        // Upgrading the whole stack sequentially takes minutes.
        { timeout: 900000 }
      )
      const failed = data.failed || []
      setNotice(
        `${data.packages_upgraded} package(s) upgraded` +
          (failed.length ? ` — failed: ${failed.join(', ')}` : '')
      )
      await load(true)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Update run failed')
    } finally {
      setUpdating(null)
    }
  }

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

      {notice && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-sm">
          <ShieldCheck className="h-4 w-4 flex-shrink-0" />
          <span>{notice}</span>
        </div>
      )}

      {/* Automatic updates */}
      {policy && (
        <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="font-semibold flex items-center gap-2">
                <RefreshCw className="h-4 w-4" />
                Automatic OS package updates
              </h2>
              <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
                Runs <code className="text-xs">apk upgrade</code> /{' '}
                <code className="text-xs">apt-get upgrade</code> inside each container on a
                schedule. Containers are updated one at a time, so a failure never leaves the
                whole stack mid-transaction.
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
              <input
                type="checkbox"
                checked={policy.enabled}
                disabled={savingPolicy}
                onChange={(e) => savePolicy({ enabled: e.target.checked })}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-disabled:opacity-50 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-background after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 mt-4">
            <div className="space-y-2">
              <label className="block text-sm font-medium">Schedule (cron, UTC)</label>
              <input
                value={policy.cron}
                onChange={(e) => setPolicy({ ...policy, cron: e.target.value })}
                onBlur={(e) => savePolicy({ cron: e.target.value })}
                className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-muted-foreground">
                Default <code>0 4 * * 0</code> — Sundays at 04:00 UTC.
              </p>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium">Never update in place</label>
              <input
                value={policy.excluded.join(', ')}
                onChange={(e) =>
                  setPolicy({ ...policy, excluded: e.target.value.split(',').map((v) => v.trim()) })
                }
                onBlur={(e) => savePolicy({ excluded: e.target.value.split(',').map((v) => v.trim()).filter(Boolean) })}
                placeholder="container-name, another-container"
                className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <p className="text-xs text-muted-foreground">
                Always excluded: {policy.always_excluded.join(', ')} — swapping libraries under a
                running database is not worth the risk, and watchtower replaces that image whole.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 mt-4 pt-4 border-t border-border">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={policy.security_only}
                disabled={savingPolicy}
                onChange={(e) => savePolicy({ security_only: e.target.checked })}
              />
              <span>
                Security updates only
                <span className="text-muted-foreground">
                  {' '}— Alpine has no security-only subset, so apk containers always take everything
                </span>
              </span>
            </label>

            <button
              onClick={() => runUpdate()}
              disabled={updating !== null}
              className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1.5"
            >
              {updating === 'all' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              {updating === 'all' ? 'Updating…' : 'Update all now'}
            </button>
          </div>

          {policy.last_run && (
            <p className="text-xs text-muted-foreground mt-3">
              Last run {String(policy.last_run).slice(0, 16).replace('T', ' ')} UTC
              {policy.last_result ? ` — ${policy.last_result}` : ''}
            </p>
          )}
        </div>
      )}

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
              {/* One button wraps the whole summary, including the reasons
                  line. It used to sit outside as a sibling, so the hover
                  highlight stopped short of the bottom of the card and that
                  line was not clickable even though everything around it
                  was. */}
              <button
                onClick={() => setExpanded(open ? null : c.name)}
                className="w-full px-4 pt-4 pb-3 text-left hover:bg-accent/50 transition-colors"
              >
                <div className="flex flex-wrap items-center gap-3">
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
                </div>

                <p className="mt-1.5 text-xs text-muted-foreground">
                  {(c.risk?.reasons || []).join(' · ')}
                </p>
              </button>

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

                  {c.scannable !== false && c.status === 'running' && (
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => runUpdate(c.name)}
                        disabled={
                          updating !== null ||
                          (policy?.always_excluded || []).includes(c.name) ||
                          (policy?.excluded || []).includes(c.name)
                        }
                        title={
                          (policy?.always_excluded || []).includes(c.name)
                            ? 'This container is never updated in place'
                            : undefined
                        }
                        className="h-9 px-3 rounded-md border border-input text-sm font-medium hover:bg-accent disabled:opacity-50 flex items-center gap-1.5"
                      >
                        {updating === c.name ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3.5 w-3.5" />
                        )}
                        {updating === c.name ? 'Updating…' : 'Update now'}
                      </button>
                      {(policy?.always_excluded || []).includes(c.name) && (
                        <span className="text-xs text-muted-foreground">
                          Excluded — updated by replacing the image, not in place.
                        </span>
                      )}
                    </div>
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
