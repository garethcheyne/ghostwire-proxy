'use client'

import {
  Server,
  FileText,
  Link2,
  Monitor,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { IpAddress } from '@/components/ip-address'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

interface TrafficTabProps {
  data: {
    requests_by_method: Record<string, number>
    hourly_distribution: Array<{ hour: number; requests: number }>
    top_hosts: Array<{
      host_id: string
      host_name: string
      requests: number
      unique_visitors: number
      bytes_sent: number
      avg_response_time: number | null
      error_rate: number
    }>
    top_pages: Array<{ uri: string; requests: number; avg_response_time: number | null }>
    top_referrers: Array<{ referer: string; requests: number }>
    top_ips: Array<{ ip: string; requests: number; country_code?: string; country_name?: string }>
    browser_stats: Array<{ browser: string; requests: number; percentage: number }>
    country_stats: Array<{ country: string; requests: number }>
  }
  formatNumber: (n: number) => string
  formatBytes: (b: number) => string
  formatResponseTime: (ms: number | null) => string
}

export function TrafficTab({ data, formatNumber, formatBytes, formatResponseTime }: TrafficTabProps) {
  const methodData = Object.entries(data.requests_by_method).map(([method, count]) => ({
    method,
    count,
  }))

  return (
    <div className="space-y-6">
      {/* HTTP Methods & Hourly Distribution */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">HTTP Methods</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={methodData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis dataKey="method" type="category" tick={{ fontSize: 12 }} width={50} />
              <Tooltip
                formatter={(value: number) => formatNumber(value)}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Hourly Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.hourly_distribution}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickFormatter={(h) => `${h}:00`} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip
                labelFormatter={(h) => `${h}:00 - ${h}:59`}
                formatter={(value: number) => formatNumber(value)}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="requests" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Hosts Table */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold">Top Hosts</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Host</th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Requests</th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Visitors</th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Bandwidth</th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Avg Response</th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">Error Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.top_hosts.map((host, idx) => (
                <tr key={host.host_id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                      <span className="font-medium" data-private="domain">{host.host_name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">{formatNumber(host.requests)}</td>
                  <td className="px-4 py-3 text-right font-mono">{formatNumber(host.unique_visitors)}</td>
                  <td className="px-4 py-3 text-right font-mono">{formatBytes(host.bytes_sent)}</td>
                  <td className="px-4 py-3 text-right font-mono">{formatResponseTime(host.avg_response_time)}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`font-mono ${
                      host.error_rate > 5 ? 'text-red-500' : host.error_rate > 1 ? 'text-yellow-500' : 'text-green-500'
                    }`}>
                      {host.error_rate.toFixed(2)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pages, Referrers, Browsers */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Top Pages</h3>
          </div>
          <div className="space-y-3">
            {data.top_pages.slice(0, 8).map((page, idx) => (
              <div key={idx} className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                  <code className="text-xs truncate flex-1" title={page.uri}>{page.uri}</code>
                </div>
                <span className="text-xs font-mono text-muted-foreground ml-2">{formatNumber(page.requests)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Link2 className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Top Referrers</h3>
          </div>
          <div className="space-y-3">
            {data.top_referrers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No referrer data available</p>
            ) : (
              data.top_referrers.slice(0, 8).map((ref, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                    <span className="text-xs truncate flex-1" title={ref.referer}>{ref.referer}</span>
                  </div>
                  <span className="text-xs font-mono text-muted-foreground ml-2">{formatNumber(ref.requests)}</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Monitor className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Browsers</h3>
          </div>
          <div className="space-y-3">
            {data.browser_stats.map((browser, idx) => (
              <div key={idx}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm">{browser.browser}</span>
                  <span className="text-xs font-mono text-muted-foreground">{browser.percentage}%</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${browser.percentage}%`, backgroundColor: COLORS[idx % COLORS.length] }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top IPs and Countries */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Top IP Addresses</h3>
          <div className="space-y-2">
            {data.top_ips.map((item, idx) => {
              const maxRequests = data.top_ips[0]?.requests || 1
              const percentage = (item.requests / maxRequests) * 100
              return (
                <div key={idx} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                  <div className="flex items-center gap-1.5 w-40">
                    <IpAddress ip={item.ip} countryCode={item.country_code} countryName={item.country_name} />
                  </div>
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${percentage}%` }} />
                  </div>
                  <span className="text-xs font-mono text-muted-foreground w-16 text-right">{formatNumber(item.requests)}</span>
                </div>
              )
            })}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Countries</h3>
          {data.country_stats.length === 0 ? (
            <p className="text-sm text-muted-foreground">No geographic data available</p>
          ) : (
            <div className="space-y-2">
              {data.country_stats.map((item, idx) => {
                const maxRequests = data.country_stats[0]?.requests || 1
                const percentage = (item.requests / maxRequests) * 100
                return (
                  <div key={idx} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                    <span className="text-sm w-8">{item.country}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${percentage}%`, backgroundColor: COLORS[idx % COLORS.length] }}
                      />
                    </div>
                    <span className="text-xs font-mono text-muted-foreground w-16 text-right">{formatNumber(item.requests)}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
