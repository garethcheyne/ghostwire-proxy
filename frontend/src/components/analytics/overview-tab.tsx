'use client'

import {
  Activity,
  Users,
  Globe,
  Clock,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const STATUS_COLORS: Record<string, string> = {
  '2xx': '#10b981',
  '3xx': '#3b82f6',
  '4xx': '#f59e0b',
  '5xx': '#ef4444',
}

interface OverviewTabProps {
  data: {
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
  }
  formatNumber: (n: number) => string
  formatBytes: (b: number) => string
  formatResponseTime: (ms: number | null) => string
}

export function OverviewTab({ data, formatNumber, formatBytes, formatResponseTime }: OverviewTabProps) {
  const statusData = [
    { name: '2xx Success', value: data.status_breakdown.status_2xx, color: STATUS_COLORS['2xx'] },
    { name: '3xx Redirect', value: data.status_breakdown.status_3xx, color: STATUS_COLORS['3xx'] },
    { name: '4xx Client Error', value: data.status_breakdown.status_4xx, color: STATUS_COLORS['4xx'] },
    { name: '5xx Server Error', value: data.status_breakdown.status_5xx, color: STATUS_COLORS['5xx'] },
  ].filter(d => d.value > 0)

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
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

      {/* Traffic Over Time */}
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
            <XAxis dataKey="timestamp" tick={{ fontSize: 12 }} className="text-muted-foreground" />
            <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
            />
            <Legend />
            <Area type="monotone" dataKey="requests" name="Requests" stroke="#3b82f6" fill="url(#requestsGradient)" strokeWidth={2} />
            <Area type="monotone" dataKey="unique_visitors" name="Unique Visitors" stroke="#10b981" fill="url(#visitorsGradient)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Status Code Breakdown */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Status Code Breakdown</h3>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width="50%" height={200}>
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
            <div className="space-y-3">
              {statusData.map((entry) => (
                <div key={entry.name} className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: entry.color }} />
                  <div>
                    <p className="text-sm font-medium">{entry.name}</p>
                    <p className="text-xs text-muted-foreground">{formatNumber(entry.value)} requests</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Period Summary</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Total Bandwidth</p>
              <p className="text-lg font-bold">{formatBytes(data.total_bytes_transferred)}</p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Success Rate</p>
              <p className="text-lg font-bold text-green-500">
                {data.total_requests > 0
                  ? ((data.status_breakdown.status_2xx / data.total_requests) * 100).toFixed(1)
                  : '0'}%
              </p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Client Errors</p>
              <p className="text-lg font-bold text-yellow-500">{formatNumber(data.status_breakdown.status_4xx)}</p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Server Errors</p>
              <p className="text-lg font-bold text-red-500">{formatNumber(data.status_breakdown.status_5xx)}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
