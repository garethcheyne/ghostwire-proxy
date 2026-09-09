'use client'

import { useEffect, useState, use } from 'react'
import Link from 'next/link'
import {
  ArrowLeft,
  Loader2,
  Printer,
  Mail,
  AlertCircle,
  Globe,
  ShieldAlert,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import api from '@/lib/api'
import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '@/components/ui/modal'

const PERIODS = [
  { value: '24h', label: '24 hours' },
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: '365d', label: '12 months' },
]

function bytes(n?: number | null) {
  let v = Number(n || 0)
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return i === 0 ? `${v.toFixed(0)} B` : `${v.toFixed(1)} ${units[i]}`
}

function num(n?: number | null) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString()
}

function ms(n?: number | null) {
  if (n === null || n === undefined) return '—'
  return `${Math.round(Number(n)).toLocaleString()} ms`
}

function Stat({
  label,
  value,
  change,
  sub,
}: {
  label: string
  value: string
  change?: number | null
  sub?: string
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold mt-1 flex items-baseline gap-2">
        {value}
        {change !== null && change !== undefined && (
          <span
            className={`text-xs font-medium flex items-center gap-0.5 ${
              change >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
            }`}
          >
            {change >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {Math.abs(change).toFixed(1)}%
          </span>
        )}
      </p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  )
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 break-inside-avoid">
      <h2 className="text-base font-semibold">{title}</h2>
      {subtitle && <p className="text-xs text-muted-foreground mt-0.5 mb-3">{subtitle}</p>}
      <div className={subtitle ? '' : 'mt-3'}>{children}</div>
    </section>
  )
}

/** A compact table that scrolls horizontally on small screens rather than
 *  pushing the page wide. */
