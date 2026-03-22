'use client'

import { useState, useEffect } from 'react'
import {
  Activity,
  Server,
  Database,
  HardDrive,
  Cpu,
  MemoryStick,
  Network,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Container,
  Gauge,
  ArrowUpDown,
} from 'lucide-react'
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
import api from '@/lib/api'

interface ServiceHealth {
  status: 'healthy' | 'unhealthy' | 'unknown'
  uptime?: number
  error?: string
  container_status?: string
  process?: boolean
}

interface ContainerInfo {
  name: string
  id?: string
  status: string
  cpu_percent?: number
  memory_used?: number
  memory_limit?: number
  memory_percent?: number
  network_rx_bytes?: number
  network_tx_bytes?: number
  started_at?: string
  uptime?: string
  error?: string
}

interface SystemStatus {
  timestamp: string
  services: Record<string, ServiceHealth>
  resources: {
    cpu: { usage: number; cores: number }
    memory: { used: number; total: number; percent: number; available: number }
    disk: { used: number; total: number; percent: number; free: number }
    network?: {
      bytes_sent_total?: number
      bytes_recv_total?: number
      bytes_sent_rate?: number
      bytes_recv_rate?: number
    }
  }
  containers: ContainerInfo[]
  database: {
    size_bytes?: number
    connections?: number
    table_counts?: Record<string, number>
    error?: string
  }
}

interface MetricsPoint {
  timestamp: string
  cpu_usage?: number
  memory_percent?: number
  memory_used?: number
  disk_percent?: number
  request_count?: number
}

interface ThroughputPoint {
  timestamp: string
  requests: number
  bytes_sent: number
  bytes_received: number
}

