'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Activity,
  Users,
  AlertTriangle,
  RefreshCw,
  Zap,
  BarChart3,
  Shield,
  Gauge,
} from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import api from '@/lib/api'
import { OverviewTab } from '@/components/analytics/overview-tab'
import { TrafficTab } from '@/components/analytics/traffic-tab'
import { SecurityTab } from '@/components/analytics/security-tab'
import { PerformanceTab } from '@/components/analytics/performance-tab'

interface AnalyticsDashboard {
  total_requests: number
  total_unique_visitors: number
  total_bytes_transferred: number
  avg_response_time: number | null
  error_rate: number
  requests_change_percent: number | null
  visitors_change_percent: number | null
  time_series: Array<{
    timestamp: string
    requests: number
    unique_visitors: number
    bytes_sent: number
    bytes_received: number
    avg_response_time: number | null
  }>
  status_breakdown: {
    status_2xx: number
    status_3xx: number
    status_4xx: number
    status_5xx: number
  }
  requests_by_method: Record<string, number>
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
  hourly_distribution: Array<{ hour: number; requests: number }>
  browser_stats: Array<{ browser: string; requests: number; percentage: number }>
  country_stats: Array<{ country: string; requests: number }>
  errors_by_host: Array<{
    host_id: string
    host_name: string
    total_errors: number
    status_codes: Record<string, number>
  }>
  errors_by_status: Array<{ status: number; count: number }>
}

interface RealtimeStats {
  requests_per_minute: number
  requests_last_5min: number
  active_visitors: number
  recent_errors: number
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsDashboard | null>(null)
  const [realtime, setRealtime] = useState<RealtimeStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [period, setPeriod] = useState<'24h' | '7d' | '30d' | '90d'>('7d')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(30)
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Traffic, security, and performance insights
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
            <span className="hidden sm:inline">Refresh</span>
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
        <div className="flex flex-wrap items-center gap-4 sm:gap-6 rounded-lg border border-border bg-card/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-sm font-medium">Live</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Zap className="h-4 w-4 text-yellow-500" />
            <span className="text-muted-foreground">Req/min:</span>
            <span className="font-mono font-medium">{realtime.requests_per_minute}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-blue-500" />
            <span className="text-muted-foreground">Active:</span>
            <span className="font-mono font-medium">{realtime.active_visitors}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Activity className="h-4 w-4 text-green-500" />
            <span className="text-muted-foreground">5 min:</span>
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

      {/* Tabbed Content */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
          <TabsTrigger value="overview" className="gap-1.5">
            <BarChart3 className="h-4 w-4" />
            <span className="hidden sm:inline">Overview</span>
          </TabsTrigger>
          <TabsTrigger value="traffic" className="gap-1.5">
            <Activity className="h-4 w-4" />
            <span className="hidden sm:inline">Traffic</span>
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-1.5">
            <Shield className="h-4 w-4" />
            <span className="hidden sm:inline">Security</span>
          </TabsTrigger>
          <TabsTrigger value="performance" className="gap-1.5">
            <Gauge className="h-4 w-4" />
            <span className="hidden sm:inline">Performance</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab
            data={data}
            formatNumber={formatNumber}
            formatBytes={formatBytes}
            formatResponseTime={formatResponseTime}
          />
        </TabsContent>

        <TabsContent value="traffic">
          <TrafficTab
            data={data}
            formatNumber={formatNumber}
            formatBytes={formatBytes}
            formatResponseTime={formatResponseTime}
          />
        </TabsContent>

        <TabsContent value="security">
          <SecurityTab period={period} />
        </TabsContent>

        <TabsContent value="performance">
          <PerformanceTab
            data={data}
            formatNumber={formatNumber}
            formatBytes={formatBytes}
            formatResponseTime={formatResponseTime}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
