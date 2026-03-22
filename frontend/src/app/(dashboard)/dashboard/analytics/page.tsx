'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import {
  Activity,
  Users,
  Globe,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  Server,
  FileText,
  Link2,
  Monitor,
  Zap,
  ShieldX,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import api from '@/lib/api'

const GeoHeatmap = dynamic(() => import('@/components/geo-heatmap'), { ssr: false })

interface TimeSeriesPoint {
  timestamp: string
  requests: number
  unique_visitors: number
  bytes_sent: number
  bytes_received: number
  avg_response_time: number | null
}

interface HostStats {
  host_id: string
  host_name: string
  requests: number
  unique_visitors: number
  bytes_sent: number
  avg_response_time: number | null
  error_rate: number
}

interface TopPage {
  uri: string
  requests: number
  avg_response_time: number | null
}

interface TopReferrer {
  referer: string
  requests: number
}

interface BrowserStats {
  browser: string
  requests: number
  percentage: number
}

interface HourlyDistribution {
  hour: number
  requests: number
}

interface AnalyticsDashboard {
  total_requests: number
  total_unique_visitors: number
  total_bytes_transferred: number
  avg_response_time: number | null
  error_rate: number
  requests_change_percent: number | null
  visitors_change_percent: number | null
  time_series: TimeSeriesPoint[]
  status_breakdown: {
    status_2xx: number
    status_3xx: number
    status_4xx: number
    status_5xx: number
  }
  requests_by_method: Record<string, number>
  top_hosts: HostStats[]
  top_pages: TopPage[]
  top_referrers: TopReferrer[]
  top_ips: { ip: string; requests: number }[]
  hourly_distribution: HourlyDistribution[]
  browser_stats: BrowserStats[]
  country_stats: { country: string; requests: number }[]
  errors_by_host: {
    host_id: string
    host_name: string
    total_errors: number
    status_codes: Record<string, number>
  }[]
  errors_by_status: { status: number; count: number }[]
}

interface RealtimeStats {
  requests_per_minute: number
  requests_last_5min: number
  active_visitors: number
  recent_errors: number
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']
const STATUS_COLORS = {
  '2xx': '#10b981',
  '3xx': '#3b82f6',
  '4xx': '#f59e0b',
  '5xx': '#ef4444',
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsDashboard | null>(null)
  const [realtime, setRealtime] = useState<RealtimeStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [period, setPeriod] = useState<'24h' | '7d' | '30d' | '90d'>('7d')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(30) // seconds
  const [countdown, setCountdown] = useState(30)
  const countdownRef = useRef(30)

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setIsRefreshing(true)
    try {
      const response = await api.get(`/api/analytics/dashboard?period=${period}`)
      setData(response.data)
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [period])

  const fetchRealtime = useCallback(async () => {
    try {
      const response = await api.get('/api/analytics/realtime')
      setRealtime(response.data)
    } catch (error) {
      console.error('Failed to fetch realtime stats:', error)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    fetchRealtime()
    const interval = setInterval(fetchRealtime, 15000)
    return () => clearInterval(interval)
  }, [fetchRealtime])

  // Auto-refresh countdown and data fetch
  useEffect(() => {
    if (!autoRefresh) return

    countdownRef.current = refreshInterval
    setCountdown(refreshInterval)

    const tick = setInterval(() => {
      countdownRef.current -= 1
      setCountdown(countdownRef.current)

      if (countdownRef.current <= 0) {
        fetchData(true)
        fetchRealtime()
        countdownRef.current = refreshInterval
        setCountdown(refreshInterval)
      }
    }, 1000)

    return () => clearInterval(tick)
  }, [autoRefresh, refreshInterval, fetchData, fetchRealtime])

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatNumber = (num: number) => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
    return num.toString()
  }

  const formatResponseTime = (ms: number | null) => {
    if (ms === null) return '-'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading analytics...</div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-muted-foreground">No analytics data available</div>
      </div>
    )
  }

  const statusData = [
    { name: '2xx Success', value: data.status_breakdown.status_2xx, color: STATUS_COLORS['2xx'] },
    { name: '3xx Redirect', value: data.status_breakdown.status_3xx, color: STATUS_COLORS['3xx'] },
    { name: '4xx Client Error', value: data.status_breakdown.status_4xx, color: STATUS_COLORS['4xx'] },
    { name: '5xx Server Error', value: data.status_breakdown.status_5xx, color: STATUS_COLORS['5xx'] },
  ].filter(d => d.value > 0)