export default function SystemMonitorPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [metrics, setMetrics] = useState<MetricsPoint[]>([])
  const [throughput, setThroughput] = useState<ThroughputPoint[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [period, setPeriod] = useState<'1h' | '6h' | '24h' | '7d'>('24h')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAllData()
    const interval = setInterval(fetchStatus, 30000) // Refresh status every 30s
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchMetrics()
    fetchThroughput()
  }, [period])

  const fetchAllData = async () => {
    setIsRefreshing(true)
    await Promise.all([fetchStatus(), fetchMetrics(), fetchThroughput()])
    setIsRefreshing(false)
  }

  const fetchStatus = async () => {
    try {
      const response = await api.get('/api/system/status')
      setStatus(response.data)
      setError(null)
    } catch (err: any) {
      console.error('Failed to fetch system status:', err)
      setError(err.message || 'Failed to fetch system status')
    } finally {
      setIsLoading(false)
    }
  }

  const fetchMetrics = async () => {
    try {
      const response = await api.get(`/api/system/metrics?period=${period}`)
      setMetrics(response.data)
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  const fetchThroughput = async () => {
    try {
      const response = await api.get(`/api/system/throughput?period=${period}`)
      setThroughput(response.data)
    } catch (err) {
      console.error('Failed to fetch throughput:', err)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)

    if (days > 0) return `${days}d ${hours}h`
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts)
    if (period === '1h' || period === '6h') {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' })
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />
      case 'unhealthy':
        return <XCircle className="h-5 w-5 text-red-500" />
      default:
        return <AlertCircle className="h-5 w-5 text-yellow-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500/10 border-green-500/20 text-green-500'
      case 'unhealthy':
        return 'bg-red-500/10 border-red-500/20 text-red-500'
      default:
        return 'bg-yellow-500/10 border-yellow-500/20 text-yellow-500'
    }
  }

  const getPercentColor = (percent: number) => {
    if (percent >= 90) return 'text-red-500'
    if (percent >= 70) return 'text-yellow-500'
    return 'text-green-500'
  }

  const getProgressColor = (percent: number) => {
    if (percent >= 90) return 'bg-red-500'
    if (percent >= 70) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading system status...</div>
      </div>
    )
  }

  if (error && !status) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center">
          <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <p className="text-muted-foreground">{error}</p>
          <button
            onClick={fetchAllData}
            className="mt-4 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">System Monitor</h1>
          <p className="text-muted-foreground">
            Real-time system health and resource monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-input overflow-hidden">
            {(['1h', '6h', '24h', '7d'] as const).map((p) => (
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
            onClick={fetchAllData}
            disabled={isRefreshing}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Service Health Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {status && Object.entries(status.services).map(([name, service]) => (
          <div
            key={name}
            className={`rounded-xl border p-4 ${getStatusColor(service.status)}`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {getStatusIcon(service.status)}
                <span className="font-semibold capitalize">{name}</span>
              </div>
              <span className="text-xs uppercase">{service.status}</span>
            </div>
            {service.uptime && (
              <div className="mt-2 flex items-center gap-1 text-xs opacity-80">
                <Clock className="h-3 w-3" />
                Uptime: {formatUptime(service.uptime)}
              </div>
            )}
            {service.error && (
              <p className="mt-2 text-xs opacity-80 truncate" title={service.error}>
                {service.error}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Resource Usage Overview */}
      {status && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {/* CPU */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-blue-500" />
                <span className="font-semibold">CPU</span>
              </div>
              <span className={`text-lg font-bold ${getPercentColor(status.resources.cpu.usage)}`}>
                {status.resources.cpu.usage}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${getProgressColor(status.resources.cpu.usage)}`}
                style={{ width: `${status.resources.cpu.usage}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {status.resources.cpu.cores} cores available
            </p>
          </div>

          {/* Memory */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <MemoryStick className="h-5 w-5 text-purple-500" />
                <span className="font-semibold">Memory</span>
              </div>
              <span className={`text-lg font-bold ${getPercentColor(status.resources.memory.percent)}`}>
                {status.resources.memory.percent}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${getProgressColor(status.resources.memory.percent)}`}
                style={{ width: `${status.resources.memory.percent}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {formatBytes(status.resources.memory.used)} / {formatBytes(status.resources.memory.total)}
            </p>
          </div>

          {/* Disk */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-orange-500" />
                <span className="font-semibold">Disk</span>
              </div>
              <span className={`text-lg font-bold ${getPercentColor(status.resources.disk.percent)}`}>
                {status.resources.disk.percent}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${getProgressColor(status.resources.disk.percent)}`}
                style={{ width: `${status.resources.disk.percent}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {formatBytes(status.resources.disk.free)} free
            </p>
          </div>

          {/* Network */}
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Network className="h-5 w-5 text-cyan-500" />
                <span className="font-semibold">Network</span>
              </div>
              <ArrowUpDown className="h-4 w-4 text-muted-foreground" />
            </div>
            {status.resources.network ? (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Sent</span>
                  <span className="font-mono">
                    {formatBytes(status.resources.network.bytes_sent_rate || 0)}/s
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-muted-foreground">Recv</span>
                  <span className="font-mono">
                    {formatBytes(status.resources.network.bytes_recv_rate || 0)}/s
                  </span>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No data</p>
            )}
          </div>
        </div>
      )}

      {/* Resource History Chart */}
      {metrics.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Resource Usage Over Time</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={metrics}>
              <defs>
                <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="memoryGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="diskGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatTimestamp}
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => `${v}%`}
                domain={[0, 100]}
                className="text-muted-foreground"
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
                labelFormatter={(label) => new Date(label).toLocaleString()}
                formatter={(value: number) => [`${value?.toFixed(1)}%`]}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="cpu_usage"
                name="CPU"
                stroke="#3b82f6"
                fill="url(#cpuGradient)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="memory_percent"
                name="Memory"
                stroke="#8b5cf6"
                fill="url(#memoryGradient)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="disk_percent"
                name="Disk"
                stroke="#f97316"
                fill="url(#diskGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Traffic Throughput Chart */}
      {throughput.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Traffic Throughput</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={throughput}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatTimestamp}
                tick={{ fontSize: 12 }}
              />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
                labelFormatter={(label) => new Date(label).toLocaleString()}
              />
              <Legend />
              <Bar dataKey="requests" name="Requests" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Containers Table */}
      {status && status.containers.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Container className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Docker Containers</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Container
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Status
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    CPU
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Memory
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Network I/O
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Uptime
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {status.containers.map((container) => (
                  <tr key={container.name} className="hover:bg-muted/50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Container className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">{container.name}</span>
                        {container.id && (
                          <span className="text-xs text-muted-foreground font-mono">
                            {container.id}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                        container.status === 'running'
                          ? 'bg-green-500/10 text-green-500'
                          : container.status === 'exited'
                          ? 'bg-red-500/10 text-red-500'
                          : 'bg-yellow-500/10 text-yellow-500'
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${
                          container.status === 'running' ? 'bg-green-500' : 'bg-red-500'
                        }`} />
                        {container.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {container.cpu_percent !== undefined ? (
                        <span className={`font-mono ${getPercentColor(container.cpu_percent)}`}>
                          {container.cpu_percent.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {container.memory_used !== undefined ? (
                        <div>
                          <span className="font-mono">{formatBytes(container.memory_used)}</span>
                          {container.memory_limit && container.memory_limit > 0 && (
                            <span className="text-xs text-muted-foreground ml-1">
                              / {formatBytes(container.memory_limit)}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {container.network_rx_bytes !== undefined ? (
                        <div className="text-xs font-mono">
                          <span className="text-green-500">{formatBytes(container.network_rx_bytes)}</span>
                          <span className="text-muted-foreground mx-1">/</span>
                          <span className="text-blue-500">{formatBytes(container.network_tx_bytes || 0)}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {container.uptime ? (
                        <span className="text-sm text-muted-foreground">{container.uptime}</span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Database Stats */}
      {status && status.database && !status.database.error && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Database className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Database Statistics</h3>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">Database Size</p>
              <p className="text-2xl font-bold mt-1">
                {formatBytes(status.database.size_bytes || 0)}
              </p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">Active Connections</p>
              <p className="text-2xl font-bold mt-1">
                {status.database.connections || 0}
              </p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-sm text-muted-foreground">Table Counts</p>
              <div className="mt-1 space-y-1">
                {status.database.table_counts &&
                  Object.entries(status.database.table_counts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 4)
                    .map(([table, count]) => (
                      <div key={table} className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{table}</span>
                        <span className="font-mono">{count.toLocaleString()}</span>
                      </div>
                    ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Empty State for Metrics */}
      {metrics.length === 0 && !isLoading && (
        <div className="rounded-xl border border-dashed border-border bg-card/50 p-8 text-center">
          <Gauge className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="font-semibold mb-2">No Historical Metrics</h3>
          <p className="text-sm text-muted-foreground mb-4">
            System metrics are collected periodically. Data will appear here once collection begins.
          </p>
          <button
            onClick={async () => {
              try {
                await api.post('/api/system/collect')
                await fetchMetrics()
              } catch (err) {
                console.error('Failed to trigger collection:', err)
              }
            }}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm"
          >
            Collect Metrics Now
          </button>
        </div>
      )}
    </div>
  )
}
