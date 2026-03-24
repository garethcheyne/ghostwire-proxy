'use client'

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import {
  Shield,
  ShieldAlert,
  ShieldBan,
  ShieldCheck,
  AlertTriangle,
  Ban,
  Eye,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from 'recharts'
import api from '@/lib/api'
import { IpAddress } from '@/components/ip-address'

const GeoHeatmap = dynamic(() => import('@/components/geo-heatmap'), { ssr: false })

interface ThreatStats {
  total_events: number
  events_today: number
  events_this_week: number
  total_actors: number
  blocked_actors: number
  top_categories: Array<{ category: string; count: number }>
  top_actors: Array<{ ip: string; score: number; events: number; status: string }>
  severity_breakdown: Record<string, number>
}

interface AuthErrors {
  summary: {
    total_401: number
    total_403: number
    failed_logins: number
  }
  recent_events: Array<{
    timestamp: string
    ip: string
    status: number
    method: string
    uri: string
    host: string
    country: string | null
  }>
  top_offenders: Array<{
    ip: string
    count: number
    last_seen: string
  }>
}

interface ThreatEvent {
  id: string
  timestamp: string
  client_ip: string
  category: string
  severity: string
  rule_name: string | null
  request_method: string
  request_uri: string
  host: string
  blocked: boolean
}

interface HostThreatData {
  host: string
  total: number
  categories: Record<string, number>
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
}

const CATEGORY_COLORS: Record<string, string> = {
  sqli: '#ef4444',
  xss: '#f97316',
  path_traversal: '#eab308',
  rce: '#a855f7',
  scanner: '#3b82f6',
  injection: '#ec4899',
  sensitive_data: '#14b8a6',
  recon: '#6366f1',
  dos: '#f43f5e',
  blocked_ip: '#6b7280',
}

const statusColors: Record<string, string> = {
  monitored: 'bg-slate-500/10 text-slate-400',
  warned: 'bg-yellow-500/10 text-yellow-500',
  temp_blocked: 'bg-orange-500/10 text-orange-500',
  perm_blocked: 'bg-red-500/10 text-red-500',
  firewall_banned: 'bg-purple-500/10 text-purple-500',
}

interface SecurityTabProps {
  period: '24h' | '7d' | '30d' | '90d'
}

export function SecurityTab({ period }: SecurityTabProps) {
  const [stats, setStats] = useState<ThreatStats | null>(null)
  const [authErrors, setAuthErrors] = useState<AuthErrors | null>(null)
  const [recentEvents, setRecentEvents] = useState<ThreatEvent[]>([])
  const [hostThreats, setHostThreats] = useState<HostThreatData[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const days = period === '24h' ? 1 : period === '7d' ? 7 : period === '30d' ? 30 : 90

  const fetchData = useCallback(async () => {
    setIsLoading(true)
    try {
      const [statsRes, authRes, eventsRes, hostRes] = await Promise.all([
        api.get('/api/waf/stats'),
        api.get(`/api/analytics/auth-errors?period=${period}`),
        api.get('/api/waf/events?limit=10'),
        api.get(`/api/waf/threats/by-host?days=${days}`),
      ])
      setStats(statsRes.data)
      setAuthErrors(authRes.data)
      setRecentEvents(eventsRes.data)
      setHostThreats(hostRes.data)
    } catch (error) {
      console.error('Failed to fetch security data:', error)
    } finally {
      setIsLoading(false)
    }
  }, [period, days])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const formatNumber = (num: number) => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
    return num.toString()
  }

  if (isLoading || !stats) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading security analytics...</div>
      </div>
    )
  }

  const severityData = Object.entries(stats.severity_breakdown)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: SEVERITY_COLORS[name] || '#6b7280',
    }))

  const categoryData = stats.top_categories
    .filter(c => c.count > 0)
    .map(c => ({
      category: c.category.replace(/_/g, ' '),
      rawCategory: c.category,
      count: c.count,
    }))

  // Build stacked bar data for hosts under attack
  const hostChartData = hostThreats.slice(0, 10).map(h => {
    const shortHost = h.host.replace(/\.err403\.com$/, '')
    const entry: Record<string, string | number> = { host: shortHost, total: h.total }
    for (const [cat, count] of Object.entries(h.categories)) {
      entry[cat] = count
    }
    return entry
  })

  // Collect all unique categories across hosts
  const allCategories = Array.from(
    new Set(hostThreats.flatMap(h => Object.keys(h.categories)))
  )

  return (
    <div className="space-y-6">
      {/* Threat Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Total Threats</p>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatNumber(stats.total_events)}</p>
          <p className="text-xs text-muted-foreground mt-1">all time</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Today</p>
            <ShieldAlert className="h-4 w-4 text-yellow-500" />
          </div>
          <p className="text-2xl font-bold mt-1 text-yellow-500">{formatNumber(stats.events_today)}</p>
          <p className="text-xs text-muted-foreground mt-1">events detected</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">This Week</p>
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </div>
          <p className="text-2xl font-bold mt-1 text-orange-500">{formatNumber(stats.events_this_week)}</p>
          <p className="text-xs text-muted-foreground mt-1">events detected</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Threat Actors</p>
            <Eye className="h-4 w-4 text-blue-500" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatNumber(stats.total_actors)}</p>
          <p className="text-xs text-muted-foreground mt-1">unique IPs</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Blocked</p>
            <ShieldBan className="h-4 w-4 text-red-500" />
          </div>
          <p className="text-2xl font-bold mt-1 text-red-500">{formatNumber(stats.blocked_actors)}</p>
          <p className="text-xs text-muted-foreground mt-1">IPs blocked</p>
        </div>
      </div>

      {/* Severity & Category Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Severity Breakdown */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Severity Breakdown</h3>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width="50%" height={200}>
              <PieChart>
                <Pie
                  data={severityData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {severityData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number) => formatNumber(value)}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-3">
              {severityData.map((entry) => (
                <div key={entry.name} className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: entry.color }} />
                  <div>
                    <p className="text-sm font-medium">{entry.name}</p>
                    <p className="text-xs text-muted-foreground">{formatNumber(entry.value)} events</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Attack Categories */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Attack Categories</h3>
          {categoryData.length === 0 ? (
            <div className="flex h-[200px] items-center justify-center text-muted-foreground">
              <ShieldCheck className="h-8 w-8 mr-2" />
              No threats detected
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={categoryData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis
                  dataKey="category"
                  type="category"
                  tick={{ fontSize: 11 }}
                  width={100}
                  tickFormatter={(v: string) => v.charAt(0).toUpperCase() + v.slice(1)}
                />
                <Tooltip
                  formatter={(value: number) => formatNumber(value)}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {categoryData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={CATEGORY_COLORS[entry.rawCategory] || '#6b7280'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Hosts Under Attack */}
      {hostChartData.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-red-500" />
              <h3 className="font-semibold">Most Targeted Hosts</h3>
            </div>
            <span className="text-xs text-muted-foreground">Last {days} {days === 1 ? 'day' : 'days'}</span>
          </div>
          <ResponsiveContainer width="100%" height={Math.max(220, hostChartData.length * 36)}>
            <BarChart data={hostChartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis
                dataKey="host"
                type="category"
                tick={{ fontSize: 11 }}
                width={120}
              />
              <Tooltip
                formatter={(value: number, name: string) => [formatNumber(value), name.replace(/_/g, ' ')]}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              {allCategories.map((cat) => (
                <Bar
                  key={cat}
                  dataKey={cat}
                  stackId="threats"
                  fill={CATEGORY_COLORS[cat] || '#6b7280'}
                  radius={allCategories.indexOf(cat) === allCategories.length - 1 ? [0, 4, 4, 0] : undefined}
                  name={cat.replace(/_/g, ' ')}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-3 justify-center">
            {allCategories.map((cat) => (
              <div key={cat} className="flex items-center gap-1.5 text-xs">
                <div className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CATEGORY_COLORS[cat] || '#6b7280' }} />
                <span className="text-muted-foreground">{cat.replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Auth Errors & Top Threat Actors */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Auth Errors */}
        {authErrors && (
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <Ban className="h-5 w-5 text-red-500" />
              <h3 className="font-semibold">Authentication Errors</h3>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="rounded-lg bg-red-500/5 border border-red-500/10 p-3 text-center">
                <p className="text-2xl font-bold text-red-500">{formatNumber(authErrors.summary.total_401)}</p>
                <p className="text-xs text-muted-foreground">401 Unauthorized</p>
              </div>
              <div className="rounded-lg bg-orange-500/5 border border-orange-500/10 p-3 text-center">
                <p className="text-2xl font-bold text-orange-500">{formatNumber(authErrors.summary.total_403)}</p>
                <p className="text-xs text-muted-foreground">403 Forbidden</p>
              </div>
            </div>
            {authErrors.top_offenders.length > 0 && (
              <>
                <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wider">Top Offending IPs</p>
                <div className="space-y-2">
                  {authErrors.top_offenders.slice(0, 5).map((item, idx) => {
                    const maxCount = authErrors.top_offenders[0]?.count || 1
                    const pct = (item.count / maxCount) * 100
                    return (
                      <div key={idx} className="flex items-center gap-3">
                        <div className="w-32 truncate">
                          <IpAddress ip={item.ip} />
                        </div>
                        <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                          <div className="h-full rounded-full bg-red-500 transition-all" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs font-mono text-muted-foreground w-12 text-right">{item.count}</span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {/* Top Threat Actors */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert className="h-5 w-5 text-orange-500" />
            <h3 className="font-semibold">Top Threat Actors</h3>
          </div>
          {stats.top_actors.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground text-sm">
              No threat actors detected
            </div>
          ) : (
            <div className="space-y-3">
              {stats.top_actors.slice(0, 8).map((actor, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                  <div className="flex-1 min-w-0 truncate">
                    <IpAddress ip={actor.ip} />
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${statusColors[actor.status] || 'bg-slate-500/10 text-slate-400'}`}>
                    {actor.status.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs text-muted-foreground w-16 text-right">{actor.events} events</span>
                  <span className={`text-xs font-mono w-10 text-right font-bold ${
                    actor.score >= 80 ? 'text-red-500' : actor.score >= 50 ? 'text-orange-500' : actor.score >= 20 ? 'text-yellow-500' : 'text-blue-500'
                  }`}>
                    {actor.score}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Threat Events */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Recent Threat Events</h3>
          </div>
          <a href="/dashboard/threats" className="text-xs text-primary hover:underline">
            View all →
          </a>
        </div>
        {recentEvents.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-muted-foreground text-sm">
            <ShieldCheck className="h-5 w-5 mr-2" />
            No recent threats
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Time</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">IP</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Category</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Severity</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Host</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Request</th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recentEvents.map((event) => (
                  <tr key={event.id} className="hover:bg-muted/50">
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(event.timestamp).toLocaleString(undefined, {
                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                      })}
                    </td>
                    <td className="px-3 py-2">
                      <IpAddress ip={event.client_ip} />
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-xs px-1.5 py-0.5 rounded" style={{
                        backgroundColor: `${CATEGORY_COLORS[event.category] || '#6b7280'}15`,
                        color: CATEGORY_COLORS[event.category] || '#6b7280',
                      }}>
                        {event.category.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-xs px-1.5 py-0.5 rounded font-medium" style={{
                        backgroundColor: `${SEVERITY_COLORS[event.severity] || '#6b7280'}15`,
                        color: SEVERITY_COLORS[event.severity] || '#6b7280',
                      }}>
                        {event.severity}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400">{event.host}</span>
                    </td>
                    <td className="px-3 py-2">
                      <code className="text-xs font-mono text-muted-foreground truncate max-w-[200px] block">
                        {event.request_method} {event.request_uri}
                      </code>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        event.blocked ? 'bg-red-500/10 text-red-500' : 'bg-yellow-500/10 text-yellow-500'
                      }`}>
                        {event.blocked ? 'Blocked' : 'Logged'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Threat Geographic Map */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Threat Origin Heatmap</h3>
        <GeoHeatmap days={days} showThreats />
      </div>
    </div>
  )
}
