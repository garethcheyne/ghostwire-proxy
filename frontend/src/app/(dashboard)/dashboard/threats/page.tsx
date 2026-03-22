'use client'

import { useState, useEffect } from 'react'
import {
  AlertTriangle,
  Shield,
  ShieldBan,
  ShieldCheck,
  Eye,
  Ban,
  Unlock,
  Loader2,
  Search,
  ChevronDown,
} from 'lucide-react'
import api from '@/lib/api'

interface ThreatEvent {
  id: string
  proxy_host_id: string | null
  client_ip: string
  rule_id: string | null
  rule_name: string | null
  category: string
  severity: string
  action_taken: string
  request_method: string | null
  request_uri: string | null
  matched_payload: string | null
  timestamp: string
}

interface ThreatActor {
  id: string
  ip_address: string
  total_events: number
  threat_score: number
  first_seen: string
  last_seen: string
  current_status: string
  temp_block_until: string | null
  perm_blocked_at: string | null
  firewall_banned_at: string | null
  notes: string | null
}

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

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

const statusColors: Record<string, string> = {
  monitored: 'bg-slate-500/10 text-slate-400',
  warned: 'bg-yellow-500/10 text-yellow-500',
  temp_blocked: 'bg-orange-500/10 text-orange-500',
  perm_blocked: 'bg-red-500/10 text-red-500',
  firewall_banned: 'bg-purple-500/10 text-purple-500',
}

const categoryColors: Record<string, string> = {
  sqli: 'bg-red-500/10 text-red-500',
  xss: 'bg-orange-500/10 text-orange-500',
  path_traversal: 'bg-yellow-500/10 text-yellow-500',
  rce: 'bg-purple-500/10 text-purple-500',
  scanner: 'bg-blue-500/10 text-blue-500',
}

