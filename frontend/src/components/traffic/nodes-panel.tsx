'use client'

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, Shuffle } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { useTrafficNodes, type TrafficFilters } from '@/lib/queries/traffic'
import { Panel } from './traffic-panels'
import { formatCount, formatMs, formatPct } from './format'

// Distinct, readable on light and dark backgrounds.
const NODE_COLOURS = ['#0ea5e9', '#a855f7', '#22c55e', '#f59e0b', '#ef4444', '#14b8a6', '#ec4899', '#6366f1', '#94a3b8']

/** How a load-balanced host's (or one machine's) traffic spread over its upstream nodes. */
export function NodesPanel({ filters, onNode }: { filters: TrafficFilters; onNode?: (node: string) => void }) {
  const { data, isPending } = useTrafficNodes(filters)
  if (isPending || !data) {
    return (
      <Panel title="Nodes">
        <Skeleton className="h-48 w-full" />
      </Panel>
    )
  }
  const nodes = data.nodes.filter((n) => n.node)
  if (!nodes.length) return null
  const chart = data.timeseries.map((p) => ({ t: p.t, ...p.values }))
  const fmtTick = (iso: string) => {
    const d = new Date(iso)
    return data.stride_seconds < 86400
      ? d.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString([], { day: 'numeric', month: 'short' })
  }
  return (
    <Panel
      title={`Nodes (${nodes.length})`}
      action={
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Shuffle className="h-3.5 w-3.5" />
          {formatCount(data.failovers.total)} failover{data.failovers.total === 1 ? '' : 's'}
        </span>
      }
    >
      <div className="space-y-4">
        {nodes.length > 1 && (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chart} margin={{ left: 0, right: 8, top: 4 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
              <XAxis dataKey="t" tickFormatter={fmtTick} tick={{ fontSize: 11 }} minTickGap={24} />
              <YAxis tickFormatter={(v) => formatCount(v)} tick={{ fontSize: 11 }} width={44} />
              <Tooltip
                contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }}
                labelFormatter={(iso) => new Date(String(iso)).toLocaleString()}
              />
              {data.series_nodes.map((n, i) => (
                <Area
                  key={n}
                  type="monotone"
                  dataKey={n}
                  name={n}
                  stackId="nodes"
                  stroke={NODE_COLOURS[i % NODE_COLOURS.length]}
                  fill={NODE_COLOURS[i % NODE_COLOURS.length]}
                  fillOpacity={0.35}
                  isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        )}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Node</TableHead>
                <TableHead className="text-right">Share</TableHead>
                <TableHead className="text-right">Requests</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="hidden text-right md:table-cell">p50 / p95</TableHead>
                <TableHead className="hidden text-right md:table-cell" title="Answered after another node failed / failed then answered elsewhere">
                  Failover in / out
                </TableHead>
                <TableHead className="hidden lg:table-cell">Health</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {nodes.map((n) => {
                const colour = NODE_COLOURS[data.series_nodes.indexOf(n.node)] ?? NODE_COLOURS[NODE_COLOURS.length - 1]
                return (
                  <TableRow key={n.node} className={cn(onNode && 'cursor-pointer')} onClick={() => onNode?.(n.node)}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colour }} />
                        <span className="font-mono text-sm">{n.node}</span>
                      </div>
                      {n.label && <div className="pl-[18px] text-xs text-muted-foreground">{n.label}</div>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatPct(n.share)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(n.requests)}</TableCell>
                    <TableCell
                      className={cn(
                        'text-right tabular-nums',
                        n.server_error_rate >= 5 ? 'text-red-600 dark:text-red-400' : n.error_rate >= 10 ? 'text-amber-700 dark:text-amber-400' : ''
                      )}
                    >
                      {formatPct(n.error_rate)}
                    </TableCell>
                    <TableCell className="hidden text-right text-sm md:table-cell">
                      {formatMs(n.p50)} / {formatMs(n.p95)}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums md:table-cell">
                      {formatCount(n.failovers_in)} / {formatCount(n.failovers_out)}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {n.health.length ? (
                        n.health.map((h, i) => (
                          <span
                            key={i}
                            title={h.error ?? undefined}
                            className={cn(
                              'mr-1 rounded px-2 py-0.5 text-xs font-medium',
                              h.down || !h.enabled
                                ? 'bg-muted text-muted-foreground'
                                : h.status === 'up'
                                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                                  : h.status === 'down'
                                    ? 'bg-red-500/10 text-red-600 dark:text-red-400'
                                    : 'bg-muted text-muted-foreground'
                            )}
                          >
                            {!h.enabled ? 'disabled' : h.down ? 'maintenance' : (h.status ?? 'unknown')}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">not checked</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
        {data.failovers.pairs.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Failed over (from → to)</p>
            <ul className="space-y-1 text-sm">
              {data.failovers.pairs.slice(0, 8).map((p) => (
                <li key={`${p.from}>${p.to}`} className="flex items-center gap-2 font-mono text-xs">
                  {p.from}
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  {p.to}
                  <span className="ml-auto text-muted-foreground">{formatCount(p.requests)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  )
}
