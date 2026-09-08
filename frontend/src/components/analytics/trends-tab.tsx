'use client'

import { useMemo } from 'react'
import { TrendingUp, Users, ShieldAlert, Gauge, Globe } from 'lucide-react'
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

const TOOLTIP_STYLE = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '8px',
} as const

export interface TrendPoint {
  date: string
  requests: number
  unique_visitors: number
  blocked: number
  threats: number
  bytes_sent: number
  bytes_received: number
  avg_response_time: number | null
}

export interface TrendsData {
  days: number
  totals: TrendPoint[]
  by_host: Array<{ host_id: string; host_name: string; points: TrendPoint[] }>
  top_countries: Array<{ country: string; requests: number; blocked: number }>
}

interface TrendsTabProps {
  data: TrendsData | null
  isLoading: boolean
  formatNumber: (n: number) => string
  formatBytes: (n: number) => string
}

/** Shorter axis labels: "2026-09-08" is too wide to repeat across 90 ticks. */
function shortDate(date: string) {
  const [, m, d] = date.split('-')
  return m && d ? `${d}/${m}` : date
}

export function TrendsTab({ data, isLoading, formatNumber, formatBytes }: TrendsTabProps) {
  // Merge each host's series into one row per date so Recharts can draw them
  // as comparable lines rather than separate charts.
  const perHostSeries = useMemo(() => {
    if (!data) return { rows: [], hosts: [] as Array<{ id: string; name: string }> }
    const byDate = new Map<string, Record<string, string | number>>()
    for (const host of data.by_host) {
      for (const p of host.points) {
        const row = byDate.get(p.date) ?? { date: p.date }
        row[host.host_id] = p.requests
        byDate.set(p.date, row)
      }
    }
    return {
      rows: [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date))),
      hosts: data.by_host.map((h) => ({ id: h.host_id, name: h.host_name })),
    }
  }, [data])

  if (isLoading) {
    return <div className="animate-pulse text-muted-foreground py-12 text-center">Loading trends…</div>
  }

  if (!data || data.totals.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center">
        <TrendingUp className="h-10 w-10 mx-auto mb-3 opacity-30" />
        <p className="font-medium">No trend data yet</p>
        <p className="text-sm text-muted-foreground mt-1">
          Daily rollups are written hourly, just before old traffic is pruned.
          Trends appear once the first rollup has run.
        </p>
      </div>
    )
  }

  const totalRequests = data.totals.reduce((sum, p) => sum + p.requests, 0)
  const peakVisitors = data.totals.reduce((max, p) => Math.max(max, p.unique_visitors), 0)
  const totalThreats = data.totals.reduce((sum, p) => sum + p.threats, 0)
  const rtPoints = data.totals.filter((p) => p.avg_response_time != null)
  const avgRt = rtPoints.length
    ? Math.round(rtPoints.reduce((s, p) => s + (p.avg_response_time ?? 0), 0) / rtPoints.length)
    : null

  return (
    <div className="space-y-6">
      {/* Summary across the retained rollup window */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: `Requests (${data.days}d)`, value: formatNumber(totalRequests), icon: TrendingUp },
          { label: 'Peak daily visitors', value: formatNumber(peakVisitors), icon: Users },
          { label: `Threats (${data.days}d)`, value: formatNumber(totalThreats), icon: ShieldAlert },
          { label: 'Avg response', value: avgRt == null ? '—' : `${avgRt}ms`, icon: Gauge },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <Icon className="h-4 w-4" />
              <span className="text-xs uppercase tracking-wider">{label}</span>
            </div>
            <p className="text-2xl font-semibold font-mono">{value}</p>
          </div>
        ))}
      </div>

      {/* Requests vs unique visitors */}
      <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
        <h3 className="font-semibold mb-1">Requests and unique visitors</h3>
        <p className="text-xs text-muted-foreground mb-4">
          From daily rollups, so this reaches back further than the traffic-log
          retention window.
        </p>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data.totals}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="date" tickFormatter={shortDate} stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <YAxis yAxisId="left" stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <YAxis yAxisId="right" orientation="right" stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend />
            <Area yAxisId="left" type="monotone" dataKey="requests" name="Requests"
                  stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.2} />
            <Area yAxisId="right" type="monotone" dataKey="unique_visitors" name="Unique visitors"
                  stroke={COLORS[1]} fill={COLORS[1]} fillOpacity={0.2} />
            <Area yAxisId="left" type="monotone" dataKey="bot_requests" name="Bot requests"
                  stroke={COLORS[5]} fill={COLORS[5]} fillOpacity={0.15} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Per-host comparison */}
      <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
        <h3 className="font-semibold mb-1">Requests by host</h3>
        <p className="text-xs text-muted-foreground mb-4">
          Top 10 hosts. Fleet-wide averages hide a single site misbehaving.
        </p>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={perHostSeries.rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="date" tickFormatter={shortDate} stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend />
            {perHostSeries.hosts.map((h, i) => (
              <Line key={h.id} type="monotone" dataKey={h.id} name={h.name}
                    stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={2} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Security over time */}
        <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
          <h3 className="font-semibold mb-4">Blocked requests and threats</h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={data.totals}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke="hsl(var(--muted-foreground))" fontSize={12} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
              <Area type="monotone" dataKey="blocked" name="Blocked" stackId="1"
                    stroke={COLORS[2]} fill={COLORS[2]} fillOpacity={0.3} />
              <Area type="monotone" dataKey="threats" name="Threats" stackId="1"
                    stroke={COLORS[3]} fill={COLORS[3]} fillOpacity={0.3} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Bandwidth */}
        <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
          <h3 className="font-semibold mb-4">Bandwidth</h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={data.totals}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke="hsl(var(--muted-foreground))" fontSize={12} />
              <YAxis tickFormatter={(v) => formatBytes(Number(v))} stroke="hsl(var(--muted-foreground))" fontSize={12} width={70} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => formatBytes(Number(v))} />
              <Legend />
              <Area type="monotone" dataKey="bytes_sent" name="Sent" stackId="1"
                    stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.3} />
              <Area type="monotone" dataKey="bytes_received" name="Received" stackId="1"
                    stroke={COLORS[6]} fill={COLORS[6]} fillOpacity={0.3} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Response time trend */}
      <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
        <h3 className="font-semibold mb-1">Average response time</h3>
        <p className="text-xs text-muted-foreground mb-4">
          Request-weighted across hosts. An average hides slow outliers — a
          percentile would show them, and needs a column on the rollup.
        </p>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data.totals}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="date" tickFormatter={shortDate} stroke="hsl(var(--muted-foreground))" fontSize={12} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} unit="ms" />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Line type="monotone" dataKey="avg_response_time" name="Avg response"
                  stroke={COLORS[4]} dot={false} strokeWidth={2} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Geo */}
      {data.top_countries.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
          <div className="flex items-center gap-2 mb-4">
            <Globe className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Requests by country</h3>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.top_countries}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="country" stroke="hsl(var(--muted-foreground))" fontSize={12} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend />
              <Bar dataKey="requests" name="Requests" fill={COLORS[0]} radius={[4, 4, 0, 0]} />
              <Bar dataKey="blocked" name="Blocked" fill={COLORS[3]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default TrendsTab
