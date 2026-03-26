'use client'

import {
  ShieldX,
  AlertTriangle,
} from 'lucide-react'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

interface PerformanceTabProps {
  data: {
    time_series: Array<{
      timestamp: string
      requests: number
      bytes_sent: number
      bytes_received: number
      avg_response_time: number | null
    }>
    errors_by_host: Array<{
      host_id: string
      host_name: string
      total_errors: number
      status_codes: Record<string, number>
    }>
    errors_by_status: Array<{
      status: number
      count: number
    }>
    top_hosts: Array<{
      host_name: string
      avg_response_time: number | null
      error_rate: number
    }>
  }
  formatNumber: (n: number) => string
  formatBytes: (b: number) => string
  formatResponseTime: (ms: number | null) => string
}

export function PerformanceTab({ data, formatNumber, formatBytes, formatResponseTime }: PerformanceTabProps) {
  const responseTimeData = data.time_series.filter(d => d.avg_response_time !== null)

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

  // Sort hosts by response time descending for the performance table
  const hostsByResponseTime = [...data.top_hosts]
    .filter(h => h.avg_response_time !== null)
    .sort((a, b) => (b.avg_response_time || 0) - (a.avg_response_time || 0))

  return (
    <div className="space-y-6">
      {/* Response Time Trend */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Response Time Trend</h3>
        {responseTimeData.length === 0 ? (
          <div className="flex h-[200px] items-center justify-center text-muted-foreground text-sm">
            No response time data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={responseTimeData}>
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
              <Line type="monotone" dataKey="avg_response_time" stroke="#f59e0b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Bandwidth Over Time */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="font-semibold mb-4">Bandwidth Over Time</h3>
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={data.time_series}>
            <defs>
              <linearGradient id="sentGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="receivedGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis dataKey="timestamp" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => formatBytes(v)} />
            <Tooltip
              formatter={(value: number, name: string) => [formatBytes(value), name]}
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
            />
            <Legend />
            <Area type="monotone" dataKey="bytes_sent" name="Sent" stroke="#3b82f6" fill="url(#sentGradient)" strokeWidth={2} />
            <Area type="monotone" dataKey="bytes_received" name="Received" stroke="#10b981" fill="url(#receivedGradient)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Host Performance Ranking */}
      {hostsByResponseTime.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="font-semibold mb-4">Host Performance Ranking</h3>
          <p className="text-xs text-muted-foreground mb-4">Sorted by average response time (slowest first)</p>
          <div className="space-y-3">
            {hostsByResponseTime.map((host, idx) => {
              const maxTime = hostsByResponseTime[0]?.avg_response_time || 1
              const pct = ((host.avg_response_time || 0) / maxTime) * 100
              const isHealthy = (host.avg_response_time || 0) < 500 && host.error_rate < 2
              const isWarning = (host.avg_response_time || 0) >= 500 || host.error_rate >= 2
              const isCritical = (host.avg_response_time || 0) >= 2000 || host.error_rate >= 10
              const barColor = isCritical ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : 'bg-green-500'
              return (
                <div key={idx}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium" data-private="domain">{host.host_name}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-muted-foreground">
                        {formatResponseTime(host.avg_response_time)}
                      </span>
                      <span className={`text-xs font-mono ${
                        host.error_rate > 5 ? 'text-red-500' : host.error_rate > 1 ? 'text-yellow-500' : 'text-green-500'
                      }`}>
                        {host.error_rate.toFixed(1)}% err
                      </span>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Error Breakdown */}
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
                        <span className="text-sm font-medium truncate" data-private="domain">{host.host_name}</span>
                        <span className="text-xs font-mono text-muted-foreground">{formatNumber(host.total_errors)} errors</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden mb-1">
                        <div className="h-full rounded-full bg-red-500 transition-all" style={{ width: `${percentage}%` }} />
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
                      <span className="text-xs font-mono text-muted-foreground w-16 text-right">{formatNumber(item.count)}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
