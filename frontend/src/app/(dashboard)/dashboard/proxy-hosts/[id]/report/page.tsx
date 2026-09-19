'use client'

import { useEffect, useState, use } from 'react'
import Link from 'next/link'
import {
  ArrowLeft,
  Loader2,
  Printer,
  Mail,
  AlertCircle,
  ShieldAlert,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import dynamic from 'next/dynamic'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import api from '@/lib/api'
import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '@/components/ui/modal'
import { PageHeader } from '@/components/layout/page-header'
import { FileBarChart as HeaderIcon } from 'lucide-react'

// Leaflet touches `window` on import, so it cannot be server-rendered.
const GeoHeatmap = dynamic(() => import('@/components/geo-heatmap'), {
  ssr: false,
  loading: () => (
    <div className="h-[320px] flex items-center justify-center text-sm text-muted-foreground">
      Loading map…
    </div>
  ),
})

// Reuses the palette the analytics tabs already use, so a status colour means
// the same thing on every page. These are status colours, not categorical ones
// — they are never recycled for an unrelated series.
const STATUS_COLORS: Record<string, string> = {
  '2xx': '#10b981',
  '3xx': '#3b82f6',
  '4xx': '#f59e0b',
  '5xx': '#ef4444',
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
  unknown: '#6b7280',
}

// Two series, validated for colour-vision deficiency separation
// (ΔE 35.2 normal / 26.7 protan) rather than eyeballed.
const SERIES_REQUESTS = '#3b82f6'
const SERIES_ERRORS = '#ef4444'

const tooltipStyle = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '8px',
  fontSize: '12px',
}

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

/** Requests over time, with errors overlaid.
 *
 *  A line over time is the right form for change-over-time, and it carries a
 *  crosshair tooltip so a reader can interrogate any point rather than guess
 *  from the shape. Two series, so the legend is always present — identity is
 *  never carried by colour alone.
 */
function TrafficChart({
  points,
  bucket,
}: {
  points: { timestamp: string; requests: number; errors: number; unique_visitors: number }[]
  bucket: string
}) {
  if (points.length < 2) {
    return <p className="text-sm text-muted-foreground">Not enough data to plot yet.</p>
  }

  const data = points.map((p) => ({
    ...p,
    label:
      bucket === 'hour'
        ? String(p.timestamp || '').slice(11, 16)
        : String(p.timestamp || '').slice(5, 10),
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="reqFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES_REQUESTS} stopOpacity={0.35} />
            <stop offset="100%" stopColor={SERIES_REQUESTS} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
        <YAxis tick={{ fontSize: 11 }} width={48} />
        <RTooltip
          contentStyle={tooltipStyle}
          formatter={(v: number, n: string) => [Number(v).toLocaleString(), n]}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area
          type="monotone"
          dataKey="requests"
          name="Requests"
          stroke={SERIES_REQUESTS}
          strokeWidth={2}
          fill="url(#reqFill)"
        />
        <Area
          type="monotone"
          dataKey="errors"
          name="Errors"
          stroke={SERIES_ERRORS}
          strokeWidth={2}
          fill="none"
          strokeDasharray="4 3"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Horizontal magnitude comparison for a labelled category. */
function CategoryBars({
  items,
  colorFor,
}: {
  items: { name: string; requests: number; percent: number }[]
  colorFor?: (name: string) => string
}) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No data.</p>

  const data = items.slice(0, 8)
  const height = Math.max(140, data.length * 30)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={92} />
        <RTooltip
          contentStyle={tooltipStyle}
          formatter={(v: number) => [Number(v).toLocaleString(), 'Requests']}
        />
        <Bar dataKey="requests" radius={[0, 4, 4, 0]} maxBarSize={18}>
          {data.map((d) => (
            <Cell key={d.name} fill={colorFor ? colorFor(d.name) : SERIES_REQUESTS} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
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

  // GeoHeatmap works in days; translate the report's period so the map covers
  // the same window as everything else on the page.
  const geoDays =
    { '24h': 1, '7d': 7, '30d': 30, '90d': 90, '365d': 365 }[period] ?? 30

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
      <div className="space-y-2">
      <Link
        href="/dashboard/proxy-hosts"
        className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 mb-1 print:hidden"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to hosts
      </Link>
        <PageHeader
          icon={HeaderIcon}
          title={report.host?.primary_domain}
          description={
            <>
              Traffic report · {PERIODS.find((p) => p.value === period)?.label} ·
              generated {String(report.meta?.generated_at || '').slice(0, 16).replace('T', ' ')} UTC
            </>
          }
          actions={
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
          }
        />
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
        <TrafficChart
          points={report.timeseries?.points || []}
          bucket={report.timeseries?.bucket || 'day'}
        />
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
          <CategoryBars items={clients.browsers || []} />
        </Section>

        <Section title="Devices">
          <CategoryBars items={clients.devices || []} />
        </Section>

        <Section title="Operating systems">
          <CategoryBars items={clients.operating_systems || []} />
        </Section>

        <Section title="Bots and automation">
          <CategoryBars items={clients.bots || []} />
        </Section>

        {/* Full width — a world map in a half-width column is unreadable. */}
        <div className="lg:col-span-2">
        <Section title="Where visitors came from" subtitle="Country and city origins for this host">
          <div className="h-[340px] rounded-lg overflow-hidden border border-border mb-4 print:hidden">
            <GeoHeatmap proxyHostId={id} days={geoDays} showThreats />
          </div>
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
        </div>

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
              <h3 className="text-sm font-medium mb-2">By severity</h3>
              <CategoryBars
                items={(sec.by_severity || []).map((x: any) => ({
                  name: x.severity,
                  requests: x.events,
                  percent: 0,
                }))}
                colorFor={(n) => SEVERITY_COLORS[n] || SEVERITY_COLORS.unknown}
              />
            </div>
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
