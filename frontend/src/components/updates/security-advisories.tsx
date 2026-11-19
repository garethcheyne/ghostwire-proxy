'use client'

import { useState } from 'react'
import { AlertTriangle, CheckCircle, ExternalLink, Loader2, ShieldAlert } from 'lucide-react'
import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { useConfirm } from '@/components/confirm-dialog'

// The upgrade script's last CVE report (cve/README.md), served by GET /api/updates/cve.

export type CveStatusName = 'vulnerable' | 'unknown' | 'mitigated' | 'not_exposed' | 'fixed'

export interface CveAdvisory {
  id: string
  aliases: string[]
  title: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  component: string
  version: string | null
  status: CveStatusName
  reasons: string[]
  fixed_in: string[]
  fix_note: string
  mitigations: string[]
}

export interface CveStatus {
  report: {
    meta: { checked_at?: string; version?: string; host?: string }
    summary: Partial<Record<CveStatusName | 'invalid', number>>
    advisories: CveAdvisory[]
  } | null
  error: string | null
  active_mitigations: string[]
  available_mitigations: Record<string, string>
}

/** Open advisories (anything not fixed) for one component, e.g. the proxy's nginx. */
export function openAdvisoriesFor(status: CveStatus | null, components: string[]): CveAdvisory[] {
  return (status?.report?.advisories ?? []).filter(
    (a) => components.includes(a.component) && a.status !== 'fixed'
  )
}

