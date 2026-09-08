'use client'

import { createPortal } from 'react-dom'
import { X, Globe, Server, AlertTriangle, Activity, Clock, Tag } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

import { useIpReport } from '@/lib/queries/known-ips'

interface IpReportProps {
  ip: string | null
  onClose: () => void
  days?: number
}

function bytes(n: number) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(n) / Math.log(1024))
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function when(v: string | null | undefined) {
  return v ? new Date(v).toLocaleString() : '—'
}

/**
 * Everything the proxy knows about one address, across every host.
 *
 * Portalled to document.body: rendered in place, an ancestor's containing block
 * offsets a fixed panel instead of letting it fill the window.
 */
export function IpReport({ ip, onClose, days = 30 }: IpReportProps) {
  const { data, isPending } = useIpReport(ip, days)

  if (!ip || typeof document === 'undefined') return null

  const t = data?.totals
  const errorRate = t && t.requests ? ((t.errors / t.requests) * 100).toFixed(1) : '0.0'

  return createPortal(
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-background border-l shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-background border-b px-4 py-3 flex items-center justify-between z-10">
          <div className="min-w-0">
            <h3 className="font-semibold flex flex-wrap items-center gap-2">
              <Activity className="h-4 w-4 text-blue-500 shrink-0" />
              <span>Traffic report</span>
              <code className="text-sm font-mono" data-private="ip">{ip}</code>
            </h3>
            {data?.known && (
              <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                <Tag className="h-3 w-3" />
                {data.known.label}
                {data.known.category ? ` · ${data.known.category}` : ''}
              </p>
            )}
          </div>
          <button onClick={onClose} aria-label="Close"
            className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        {isPending ? (
          <p className="p-8 text-center text-muted-foreground animate-pulse">Loading report…</p>
        ) : !data ? (
          <p className="p-8 text-center text-muted-foreground">Could not load report.</p>
        ) : (
          <div className="p-4 space-y-5">
            <p className="text-xs text-muted-foreground">Last {data.days} days</p>

            <div className="grid grid-cols-2 gap-3">
              {[
                ['Requests', (t?.requests ?? 0).toLocaleString()],
                ['Hosts touched', String(t?.hosts_touched ?? 0)],
                ['Error rate', `${errorRate}%`],
                ['Data sent', bytes(t?.bytes_sent ?? 0)],
                ['Unique paths', String(t?.unique_paths ?? 0)],
                ['Bot requests', (t?.bot_requests ?? 0).toLocaleString()],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-border p-3">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="text-lg font-semibold font-mono">{value}</p>
                </div>
              ))}
            </div>

            <div className="rounded-lg border border-border p-3 text-sm space-y-1">
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> First seen</span>
                <span>{when(t?.first_seen)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> Last seen</span>
                <span>{when(t?.last_seen)}</span>
              </div>
            </div>

            {data.enrichment && (
              <section>
                <h4 className="font-medium mb-2 flex items-center gap-2"><Globe className="h-4 w-4 text-muted-foreground" /> Network</h4>
                <div className="rounded-lg border border-border p-3 text-sm space-y-1">
                  {[
                    ['Country', data.enrichment.country_name],
                    ['City', data.enrichment.city],
                    ['ISP', data.enrichment.isp],
                    ['Organisation', data.enrichment.org],
                    ['ASN', data.enrichment.asn],
                    ['Reverse DNS', data.enrichment.reverse_dns],
                  ].filter(([, v]) => v).map(([k, v]) => (
                    <div key={String(k)} className="flex justify-between gap-4">
                      <span className="text-muted-foreground">{k}</span>
                      <span className="text-right break-all">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {data.daily?.length > 1 && (
              <section>
                <h4 className="font-medium mb-2">Requests over time</h4>
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart data={data.daily}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11}
                      tickFormatter={(d: string) => d.slice(5)} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }} />
                    <Area type="monotone" dataKey="requests" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} />
                  </AreaChart>
                </ResponsiveContainer>
              </section>
            )}

            {data.threats?.length > 0 && (
              <section>
                <h4 className="font-medium mb-2 flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-red-500" /> Threats</h4>
                <div className="space-y-1">
                  {data.threats.map((th: Record<string, unknown>, i: number) => (
                    <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm">
                      <span>{String(th.category)} <span className="text-xs text-muted-foreground">({String(th.severity)})</span></span>
                      <span className="font-mono">{String(th.count)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section>
              <h4 className="font-medium mb-2 flex items-center gap-2"><Server className="h-4 w-4 text-muted-foreground" /> Hosts visited</h4>
              {data.by_host?.length === 0 ? (
                <p className="text-sm text-muted-foreground">No traffic in this window.</p>
              ) : (
                <div className="space-y-1">
                  {data.by_host.map((h: Record<string, unknown>) => (
                    <div key={String(h.host_id)} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm">
                      <span className="truncate" data-private="domain">{String(h.host_name)}</span>
                      <span className="font-mono shrink-0">
                        {Number(h.requests).toLocaleString()}
                        {Number(h.errors) > 0 && (
                          <span className="text-red-500 ml-2">{String(h.errors)} err</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <h4 className="font-medium mb-2">Top paths</h4>
              <div className="space-y-1">
                {data.top_paths?.map((p: Record<string, unknown>, i: number) => (
                  <div key={i} className="flex items-center justify-between gap-3 text-sm">
                    <code className="text-xs truncate">{String(p.uri)}</code>
                    <span className="font-mono text-xs shrink-0">{Number(p.requests).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </>,
    document.body,
  )
}

export default IpReport
