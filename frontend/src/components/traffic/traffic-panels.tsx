'use client'

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { TopItem, TrafficOverview } from '@/lib/queries/traffic'
import { SERIES, formatBytes, formatCount, formatMs, formatPct, statusTone } from './format'

export function Panel({
  title,
  action,
  children,
  className,
}: {
  title: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('rounded-xl border border-border bg-card p-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={cn('mt-1 text-xl font-bold sm:text-2xl', tone)}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

export function SummaryCards({ data, loading }: { data?: TrafficOverview; loading: boolean }) {
  if (!data) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className={cn('h-[92px] rounded-xl', !loading && 'animate-none')} />
        ))}
      </div>
    )
  }
  const t = data.totals
  const errTone =
    t.server_error_rate >= 5
      ? 'text-red-600 dark:text-red-400'
      : t.error_rate >= 10
        ? 'text-amber-700 dark:text-amber-400'
        : undefined
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Stat
        label="Requests"
        value={formatCount(t.requests)}
        sub={t.requests ? `${formatPct((t.bot_requests / t.requests) * 100)} bots` : undefined}
      />
      <Stat
        label="Errors"
        value={formatPct(t.error_rate)}
        tone={errTone}
        sub={`${formatCount(t.errors_5xx)} 5xx · ${formatCount(t.errors_4xx)} 4xx`}
      />
      <Stat
        label="Latency p50 / p95"
        value={
          <>
            {formatMs(t.latency.p50)} <span className="text-muted-foreground">/</span> {formatMs(t.latency.p95)}
          </>
        }
        sub={`p99 ${formatMs(t.latency.p99)} · avg ${formatMs(t.latency.avg)}`}
      />
      <Stat label="Sent" value={formatBytes(t.bytes_sent)} sub="to clients" />
      <Stat label="Received" value={formatBytes(t.bytes_received)} sub="from clients" />
    </div>
  )
}

function tickFormatter(strideSeconds: number) {
  return (iso: string) => {
    const d = new Date(iso)
    if (strideSeconds < 3600) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    if (strideSeconds < 86400) return d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit' })
    return d.toLocaleDateString([], { day: 'numeric', month: 'short' })
  }
}

const tooltipStyle = {
  contentStyle: {
    backgroundColor: 'hsl(var(--card))',
    border: '1px solid hsl(var(--border))',
    borderRadius: 8,
    fontSize: 12,
  },
  labelFormatter: (iso: unknown) => new Date(String(iso)).toLocaleString(),
}

export function RequestsChart({ data }: { data?: TrafficOverview }) {
  if (!data) return <Skeleton className="h-[220px] w-full" />
  const fmt = tickFormatter(data.range.stride_seconds)
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data.timeseries} margin={{ left: 0, right: 8, top: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmt} tick={{ fontSize: 11 }} className="fill-muted-foreground" minTickGap={24} />
        <YAxis tickFormatter={(v) => formatCount(v)} tick={{ fontSize: 11 }} width={44} />
        <Tooltip {...tooltipStyle} />
        {(['s2xx', 's3xx', 's4xx', 's5xx'] as const).map((k) => (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            name={k.slice(1)}
            stackId="1"
            stroke={SERIES[k]}
            fill={SERIES[k]}
            fillOpacity={0.35}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function LatencyChart({ data }: { data?: TrafficOverview }) {
  if (!data) return <Skeleton className="h-[220px] w-full" />
  const fmt = tickFormatter(data.range.stride_seconds)
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data.timeseries} margin={{ left: 0, right: 8, top: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis dataKey="t" tickFormatter={fmt} tick={{ fontSize: 11 }} minTickGap={24} />
        <YAxis tickFormatter={(v) => formatMs(v)} tick={{ fontSize: 11 }} width={56} />
        <Tooltip {...tooltipStyle} formatter={(v) => formatMs(Number(v))} />
        <Line type="monotone" dataKey="p50" name="p50" stroke={SERIES.p50} dot={false} isAnimationActive={false} connectNulls />
        <Line type="monotone" dataKey="p95" name="p95" stroke={SERIES.p95} dot={false} isAnimationActive={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function StatusCodes({ data, onSelect }: { data?: TrafficOverview; onSelect?: (code: number) => void }) {
  if (!data) return <Skeleton className="h-24 w-full" />
  if (!data.status_codes.length) return <p className="text-sm text-muted-foreground">No requests.</p>
  const total = data.totals.requests || 1
  return (
    <div className="flex flex-wrap gap-2">
      {data.status_codes.slice(0, 16).map((c) => (
        <button
          key={c.status}
          type="button"
          onClick={() => onSelect?.(c.status)}
          className={cn('rounded-md px-2 py-1 text-xs font-medium hover:opacity-80', statusTone(c.status))}
          title="Filter to this code"
        >
          {c.status} · {formatCount(c.requests)} ({formatPct((c.requests / total) * 100)})
        </button>
      ))}
    </div>
  )
}

export function TopList({
  items,
  loading,
  onSelect,
  render,
  empty = 'Nothing in this window.',
}: {
  items?: TopItem[]
  loading?: boolean
  onSelect?: (item: TopItem) => void
  render?: (item: TopItem) => React.ReactNode
  empty?: string
}) {
  if (!items) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className={cn('h-6 w-full', !loading && 'animate-none')} />
        ))}
      </div>
    )
  }
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>
  const max = Math.max(...items.map((i) => i.requests), 1)
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.value}>
          <button
            type="button"
            disabled={!onSelect}
            onClick={() => onSelect?.(item)}
            className="group relative flex w-full items-center gap-2 overflow-hidden rounded-md px-2 py-1 text-left text-sm hover:bg-muted disabled:cursor-default disabled:hover:bg-transparent"
          >
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 bg-primary/10"
              style={{ width: `${(item.requests / max) * 100}%` }}
            />
            <span className="relative min-w-0 flex-1 truncate font-mono text-xs" title={item.value}>
              {render ? render(item) : item.value || '(none)'}
            </span>
            {item.errors_5xx ? (
              <span className="relative text-xs text-red-600 dark:text-red-400">{formatCount(item.errors_5xx)} 5xx</span>
            ) : null}
            <span className="relative w-14 text-right text-xs tabular-nums text-muted-foreground">
              {formatCount(item.requests)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