function Table({
  headers,
  rows,
  align = [],
  empty = 'No data for this period.',
}: {
  headers: string[]
  rows: React.ReactNode[][]
  align?: ('left' | 'right')[]
  empty?: string
}) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">{empty}</p>
  }
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm min-w-[380px]">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h, i) => (
              <th
                key={h}
                className={`py-2 px-1 text-xs uppercase tracking-wide text-muted-foreground font-medium ${
                  align[i] === 'right' ? 'text-right' : 'text-left'
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={`py-1.5 px-1 ${align[j] === 'right' ? 'text-right tabular-nums' : ''}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Horizontal share bar — cheaper to read than a pie, and prints legibly. */
function ShareRows({ items }: { items: { name: string; percent: number; requests: number }[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No data.</p>
  return (
    <div className="space-y-2">
      {items.map((it) => (
        <div key={it.name}>
          <div className="flex justify-between text-sm mb-0.5">
            <span className="truncate pr-2">{it.name}</span>
            <span className="text-muted-foreground tabular-nums flex-shrink-0">
              {it.percent}% · {num(it.requests)}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary rounded-full"
              style={{ width: `${Math.min(it.percent, 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Requests over time. Inline SVG so it prints and needs no chart library. */
function Sparkline({ points }: { points: { timestamp: string; requests: number; errors: number }[] }) {
  if (points.length < 2) {
    return <p className="text-sm text-muted-foreground">Not enough data to plot.</p>
  }
  const w = 800
  const h = 140
  const max = Math.max(...points.map((p) => p.requests), 1)
  const step = w / (points.length - 1)

  const line = points.map((p, i) => `${i * step},${h - (p.requests / max) * h}`).join(' ')
  const area = `0,${h} ${line} ${w},${h}`
  const errLine = points.map((p, i) => `${i * step},${h - (p.errors / max) * h}`).join(' ')

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-32 min-w-[320px]" preserveAspectRatio="none">
        <polygon points={area} className="fill-primary/15" />
        <polyline points={line} className="fill-none stroke-primary" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        <polyline
          points={errLine}
          className="fill-none stroke-red-500"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground mt-1">
        <span>{points[0].timestamp?.slice(0, 10)}</span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-primary" /> requests
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-red-500" /> errors
          </span>
        </span>
        <span>{points[points.length - 1].timestamp?.slice(0, 10)}</span>
      </div>
    </div>
  )
}

export default function HostReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)

  const [period, setPeriod] = useState('30d')
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [emailOpen, setEmailOpen] = useState(false)
  const [recipients, setRecipients] = useState('')
  const [sending, setSending] = useState(false)
  const [emailNotice, setEmailNotice] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api
      .get(`/api/reports/hosts/${id}`, { params: { period } })
      .then(({ data }) => {
        if (!cancelled) setReport(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.response?.data?.detail || 'Could not load the report')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, period])

  const sendEmail = async () => {
    setSending(true)
    setEmailNotice('')
    try {
      const list = recipients
        .split(',')
        .map((r) => r.trim())
        .filter(Boolean)
      await api.post(`/api/reports/hosts/${id}/send`, { recipients: list }, { params: { period } })
      setEmailNotice(`Sent to ${list.length} recipient${list.length === 1 ? '' : 's'}.`)
    } catch (e: any) {
      setEmailNotice(e.response?.data?.detail || 'Could not send the report')
    } finally {
      setSending(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="flex items-center gap-2 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive">
        <AlertCircle className="h-4 w-4" />
        <span>{error || 'No report available'}</span>
      </div>
    )
  }

  const ov = report.overview || {}
  const sec = report.security || {}
  const life = report.lifetime || {}
  const paths = report.paths || {}
  const clients = report.clients || {}
  const geo = report.geography || {}
  const refs = report.referrers || {}
  const resp = report.responses || {}
  const visitors = report.visitors || {}
  const fam = resp.status_families || {}

  return (
    <div className="space-y-5 print:space-y-3">
      {/* Print rules: drop the chrome, let sections break cleanly across pages. */}
      <style jsx global>{`
        @media print {
          nav,
          aside,
          header,
          .print\\:hidden {
            display: none !important;
          }
          main {
            padding: 0 !important;
          }
          section {
            break-inside: avoid;
            border-color: #ddd !important;
          }
          body {
            background: #fff !important;
          }
          @page {
            margin: 14mm;
          }
        }
      `}</style>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            href="/dashboard/proxy-hosts"
            className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 mb-1 print:hidden"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to hosts
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Globe className="h-6 w-6 text-primary print:hidden" />
            {report.host?.primary_domain}
          </h1>
          <p className="text-sm text-muted-foreground">
            Traffic report · {PERIODS.find((p) => p.value === period)?.label} ·
            generated {String(report.meta?.generated_at || '').slice(0, 16).replace('T', ' ')} UTC
          </p>
        </div>

        <div className="flex items-center gap-2 print:hidden">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => setEmailOpen(true)}
            className="h-9 px-3 rounded-md border border-input text-sm font-medium hover:bg-accent flex items-center gap-1.5"
          >
            <Mail className="h-3.5 w-3.5" />
            Email
          </button>
          <button
            onClick={() => window.print()}
            className="h-9 px-3 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 flex items-center gap-1.5"
          >
            <Printer className="h-3.5 w-3.5" />
            Print / PDF
          </button>
        </div>
      </div>

      {/* Headline */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Stat label="Requests" value={num(ov.total_requests)} change={ov.requests_change_percent} />
        <Stat label="Unique visitors" value={num(ov.unique_visitors)} change={ov.visitors_change_percent} />
        <Stat label="Data sent" value={bytes(ov.bytes_sent)} sub={`${bytes(ov.bytes_received)} received`} />
        <Stat label="Error rate" value={`${ov.error_rate ?? 0}%`} sub={`${num(ov.error_count)} errors`} />
        <Stat label="Bot traffic" value={`${ov.bot_percent ?? 0}%`} sub={`${num(ov.human_requests)} human requests`} />
        <Stat label="Median response" value={ms(ov.p50_response_time_ms)} />
        <Stat label="p95 response" value={ms(ov.p95_response_time_ms)} sub={`p99 ${ms(ov.p99_response_time_ms)}`} />
        <Stat
          label="Security events"
          value={num(sec.total_events)}
          change={sec.events_change_percent}
          sub={`${num(sec.unique_attackers)} unique attackers`}
        />
      </div>

      <Section title="Traffic over time" subtitle={`Grouped by ${report.timeseries?.bucket || 'day'}`}>
        <Sparkline points={report.timeseries?.points || []} />
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Most requested paths">
          <Table
            headers={['Path', 'Requests', 'Visitors', 'Avg', 'Errors']}
            align={['left', 'right', 'right', 'right', 'right']}
            rows={(paths.top_paths || []).map((p: any) => [
              <span key="u" className="font-mono text-xs break-all">{p.uri}</span>,
              num(p.requests),
              num(p.unique_visitors),
              ms(p.avg_response_time_ms),
              p.errors ? <span className="text-red-600 dark:text-red-400">{num(p.errors)}</span> : '0',
            ])}
          />
        </Section>

        <Section
          title="Slowest paths"
          subtitle="Ranked by p95, and only where there were at least 10 requests — a mean hides the tail"
        >
          <Table
            headers={['Path', 'Requests', 'p95', 'Avg']}
            align={['left', 'right', 'right', 'right']}
            rows={(paths.slowest_paths || []).map((p: any) => [
              <span key="u" className="font-mono text-xs break-all">{p.uri}</span>,
              num(p.requests),
              ms(p.p95_response_time_ms),
              ms(p.avg_response_time_ms),
            ])}
          />
        </Section>

        <Section title="Browsers" subtitle={clients.sampled ? `Sampled from the most recent ${num(clients.sample_size)} of ${num(clients.total_in_period)} requests` : undefined}>
          <ShareRows items={clients.browsers || []} />
        </Section>

        <Section title="Devices">
          <ShareRows items={clients.devices || []} />
        </Section>

        <Section title="Operating systems">
          <ShareRows items={clients.operating_systems || []} />
        </Section>

        <Section title="Bots and automation">
          <ShareRows items={clients.bots || []} />
        </Section>

        <Section title="Countries">
          <Table
            headers={['Country', 'Requests', 'Visitors', 'Data']}
            align={['left', 'right', 'right', 'right']}
            rows={(geo.countries || []).map((c: any) => [
              `${c.country_name} (${c.country_code})`,
              num(c.requests),
              num(c.unique_visitors),
              bytes(c.bytes_sent),
            ])}
          />
          {geo.unlocated_requests > 0 && (
            <p className="text-xs text-muted-foreground mt-2">
              {num(geo.unlocated_requests)} requests could not be geolocated.
            </p>
          )}
        </Section>

        <Section title="Referring domains" subtitle={`${num(refs.direct_requests)} requests arrived directly (no referrer)`}>
          <Table
            headers={['Domain', 'Requests']}
            align={['left', 'right']}
            rows={(refs.referring_domains || []).map((r: any) => [r.domain, num(r.requests)])}
          />
        </Section>

        <Section title="Response codes">
          {/* Two columns on a phone: at four, a six-figure count overflows
              its ~64px tile. */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
            {[
              ['2xx', fam['2xx'], 'text-emerald-600 dark:text-emerald-400'],
              ['3xx', fam['3xx'], 'text-blue-600 dark:text-blue-400'],
              ['4xx', fam['4xx'], 'text-amber-600 dark:text-amber-400'],
              ['5xx', fam['5xx'], 'text-red-600 dark:text-red-400'],
            ].map(([label, value, cls]) => (
              <div key={label as string} className="rounded-lg border border-border p-2 text-center">
                <p className={`text-base sm:text-lg font-semibold tabular-nums ${cls}`}>{num(value as number)}</p>
                <p className="text-xs text-muted-foreground">{label as string}</p>
              </div>
            ))}
          </div>
          <Table
            headers={['Status', 'Requests', 'Share']}
            align={['left', 'right', 'right']}
            rows={(resp.status_codes || []).slice(0, 10).map((s: any) => [
              s.status,
              num(s.requests),
              `${s.percent}%`,
            ])}
          />
        </Section>

        <Section title="Top visitors">
          <Table
            headers={['IP', 'Requests', 'Country', 'Data']}
            align={['left', 'right', 'left', 'right']}
            rows={(visitors.top_ips || []).slice(0, 15).map((v: any) => [
              <span key="i" className="font-mono text-xs">{v.client_ip}</span>,
              num(v.requests),
              v.country_name || '—',
              bytes(v.bytes_sent),
            ])}
          />
        </Section>

        {(visitors.authenticated_users || []).length > 0 && (
          <Section title="Signed-in users" subtitle="Visitors identified through an auth wall">
            <Table
              headers={['User', 'Requests', 'IPs', 'Last seen']}
              align={['left', 'right', 'right', 'left']}
              rows={(visitors.authenticated_users || []).map((u: any) => [
                u.username,
                num(u.requests),
                num(u.distinct_ips),
                String(u.last_seen || '').slice(0, 16).replace('T', ' '),
              ])}
            />
          </Section>
        )}
      </div>

      {/* Security */}
      <Section
        title="Security"
        subtitle={`${num(sec.total_events)} events from ${num(sec.unique_attackers)} unique addresses · ${sec.blocked_percent ?? 0}% blocked`}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div>
            <h3 className="text-sm font-medium mb-2 flex items-center gap-1.5">
              <ShieldAlert className="h-4 w-4 text-amber-500" />
              Top attackers
            </h3>
            <Table
              headers={['IP', 'Events', 'Type', 'Blocked']}
              align={['left', 'right', 'left', 'right']}
              rows={(sec.top_attackers || []).slice(0, 15).map((a: any) => [
                <span key="i" className="font-mono text-xs">{a.client_ip}</span>,
                num(a.events),
                a.category || '—',
                num(a.blocked),
              ])}
              empty="No attacks recorded in this period."
            />
          </div>

          <div className="space-y-5">
            <div>
              <h3 className="text-sm font-medium mb-2">Attack types</h3>
              <Table
                headers={['Category', 'Events']}
                align={['left', 'right']}
                rows={(sec.by_category || []).map((c: any) => [c.category, num(c.events)])}
                empty="None."
              />
            </div>
            <div>
              <h3 className="text-sm font-medium mb-2">Most targeted paths</h3>
              <Table
                headers={['Path', 'Events']}
                align={['left', 'right']}
                rows={(sec.targeted_paths || []).slice(0, 10).map((t: any) => [
                  <span key="u" className="font-mono text-xs break-all">{t.uri}</span>,
                  num(t.events),
                ])}
                empty="None."
              />
            </div>
            <div>
              <h3 className="text-sm font-medium mb-2">Rules triggered</h3>
              <Table
                headers={['Rule', 'Events']}
                align={['left', 'right']}
                rows={(sec.triggered_rules || []).slice(0, 10).map((r: any) => [
                  r.rule_name,
                  num(r.events),
                ])}
                empty="None."
              />
            </div>
          </div>
        </div>
      </Section>

      {/* Lifetime */}
      <Section
        title="Lifetime totals"
        subtitle="From daily rollups, which survive log retention — so these reach further back than the sections above"
      >
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          <Stat label="Total requests" value={num(life.total_requests)} />
          <Stat label="Total threats" value={num(life.total_threats)} />
          <Stat label="Data sent" value={bytes(life.bytes_sent)} />
          <Stat
            label="Days with traffic"
            value={num(life.days_with_traffic)}
            sub={`${num(life.avg_requests_per_day)} req/day average`}
          />
        </div>
        {life.busiest_day && (
          <p className="text-sm text-muted-foreground mt-3">
            Busiest day: <strong>{life.busiest_day.date}</strong> with{' '}
            {num(life.busiest_day.requests)} requests. Peak single-day unique visitors:{' '}
            {num(life.peak_daily_unique_ips)}.
          </p>
        )}
      </Section>

      {/* Email modal */}
      <Modal open={emailOpen} onOpenChange={setEmailOpen} size="md">
        <ModalHeader>
          <ModalTitle>Email this report</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Sends the {PERIODS.find((p) => p.value === period)?.label} report for{' '}
            {report.host?.primary_domain}. Requires an SMTP server under Settings.
          </p>
          <label className="block text-sm font-medium">Recipients (comma separated)</label>
          <input
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            placeholder="owner@example.com, ops@example.com"
            className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
          {emailNotice && <p className="text-sm">{emailNotice}</p>}
        </ModalBody>
        <ModalFooter>
          <button
            onClick={() => setEmailOpen(false)}
            className="h-9 px-4 rounded-md border border-input text-sm font-medium hover:bg-accent"
          >
            Close
          </button>
          <button
            onClick={sendEmail}
            disabled={sending || !recipients.trim()}
            className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1.5"
          >
            {sending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Send
          </button>
        </ModalFooter>
      </Modal>
    </div>
  )
}
