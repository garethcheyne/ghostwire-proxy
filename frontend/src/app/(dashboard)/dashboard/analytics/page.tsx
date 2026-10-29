'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { usePageData } from '@/lib/use-page-data'
import {
  Activity,
  Users,
  AlertTriangle,
  RefreshCw,
  Zap,
  BarChart3,
  TrendingUp,
  Shield,
  Gauge,
} from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import api from '@/lib/api'
import { useProxyHosts } from '@/lib/queries/proxy-hosts'
import { OverviewTab } from '@/components/analytics/overview-tab'
import { TrafficTab } from '@/components/analytics/traffic-tab'
import { SecurityTab } from '@/components/analytics/security-tab'
import { PerformanceTab } from '@/components/analytics/performance-tab'
import { LogsTab } from '@/components/analytics/logs-tab'
import { TrendsTab, type TrendsData } from '@/components/analytics/trends-tab'
import { FileText } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { BarChart3 as HeaderIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ContentSkeleton, LoadError } from '@/components/load-state'

const PERIODS = ['24h', '7d', '30d', '90d'] as const
type Period = (typeof PERIODS)[number]
/** Select items can't have an empty value; this stands for "all hosts" ('' in state). */
const ALL_HOSTS = '__all__'

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
  const [period, setPeriod] = useState<Period>('7d')
  // '' = all hosts. The dashboard endpoint has always accepted proxy_host_id;
  // the UI just never sent it, so every figure was fleet-wide.
  const [selectedHost, setSelectedHost] = useState('')
  const [trends, setTrends] = useState<TrendsData | null>(null)
  const [trendsLoading, setTrendsLoading] = useState(true)
  const [trendsFailed, setTrendsFailed] = useState(false)
  const { data: hostsData } = useProxyHosts({ limit: 100 })
  const hosts = hostsData?.items ?? []
  const selectedHostName =
    hosts.find((h) => h.id === selectedHost)?.domain_names?.[0] ?? null
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(30)
  const [countdown, setCountdown] = useState(30)
  const countdownRef = useRef(30)

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setIsRefreshing(true)
    try {
      const params = new URLSearchParams({ period })
      if (selectedHost) params.set('proxy_host_id', selectedHost)
      const response = await api.get(`/api/analytics/dashboard?${params}`)
      setData(response.data)
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [period, selectedHost])

  // Trends come from the analytics_* rollups, not traffic_logs, so this reaches
  // past the retention window. Its own fetch because it has a different range
  // (90 days) and a much cheaper cache than the live dashboard.
  const fetchTrends = useCallback(async () => {
    try {
      const params = new URLSearchParams({ days: '90' })
      if (selectedHost) params.set('proxy_host_id', selectedHost)
      const response = await api.get(`/api/analytics/trends?${params}`)
      setTrends(response.data)
      setTrendsFailed(false)
    } catch (error) {
      console.error('Failed to fetch trends:', error)
      setTrendsFailed(true)
    } finally {
      setTrendsLoading(false)
    }
  }, [selectedHost])

  usePageData(fetchTrends, [selectedHost])

  const fetchRealtime = useCallback(async () => {
    try {
      const response = await api.get('/api/analytics/realtime')
      setRealtime(response.data)
    } catch (error) {
      console.error('Failed to fetch realtime stats:', error)
    }
  }, [])

  // Refetch when the period or host filter changes, as well as on mount.
  usePageData(() => { fetchData() }, [period, selectedHost])

  usePageData(fetchRealtime)
  useEffect(() => {
    const interval = setInterval(fetchRealtime, 15000)
    return () => clearInterval(interval)
  }, [fetchRealtime])

  // The countdown display is reset where the setting changes (toggle, interval), so this effect
  // only restarts the timer.
  const setAutoRefreshEnabled = (enabled: boolean) => {
    setAutoRefresh(enabled)
    if (enabled) setCountdown(refreshInterval)
  }
  const changeRefreshInterval = (seconds: number) => {
    setRefreshInterval(seconds)
    setCountdown(seconds)
  }

  useEffect(() => {
    if (!autoRefresh) return

    countdownRef.current = refreshInterval

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        icon={HeaderIcon}
        title="Analytics"
        description={
          selectedHostName
            ? `Traffic, security, and performance for ${selectedHostName}`
            : 'Traffic, security, and performance across all hosts'
        }
        actions={
          <>
            <Select
              value={selectedHost || ALL_HOSTS}
              onValueChange={(v) => setSelectedHost(v === ALL_HOSTS ? '' : v)}
            >
              <SelectTrigger aria-label="Filter analytics by host" className="max-w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_HOSTS}>All hosts</SelectItem>
                {hosts.map((h) => (
                  <SelectItem key={h.id} value={h.id}>
                    {h.domain_names?.[0] ?? h.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Tabs value={period} onValueChange={(v) => setPeriod(v as Period)}>
              <TabsList aria-label="Period">
                {PERIODS.map((p) => (
                  <TabsTrigger key={p} value={p} className="px-2.5 py-1">
                    {p}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Button
              variant="outline"
              size="lg"
              onClick={() => fetchData()}
              disabled={isRefreshing}
            >
              <RefreshCw className={isRefreshing ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <div className="flex h-9 items-center gap-2 rounded-lg border border-input px-3">
              <Switch
                id="analytics-auto-refresh"
                checked={autoRefresh}
                onCheckedChange={setAutoRefreshEnabled}
                aria-label="Auto-refresh"
              />
              <label
                htmlFor="analytics-auto-refresh"
                className="text-sm font-medium tabular-nums text-muted-foreground"
              >
                {autoRefresh ? `${countdown}s` : 'Auto'}
              </label>
              {autoRefresh && (
                <Select
                  value={String(refreshInterval)}
                  onValueChange={(v) => changeRefreshInterval(Number(v))}
                >
                  <SelectTrigger size="sm" aria-label="Auto-refresh interval" className="border-0 px-1.5 text-xs dark:bg-transparent">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15s</SelectItem>
                    <SelectItem value="30">30s</SelectItem>
                    <SelectItem value="60">1m</SelectItem>
                    <SelectItem value="300">5m</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>
          </>
        }
      />

      {isLoading ? (
        <ContentSkeleton stats={5} rows={3} />
      ) : !data ? (
        <LoadError what="analytics" onRetry={() => fetchData()} />
      ) : (
        <>
          {/* Real-time Stats Bar */}
          {realtime && (
            <div className="flex flex-wrap items-center gap-4 sm:gap-6 rounded-xl border bg-card px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-sm font-medium">Live</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Zap className="h-4 w-4 text-yellow-700 dark:text-yellow-400" />
                <span className="text-muted-foreground">Req/min:</span>
                <span className="font-mono font-medium">{realtime.requests_per_minute}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Users className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                <span className="text-muted-foreground">Active:</span>
                <span className="font-mono font-medium">{realtime.active_visitors}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Activity className="h-4 w-4 text-green-600 dark:text-green-400" />
                <span className="text-muted-foreground">5 min:</span>
                <span className="font-mono font-medium">{realtime.requests_last_5min}</span>
              </div>
              {realtime.recent_errors > 0 && (
                <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                  <AlertTriangle className="h-4 w-4" />
                  <span>{realtime.recent_errors} errors</span>
                </div>
              )}
            </div>
          )}

          {/* Tabbed Content */}
          <Tabs defaultValue="overview" className="space-y-6">
            <TabsList className="w-full justify-start gap-1 overflow-x-auto sm:w-fit">
              <TabsTrigger value="overview" className="shrink-0 gap-1.5">
                <BarChart3 className="h-4 w-4" />
                <span>Overview</span>
              </TabsTrigger>
              <TabsTrigger value="trends" className="shrink-0 gap-1.5">
                <TrendingUp className="h-4 w-4" />
                <span>Trends</span>
              </TabsTrigger>
              <TabsTrigger value="traffic" className="shrink-0 gap-1.5">
                <Activity className="h-4 w-4" />
                <span>Traffic</span>
              </TabsTrigger>
              <TabsTrigger value="logs" className="shrink-0 gap-1.5">
                <FileText className="h-4 w-4" />
                <span>Logs</span>
              </TabsTrigger>
              <TabsTrigger value="security" className="shrink-0 gap-1.5">
                <Shield className="h-4 w-4" />
                <span>Security</span>
              </TabsTrigger>
              <TabsTrigger value="performance" className="shrink-0 gap-1.5">
                <Gauge className="h-4 w-4" />
                <span>Performance</span>
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
                onSelectHost={setSelectedHost}
              />
            </TabsContent>

            <TabsContent value="trends" className="space-y-6">
              <TrendsTab
                data={trends}
                isLoading={trendsLoading}
                failed={trendsFailed}
                onRetry={fetchTrends}
                formatNumber={formatNumber}
                formatBytes={formatBytes}
              />
            </TabsContent>

            <TabsContent value="logs">
              <LogsTab
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
        </>
      )}
    </div>
  )
}