  const methodData = Object.entries(data.requests_by_method).map(([method, count]) => ({
    method,
    count,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Traffic insights and performance metrics
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-input overflow-hidden">
            {(['24h', '7d', '30d', '90d'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  period === p
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchData()}
            disabled={isRefreshing}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <div className="flex items-center gap-2 rounded-lg border border-input px-3 py-2">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-1.5 text-sm font-medium transition-colors ${
                autoRefresh ? 'text-green-500' : 'text-muted-foreground'
              }`}
              title={autoRefresh ? 'Disable auto-refresh' : 'Enable auto-refresh'}
            >
              <div className={`h-2 w-2 rounded-full ${autoRefresh ? 'bg-green-500 animate-pulse' : 'bg-muted-foreground/30'}`} />
              {autoRefresh ? `${countdown}s` : 'Auto'}
            </button>
            {autoRefresh && (
              <select
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(Number(e.target.value))}
                title="Auto-refresh interval"
                className="bg-transparent text-xs text-muted-foreground border-none outline-none cursor-pointer"
              >
                <option value={15}>15s</option>
                <option value={30}>30s</option>
                <option value={60}>1m</option>
                <option value={300}>5m</option>
              </select>
            )}
          </div>
        </div>
      </div>

      {/* Real-time Stats Bar */}
      {realtime && (
        <div className="flex items-center gap-6 rounded-lg border border-border bg-card/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-sm font-medium">Live</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Zap className="h-4 w-4 text-yellow-500" />
            <span className="text-muted-foreground">Requests/min:</span>
            <span className="font-mono font-medium">{realtime.requests_per_minute}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-blue-500" />
            <span className="text-muted-foreground">Active visitors:</span>
            <span className="font-mono font-medium">{realtime.active_visitors}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Activity className="h-4 w-4 text-green-500" />
            <span className="text-muted-foreground">Last 5 min:</span>
            <span className="font-mono font-medium">{realtime.requests_last_5min}</span>
          </div>
          {realtime.recent_errors > 0 && (
            <div className="flex items-center gap-2 text-sm text-red-500">
              <AlertTriangle className="h-4 w-4" />
              <span>{realtime.recent_errors} errors</span>
            </div>
          )}
        </div>
      )}

      {/* Main Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Total Requests</p>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatNumber(data.total_requests)}</p>
          {data.requests_change_percent !== null && (
            <div className={`flex items-center gap-1 text-xs mt-1 ${
              data.requests_change_percent >= 0 ? 'text-green-500' : 'text-red-500'
            }`}>
              {data.requests_change_percent >= 0 ? (
                <ArrowUpRight className="h-3 w-3" />
              ) : (
                <ArrowDownRight className="h-3 w-3" />
              )}
              {Math.abs(data.requests_change_percent)}% vs previous period
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Unique Visitors</p>
            <Users className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatNumber(data.total_unique_visitors)}</p>
          {data.visitors_change_percent !== null && (
            <div className={`flex items-center gap-1 text-xs mt-1 ${
              data.visitors_change_percent >= 0 ? 'text-green-500' : 'text-red-500'
            }`}>
              {data.visitors_change_percent >= 0 ? (
                <ArrowUpRight className="h-3 w-3" />
              ) : (
                <ArrowDownRight className="h-3 w-3" />
              )}
              {Math.abs(data.visitors_change_percent)}% vs previous period
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Data Transferred</p>
            <Globe className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatBytes(data.total_bytes_transferred)}</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Avg Response Time</p>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-2xl font-bold mt-1">{formatResponseTime(data.avg_response_time)}</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Error Rate</p>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className={`text-2xl font-bold mt-1 ${
            data.error_rate > 5 ? 'text-red-500' : data.error_rate > 1 ? 'text-yellow-500' : 'text-green-500'
          }`}>
            {data.error_rate.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Traffic Over Time Chart */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Traffic Over Time</h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data.time_series}>
            <defs>
              <linearGradient id="requestsGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="visitorsGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="timestamp"
              tick={{ fontSize: 12 }}
              className="text-muted-foreground"
            />
            <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="requests"
              name="Requests"
              stroke="#3b82f6"
              fill="url(#requestsGradient)"
              strokeWidth={2}
            />
            <Area
              type="monotone"
              dataKey="unique_visitors"
              name="Unique Visitors"
              stroke="#10b981"
              fill="url(#visitorsGradient)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Middle Row - Status and Methods */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Status Code Breakdown */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Status Codes</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={statusData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {statusData.map((entry, index) => (
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
          <div className="flex flex-wrap justify-center gap-4 mt-2">
            {statusData.map((entry) => (
              <div key={entry.name} className="flex items-center gap-2 text-xs">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span>{entry.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* HTTP Methods */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">HTTP Methods</h3>
          <ResponsiveContainer width="100%" height={200}>
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

        {/* Hourly Distribution */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Hourly Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.hourly_distribution}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="hour"
                tick={{ fontSize: 10 }}
                tickFormatter={(h) => `${h}:00`}
              />
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

      {/* Top Hosts */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold">Top Hosts</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Host
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Requests
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Unique Visitors
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Bandwidth
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Avg Response
                </th>
                <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Error Rate
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.top_hosts.map((host, idx) => (
                <tr key={host.host_id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 rounded-full"
                        style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                      />
                      <span className="font-medium">{host.host_name}</span>
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

      {/* Error Breakdown by Host & Status */}
      {(data.errors_by_host.length > 0 || data.errors_by_status.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Errors by Host */}
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <ShieldX className="h-5 w-5 text-red-500" />
              <h3 className="font-semibold">Errors by Host</h3>
            </div>
            {data.errors_by_host.length === 0 ? (
              <p className="text-sm text-muted-foreground">No errors in this period</p>
            ) : (
              <div className="space-y-3">
                {data.errors_by_host.map((host) => {
                  const maxErrors = data.errors_by_host[0]?.total_errors || 1
                  const percentage = (host.total_errors / maxErrors) * 100
                  return (
                    <div key={host.host_id}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium truncate">{host.host_name}</span>
                        <span className="text-xs font-mono text-muted-foreground">
                          {formatNumber(host.total_errors)} errors
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden mb-1">
                        <div
                          className="h-full rounded-full bg-red-500 transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(host.status_codes)
                          .sort(([, a], [, b]) => b - a)
                          .map(([code, count]) => (
                            <span
                              key={code}
                              className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                                parseInt(code) >= 500
                                  ? 'bg-red-500/10 text-red-500'
                                  : code === '403'
                                  ? 'bg-orange-500/10 text-orange-500'
                                  : code === '404'
                                  ? 'bg-yellow-500/10 text-yellow-500'
                                  : 'bg-slate-500/10 text-slate-400'
                              }`}
                            >
                              {code}: {count}
                            </span>
                          ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Errors by Status Code */}
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              <h3 className="font-semibold">Error Status Codes</h3>
            </div>
            {data.errors_by_status.length === 0 ? (
              <p className="text-sm text-muted-foreground">No errors in this period</p>
            ) : (
              <div className="space-y-2">
                {data.errors_by_status.map((item) => {
                  const maxCount = data.errors_by_status[0]?.count || 1
                  const percentage = (item.count / maxCount) * 100
                  const statusLabel: Record<number, string> = {
                    400: 'Bad Request',
                    401: 'Unauthorized',
                    403: 'Forbidden',
                    404: 'Not Found',
                    405: 'Method Not Allowed',
                    408: 'Request Timeout',
                    429: 'Too Many Requests',
                    500: 'Internal Server Error',
                    502: 'Bad Gateway',
                    503: 'Service Unavailable',
                    504: 'Gateway Timeout',
                  }
                  return (
                    <div key={item.status} className="flex items-center gap-3">
                      <span className={`text-xs font-mono w-8 font-bold ${
                        item.status >= 500 ? 'text-red-500' : item.status === 403 ? 'text-orange-500' : 'text-yellow-500'
                      }`}>
                        {item.status}
                      </span>
                      <span className="text-xs text-muted-foreground w-32 truncate">
                        {statusLabel[item.status] || 'Other'}
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            item.status >= 500 ? 'bg-red-500' : item.status === 403 ? 'bg-orange-500' : 'bg-yellow-500'
                          }`}
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-muted-foreground w-16 text-right">
                        {formatNumber(item.count)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Bottom Row - Pages, Referrers, Browsers */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Top Pages */}
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
                  <code className="text-xs truncate flex-1" title={page.uri}>
                    {page.uri}
                  </code>
                </div>
                <span className="text-xs font-mono text-muted-foreground ml-2">
                  {formatNumber(page.requests)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Top Referrers */}
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
                    <span className="text-xs truncate flex-1" title={ref.referer}>
                      {ref.referer}
                    </span>
                  </div>
                  <span className="text-xs font-mono text-muted-foreground ml-2">
                    {formatNumber(ref.requests)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Browser Stats */}
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
                  <span className="text-xs font-mono text-muted-foreground">
                    {browser.percentage}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${browser.percentage}%`,
                      backgroundColor: COLORS[idx % COLORS.length],
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top IPs and Countries */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Top IPs */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Top IP Addresses</h3>
          <div className="space-y-2">
            {data.top_ips.map((item, idx) => {
              const maxRequests = data.top_ips[0]?.requests || 1
              const percentage = (item.requests / maxRequests) * 100
              return (
                <div key={idx} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-4">{idx + 1}.</span>
                  <code className="text-xs font-mono w-32">{item.ip}</code>
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-muted-foreground w-16 text-right">
                    {formatNumber(item.requests)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Countries */}
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
                        style={{
                          width: `${percentage}%`,
                          backgroundColor: COLORS[idx % COLORS.length],
                        }}
                      />
                    </div>
                    <span className="text-xs font-mono text-muted-foreground w-16 text-right">
                      {formatNumber(item.requests)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Geographic Heatmap */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Traffic Origin Heatmap</h3>
        <GeoHeatmap days={period === '24h' ? 1 : period === '7d' ? 7 : period === '30d' ? 30 : 90} />
      </div>

      {/* Response Time Chart */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Response Time Trend</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data.time_series.filter(d => d.avg_response_time !== null)}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="timestamp" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v}ms`} />
            <Tooltip
              formatter={(value: number) => [`${value.toFixed(2)}ms`, 'Avg Response Time']}
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
            />
            <Line
              type="monotone"
              dataKey="avg_response_time"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