const STATUS: Record<CveStatusName, { label: string; className: string }> = {
  vulnerable: { label: 'Exposed', className: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20' },
  unknown: { label: 'Unknown', className: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20' },
  mitigated: { label: 'Mitigated', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20' },
  not_exposed: { label: 'Not exposed', className: 'bg-muted text-muted-foreground border-border' },
  fixed: { label: 'Fixed', className: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20' },
}

const SEVERITY: Record<CveAdvisory['severity'], string> = {
  critical: 'text-red-600 dark:text-red-400 border-red-500/30',
  high: 'text-orange-700 dark:text-orange-400 border-orange-500/30',
  medium: 'text-yellow-700 dark:text-yellow-400 border-yellow-500/30',
  low: 'text-muted-foreground',
}

const STALE_AFTER_MS = 2 * 24 * 60 * 60 * 1000

function ageOf(iso?: string): { text: string; stale: boolean } | null {
  if (!iso) return null
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return null
  return { text: when.toLocaleString(), stale: Date.now() - when.getTime() > STALE_AFTER_MS }
}

export function SecurityAdvisories({
  status,
  onChanged,
}: {
  status: CveStatus | null
  onChanged: () => void
}) {
  const confirm = useConfirm()
  const [busy, setBusy] = useState<string | null>(null)

  const report = status?.report ?? null
  const advisories = report?.advisories ?? []
  const open = advisories.filter((a) => a.status !== 'fixed')
  const fixed = advisories.filter((a) => a.status === 'fixed')
  const exposed = advisories.filter((a) => a.status === 'vulnerable').length
  const age = ageOf(report?.meta.checked_at)

  const toggle = async (name: string, on: boolean) => {
    const covered = advisories.filter((a) => a.mitigations.includes(name) && a.status !== 'fixed').map((a) => a.id)
    const ok = await confirm(
      on
        ? {
            title: `Turn on ${name}?`,
            description: `${status?.available_mitigations[name] ?? name}.\n\nThe proxy config is regenerated and reloaded; hosts keep their own settings.`,
            confirmLabel: 'Turn on',
          }
        : {
            title: `Turn off ${name}?`,
            description:
              covered.length > 0
                ? `${covered.join(', ')} will be exposed again until a fixed version is running.\n\nThe upgrade script turns it back on the next time it runs, while they are open.`
                : 'Nothing it covers is open now, so this only removes the mitigation.',
            confirmLabel: 'Turn off',
            variant: 'destructive',
          }
    )
    if (!ok) return
    setBusy(name)
    try {
      await api.put(`/api/updates/cve/mitigations/${name}`, { active: on, cves: covered })
      toastSuccess(`${name} turned ${on ? 'on' : 'off'}`)
      onChanged()
    } catch (err: any) {
      toastError(err?.response?.data?.detail || `Couldn't turn ${name} ${on ? 'on' : 'off'}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
            <ShieldAlert className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Security Advisories</h2>
            <p className="text-sm text-muted-foreground">
              CVEs in <code className="font-mono text-xs">cve/</code>, checked by the upgrade script against the running proxy
            </p>
          </div>
        </div>
        {report &&
          (exposed > 0 ? (
            <Badge variant="destructive">
              <AlertTriangle />
              {exposed} exposed
            </Badge>
          ) : (
            <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1 shrink-0">
              <CheckCircle className="h-4 w-4" />
              Nothing exposed
            </span>
          ))}
      </div>

      {status?.error && (
        <p className="text-sm text-yellow-700 dark:text-yellow-400 flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4" />
          {status.error}
        </p>
      )}

      {!report ? (
        <p className="text-sm text-muted-foreground">
          Not checked yet. Run <code className="font-mono text-xs">./upgradeGhostwireProxy.sh</code> on the server: every
          run checks the proxy against the advisories and records what it finds here.
        </p>
      ) : (
        <div className="space-y-3">
          {age && (
            <p className={`text-xs ${age.stale ? 'text-yellow-700 dark:text-yellow-400' : 'text-muted-foreground'}`}>
              Last checked {age.text}
              {report.meta.version ? ` on v${report.meta.version}` : ''}.
              {age.stale && ' That is over two days ago: is the upgrade script still run from cron?'}
            </p>
          )}

          {open.map((a) => (
            <div key={a.id} className="p-4 rounded-lg border border-border space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={`https://www.cve.org/CVERecord?id=${a.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono font-medium text-brand hover:underline inline-flex items-center gap-1"
                >
                  {a.id}
                  <ExternalLink className="h-3 w-3" />
                </a>
                <Badge variant="outline" className={`capitalize ${SEVERITY[a.severity]}`}>
                  {a.severity}
                </Badge>
                <Badge variant="outline" className={STATUS[a.status].className}>
                  {STATUS[a.status].label}
                </Badge>
                {a.aliases.map((alias) => (
                  <span key={alias} className="text-xs text-muted-foreground">
                    {alias}
                  </span>
                ))}
              </div>
              <p className="text-sm font-medium">{a.title}</p>
              {a.reasons.length > 0 && (
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  {a.reasons.map((r) => (
                    <li key={r}>• {r}</li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted-foreground">
                Running {a.component} {a.version ?? 'unknown'}; fixed in {a.fixed_in.join(', ') || 'no release yet'}.
                {a.fix_note ? ` ${a.fix_note}` : ''}
              </p>
            </div>
          ))}

          {fixed.length > 0 && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <CheckCircle className="h-3 w-3 text-green-600 dark:text-green-400" />
              Fixed in the running version: {fixed.map((a) => a.id).join(', ')}
            </p>
          )}
        </div>
      )}

      {status && Object.keys(status.available_mitigations).length > 0 && (
        <div className="mt-6 pt-4 border-t border-border space-y-3">
          <div>
            <p className="text-sm font-medium">Mitigations</p>
            <p className="text-xs text-muted-foreground">
              The upgrade script turns these on while an advisory is open and off once it is fixed. The switch is live;
              the statuses above are as of the last check.
            </p>
          </div>
          {Object.entries(status.available_mitigations).map(([name, describe]) => {
            const on = status.active_mitigations.includes(name)
            return (
              <div key={name} className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-mono">{name}</p>
                  <p className="text-xs text-muted-foreground">{describe}</p>
                </div>
                <div className="flex items-center gap-2">
                  {busy === name && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                  <Switch
                    checked={on}
                    disabled={busy !== null}
                    onCheckedChange={(v) => void toggle(name, v)}
                    aria-label={`${name} mitigation`}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
