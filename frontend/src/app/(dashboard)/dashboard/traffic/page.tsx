'use client'

import { useState, useEffect } from 'react'
import {
  Activity,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Clock,
  Globe,
  ArrowRight,
  Trash2,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { IpAddress } from '@/components/ip-address'
import type { TrafficLog, ProxyHost } from '@/types'

interface TrafficStats {
  requests_today: number
  requests_this_week: number
  total_bytes_sent: number
  total_bytes_received: number
  avg_response_time: number
}

export default function TrafficPage() {
  const confirm = useConfirm()
  const [logs, setLogs] = useState<TrafficLog[]>([])
  const [hosts, setHosts] = useState<ProxyHost[]>([])
  const [stats, setStats] = useState<TrafficStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedHost, setSelectedHost] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const limit = 50

  // Detail view
  const [selectedLog, setSelectedLog] = useState<TrafficLog | null>(null)

  useEffect(() => {
    fetchData()
  }, [])

  useEffect(() => {
    fetchLogs()
  }, [page, selectedHost, selectedStatus])

  const fetchData = async () => {
    try {
      const [hostsRes, statsRes] = await Promise.all([
        api.get('/api/proxy-hosts'),
        api.get('/api/traffic/stats'),
      ])
      setHosts(hostsRes.data)
      setStats(statsRes.data)
    } catch (error) {
      console.error('Failed to fetch data:', error)
    }
  }

  const fetchLogs = async () => {
    setIsRefreshing(true)
    try {
      const params = new URLSearchParams({
        skip: ((page - 1) * limit).toString(),
        limit: limit.toString(),
      })
      if (selectedHost) params.append('proxy_host_id', selectedHost)
      if (selectedStatus) params.append('status_code', selectedStatus)

      const response = await api.get(`/api/traffic?${params}`)
      setLogs(response.data.items || response.data)
      setTotalPages(Math.ceil((response.data.total || response.data.length) / limit))
    } catch (error) {
      console.error('Failed to fetch logs:', error)
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }

  const handleRefresh = () => {
    fetchLogs()
    fetchData()
  }

  const handlePurgeLogs = async () => {
    if (!(await confirm({ description: 'Are you sure you want to purge ALL traffic logs? This cannot be undone.', variant: 'destructive' }))) return
    try {
      await api.delete('/api/traffic')
      setLogs([])
      fetchData()
    } catch (error) {
      console.error('Failed to purge traffic logs:', error)
    }
  }

  const handleDeleteLog = async (logId: string) => {
    try {
      await api.delete(`/api/traffic/${logId}`)
      setLogs(logs.filter(l => l.id !== logId))
    } catch (error) {
      console.error('Failed to delete log:', error)
    }
  }

  const getStatusColor = (status: number) => {
    if (status >= 500) return 'text-red-500 bg-red-500/10'
    if (status >= 400) return 'text-yellow-500 bg-yellow-500/10'
    if (status >= 300) return 'text-blue-500 bg-blue-500/10'
    return 'text-green-500 bg-green-500/10'
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatResponseTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading traffic logs...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Traffic Logs</h1>
          <p className="text-muted-foreground">
            Monitor requests through your proxy hosts
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handlePurgeLogs}
            className="flex items-center gap-2 rounded-lg border border-red-500/30 px-4 py-2 text-sm font-medium text-red-500 hover:bg-red-500/10"
          >
            <Trash2 className="h-4 w-4" />
            Purge All
          </button>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Requests Today</p>
            <p className="text-2xl font-bold">{stats.requests_today.toLocaleString()}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">This Week</p>
            <p className="text-2xl font-bold">{stats.requests_this_week.toLocaleString()}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Data Transferred</p>
            <p className="text-2xl font-bold">
              {formatBytes(stats.total_bytes_sent + stats.total_bytes_received)}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Avg Response Time</p>
            <p className="text-2xl font-bold">{formatResponseTime(stats.avg_response_time)}</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            placeholder="Search by URI or IP..."
          />
        </div>
        <select
          value={selectedHost}
          onChange={(e) => {
            setSelectedHost(e.target.value)
            setPage(1)
          }}
          className="px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">All Hosts</option>
          {hosts.map((host) => (
            <option key={host.id} value={host.id}>
              {host.domain_names[0]}
            </option>
          ))}
        </select>
        <select
          value={selectedStatus}
          onChange={(e) => {
            setSelectedStatus(e.target.value)
            setPage(1)
          }}
          className="px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">All Status Codes</option>
          <option value="200">2xx Success</option>
          <option value="300">3xx Redirect</option>
          <option value="400">4xx Client Error</option>
          <option value="500">5xx Server Error</option>
        </select>
      </div>

      {/* Logs Table */}
      <div className="rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Time
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Host
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Method
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  URI
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Client IP
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Response Time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                    <Activity className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No traffic logs found</p>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr
                    key={log.id}
                    className="hover:bg-muted/50 cursor-pointer"
                    onClick={() => setSelectedLog(log)}
                  >
                    <td className="px-4 py-3 text-sm">
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <div className="flex items-center gap-1">
                        <Globe className="h-3 w-3 text-muted-foreground" />
                        <span className="font-medium">{log.host_name || '-'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                          log.request_method === 'GET'
                            ? 'bg-green-500/10 text-green-500'
                            : log.request_method === 'POST'
                            ? 'bg-blue-500/10 text-blue-500'
                            : log.request_method === 'PUT'
                            ? 'bg-yellow-500/10 text-yellow-500'
                            : log.request_method === 'DELETE'
                            ? 'bg-red-500/10 text-red-500'
                            : 'bg-gray-500/10 text-gray-500'
                        }`}
                      >
                        {log.request_method}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <code className="text-xs">{log.request_uri}</code>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(
                          log.status
                        )}`}
                      >
                        {log.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm font-mono">
                      <div className="flex items-center gap-1.5">
                        <IpAddress ip={log.client_ip} countryCode={log.country_code} countryName={log.country_name} />
                        {log.city && (
                          <span className="text-[10px] text-muted-foreground truncate max-w-[100px]" title={log.city}>
                            {log.city}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {log.response_time ? formatResponseTime(log.response_time) : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteLog(log.id); }}
                        className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground hover:text-red-500"
                        title="Delete log"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(page - 1)}
                disabled={page === 1}
                className="rounded-lg p-2 hover:bg-muted disabled:opacity-50"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page === totalPages}
                className="rounded-lg p-2 hover:bg-muted disabled:opacity-50"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Log Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold">Request Details</h2>
                <button
                  onClick={() => setSelectedLog(null)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  ×
                </button>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Timestamp</p>
                  <p className="font-medium">
                    {new Date(selectedLog.timestamp).toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Client IP</p>
                  <div className="flex items-center gap-2">
                    <IpAddress ip={selectedLog.client_ip} countryCode={selectedLog.country_code} countryName={selectedLog.country_name} />
                    <span className="text-sm text-muted-foreground">
                      {[selectedLog.city, selectedLog.country_name].filter(Boolean).join(', ')}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Method</p>
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                      selectedLog.request_method === 'GET'
                        ? 'bg-green-500/10 text-green-500'
                        : selectedLog.request_method === 'POST'
                        ? 'bg-blue-500/10 text-blue-500'
                        : 'bg-gray-500/10 text-gray-500'
                    }`}
                  >
                    {selectedLog.request_method}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status Code</p>
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(
                      selectedLog.status
                    )}`}
                  >
                    {selectedLog.status}
                  </span>
                </div>
              </div>

              <div>
                <p className="text-sm text-muted-foreground mb-1">URI</p>
                <code className="block p-3 rounded-lg bg-muted text-sm break-all">
                  {selectedLog.request_uri}
                </code>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Response Time</p>
                  <p className="font-medium">{selectedLog.response_time ? formatResponseTime(selectedLog.response_time) : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Bytes Sent</p>
                  <p className="font-medium">{selectedLog.bytes_sent ? formatBytes(selectedLog.bytes_sent) : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Bytes Received</p>
                  <p className="font-medium">{selectedLog.bytes_received ? formatBytes(selectedLog.bytes_received) : '-'}</p>
                </div>
              </div>

              {selectedLog.user_agent && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">User Agent</p>
                  <code className="block p-3 rounded-lg bg-muted text-sm break-all">
                    {selectedLog.user_agent}
                  </code>
                </div>
              )}

              {selectedLog.referer && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Referer</p>
                  <code className="block p-3 rounded-lg bg-muted text-sm break-all">
                    {selectedLog.referer}
                  </code>
                </div>
              )}
            </div>

            <div className="border-t border-border p-4 flex justify-end">
              <button
                onClick={() => setSelectedLog(null)}
                className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