export default function ThreatsPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'events' | 'actors'>('overview')
  const [stats, setStats] = useState<ThreatStats | null>(null)
  const [events, setEvents] = useState<ThreatEvent[]>([])
  const [actors, setActors] = useState<ThreatActor[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filterSeverity, setFilterSeverity] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterIp, setFilterIp] = useState('')

  useEffect(() => {
    fetchData()
  }, [activeTab, filterSeverity, filterCategory, filterStatus, filterIp])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'overview') {
        const res = await api.get('/api/waf/stats')
        setStats(res.data)
      } else if (activeTab === 'events') {
        const params = new URLSearchParams()
        if (filterSeverity) params.set('severity', filterSeverity)
        if (filterCategory) params.set('category', filterCategory)
        if (filterIp) params.set('client_ip', filterIp)
        const res = await api.get(`/api/waf/events?${params}`)
        setEvents(res.data)
      } else if (activeTab === 'actors') {
        const params = new URLSearchParams()
        if (filterStatus) params.set('status', filterStatus)
        const res = await api.get(`/api/waf/actors?${params}`)
        setActors(res.data)
      }
    } catch (error) {
      console.error('Failed to fetch threat data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleBlockIp = async (ip: string) => {
    if (!confirm(`Block IP ${ip} permanently?`)) return
    try {
      await api.post(`/api/waf/actors/${encodeURIComponent(ip)}/block`)
      fetchData()
    } catch (error) {
      console.error('Failed to block IP:', error)
    }
  }

  const handleUnblockIp = async (ip: string) => {
    if (!confirm(`Unblock IP ${ip}?`)) return
    try {
      await api.post(`/api/waf/actors/${encodeURIComponent(ip)}/unblock`)
      fetchData()
    } catch (error) {
      console.error('Failed to unblock IP:', error)
    }
  }

  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleString()
    } catch {
      return d
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Threat Detection</h1>
        <p className="text-muted-foreground">
          Monitor threats, events, and manage IP reputation
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(['overview', 'events', 'actors'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'bg-background shadow-sm'
                : 'hover:bg-background/50 text-muted-foreground'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex h-96 items-center justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      ) : activeTab === 'overview' && stats ? (
        <div className="space-y-6">
          {/* Stats Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between pb-2">
                <p className="text-sm font-medium text-muted-foreground">Total Events</p>
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-2xl font-bold">{stats.total_events.toLocaleString()}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between pb-2">
                <p className="text-sm font-medium text-muted-foreground">Today</p>
                <Shield className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-2xl font-bold">{stats.events_today.toLocaleString()}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between pb-2">
                <p className="text-sm font-medium text-muted-foreground">Threat Actors</p>
                <Eye className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-2xl font-bold">{stats.total_actors}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between pb-2">
                <p className="text-sm font-medium text-muted-foreground">Blocked IPs</p>
                <ShieldBan className="h-4 w-4 text-red-500" />
              </div>
              <p className="text-2xl font-bold text-red-500">{stats.blocked_actors}</p>
            </div>
          </div>

          {/* Severity Breakdown + Top Categories */}
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="text-lg font-semibold mb-4">Severity Breakdown</h3>
              <div className="space-y-3">
                {Object.entries(stats.severity_breakdown).map(([sev, count]) => (
                  <div key={sev} className="flex items-center justify-between">
                    <span className={`text-sm px-2 py-0.5 rounded-full border capitalize ${severityColors[sev] || ''}`}>
                      {sev}
                    </span>
                    <span className="text-sm font-medium">{count}</span>
                  </div>
                ))}
                {Object.keys(stats.severity_breakdown).length === 0 && (
                  <p className="text-sm text-muted-foreground">No events recorded yet</p>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="text-lg font-semibold mb-4">Top Categories</h3>
              <div className="space-y-3">
                {stats.top_categories.map((cat) => (
                  <div key={cat.category} className="flex items-center justify-between">
                    <span className={`text-sm px-2 py-0.5 rounded-full capitalize ${categoryColors[cat.category] || 'bg-muted'}`}>
                      {cat.category.replace('_', ' ')}
                    </span>
                    <span className="text-sm font-medium">{cat.count}</span>
                  </div>
                ))}
                {stats.top_categories.length === 0 && (
                  <p className="text-sm text-muted-foreground">No events recorded yet</p>
                )}
              </div>
            </div>
          </div>

          {/* Top Threat Actors */}
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="text-lg font-semibold mb-4">Top Threat Actors</h3>
            {stats.top_actors.length === 0 ? (
              <p className="text-sm text-muted-foreground">No threat actors detected yet</p>
            ) : (
              <div className="space-y-2">
                {stats.top_actors.map((actor) => (
                  <div key={actor.ip} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                    <div className="flex items-center gap-3">
                      <code className="text-sm font-mono">{actor.ip}</code>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${statusColors[actor.status] || statusColors.monitored}`}>
                        {actor.status.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-muted-foreground">{actor.events} events</span>
                      <span className="text-sm font-medium">Score: {actor.score}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : activeTab === 'events' ? (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={filterIp}
                onChange={(e) => setFilterIp(e.target.value)}
                placeholder="Filter by IP..."
                className="w-48 pl-9 pr-4 py-2 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="">All Categories</option>
              <option value="sqli">SQL Injection</option>
              <option value="xss">XSS</option>
              <option value="path_traversal">Path Traversal</option>
              <option value="rce">RCE</option>
              <option value="scanner">Scanner</option>
            </select>
          </div>

          {/* Events List */}
          {events.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <ShieldCheck className="mx-auto h-12 w-12 mb-4 text-green-500 opacity-50" />
              <p className="text-muted-foreground">No threat events found</p>
            </div>
          ) : (
            <div className="space-y-2">
              {events.map((event) => (
                <div key={event.id} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <code className="text-sm font-mono font-semibold">{event.client_ip}</code>
                        <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${categoryColors[event.category] || 'bg-muted'}`}>
                          {event.category.replace('_', ' ')}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${severityColors[event.severity] || severityColors.medium}`}>
                          {event.severity}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          event.action_taken === 'blocked' ? 'bg-red-500/10 text-red-500' : 'bg-slate-500/10 text-slate-400'
                        }`}>
                          {event.action_taken}
                        </span>
                      </div>
                      {event.request_uri && (
                        <p className="text-sm text-muted-foreground mt-1 truncate">
                          {event.request_method} {event.request_uri}
                        </p>
                      )}
                      {event.matched_payload && (
                        <code className="text-xs text-muted-foreground mt-1 block truncate">
                          Match: {event.matched_payload}
                        </code>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-muted-foreground">{formatDate(event.timestamp)}</span>
                      <button
                        onClick={() => handleBlockIp(event.client_ip)}
                        className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground hover:text-red-500"
                        title="Block IP"
                      >
                        <Ban className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : activeTab === 'actors' ? (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex gap-3">
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="">All Statuses</option>
              <option value="monitored">Monitored</option>
              <option value="warned">Warned</option>
              <option value="temp_blocked">Temp Blocked</option>
              <option value="perm_blocked">Perm Blocked</option>
              <option value="firewall_banned">Firewall Banned</option>
            </select>
          </div>

          {/* Actors List */}
          {actors.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <ShieldCheck className="mx-auto h-12 w-12 mb-4 text-green-500 opacity-50" />
              <p className="text-muted-foreground">No threat actors tracked</p>
            </div>
          ) : (
            <div className="space-y-2">
              {actors.map((actor) => (
                <div key={actor.id} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <code className="text-sm font-mono font-semibold">{actor.ip_address}</code>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${statusColors[actor.current_status] || statusColors.monitored}`}>
                          {actor.current_status.replace('_', ' ')}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          Score: <strong>{actor.threat_score}</strong>
                        </span>
                      </div>
                      <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
                        <span>{actor.total_events} events</span>
                        <span>First: {formatDate(actor.first_seen)}</span>
                        <span>Last: {formatDate(actor.last_seen)}</span>
                      </div>
                      {actor.notes && (
                        <p className="text-sm text-muted-foreground mt-1">{actor.notes}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {actor.current_status === 'monitored' || actor.current_status === 'warned' ? (
                        <button
                          onClick={() => handleBlockIp(actor.ip_address)}
                          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm bg-red-500/10 text-red-500 hover:bg-red-500/20"
                        >
                          <Ban className="h-3.5 w-3.5" />
                          Block
                        </button>
                      ) : (
                        <button
                          onClick={() => handleUnblockIp(actor.ip_address)}
                          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm bg-green-500/10 text-green-500 hover:bg-green-500/20"
                        >
                          <Unlock className="h-3.5 w-3.5" />
                          Unblock
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
