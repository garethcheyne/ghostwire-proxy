'use client'

import {
  Activity,
  Users,
  Globe,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import { StatCard } from '@/components/stat-card'
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
        <StatCard
          title="Total Requests"
          value={formatNumber(data.total_requests)}
          icon={Activity}
          trend={data.requests_change_percent !== null ? (data.requests_change_percent >= 0 ? 'up' : 'down') : null}
          trendValue={data.requests_change_percent !== null ? `${Math.abs(data.requests_change_percent)}% vs previous period` : undefined}
        />
        <StatCard
          title="Unique Visitors"
          value={formatNumber(data.total_unique_visitors)}
          icon={Users}
          trend={data.visitors_change_percent !== null ? (data.visitors_change_percent >= 0 ? 'up' : 'down') : null}
          trendValue={data.visitors_change_percent !== null ? `${Math.abs(data.visitors_change_percent)}% vs previous period` : undefined}
        />
        <StatCard title="Data Transferred" value={formatBytes(data.total_bytes_transferred)} icon={Globe} />
        <StatCard title="Avg Response Time" value={formatResponseTime(data.avg_response_time)} icon={Clock} />
        <StatCard
          title="Error Rate"
          value={`${data.error_rate.toFixed(2)}%`}
          icon={AlertTriangle}
          tone={data.error_rate > 5 ? 'danger' : data.error_rate > 1 ? 'warning' : 'success'}
        />
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
                backgroundColor: 'var(--card)',
                border: '1px solid var(--border)',
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
                  formatter={(value) => formatNumber(Number(value))}
                  contentStyle={{
                    backgroundColor: 'var(--card)',
                    border: '1px solid var(--border)',
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
              <p className="text-lg font-bold text-green-600 dark:text-green-400">
                {data.total_requests > 0
                  ? ((data.status_breakdown.status_2xx / data.total_requests) * 100).toFixed(1)
                  : '0'}%
              </p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Client Errors</p>
              <p className="text-lg font-bold text-yellow-700 dark:text-yellow-400">{formatNumber(data.status_breakdown.status_4xx)}</p>
            </div>
            <div className="rounded-lg bg-muted/50 p-4">
              <p className="text-xs text-muted-foreground mb-1">Server Errors</p>
              <p className="text-lg font-bold text-red-600 dark:text-red-400">{formatNumber(data.status_breakdown.status_5xx)}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
