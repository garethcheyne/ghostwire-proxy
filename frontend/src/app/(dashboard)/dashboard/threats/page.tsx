'use client'

import { useState, useEffect, useMemo } from 'react'
import {
  AlertTriangle,
  Shield,
  ShieldBan,
  ShieldCheck,
  Eye,
  Loader2,
  Search,
  Trash2,
  Globe,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataTable } from '@/components/data-table'
import { createEventColumns, type ThreatEvent } from '@/components/threats/event-columns'
import { createActorColumns, type ThreatActor } from '@/components/threats/actor-columns'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'

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
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<'overview' | 'events' | 'actors'>('overview')
  const [stats, setStats] = useState<ThreatStats | null>(null)
  const [events, setEvents] = useState<ThreatEvent[]>([])
  const [actors, setActors] = useState<ThreatActor[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Event filters
  const [evFilterIp, setEvFilterIp] = useState('')
  const [evFilterSeverity, setEvFilterSeverity] = useState('')
  const [evFilterCategory, setEvFilterCategory] = useState('')

  // Actor filters
  const [actorFilterIp, setActorFilterIp] = useState('')
  const [actorFilterStatus, setActorFilterStatus] = useState('')

  // Actor expanded events
  const [expandedActorIp, setExpandedActorIp] = useState<string | null>(null)
  const [actorEvents, setActorEvents] = useState<ThreatEvent[]>([])
  const [loadingActorEvents, setLoadingActorEvents] = useState(false)

  useEffect(() => {
    fetchData()
  }, [activeTab])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'overview') {
        const res = await api.get('/api/waf/stats')
        setStats(res.data)
      } else if (activeTab === 'events') {
        const res = await api.get('/api/waf/events?limit=200')
        setEvents(res.data)
      } else if (activeTab === 'actors') {
        const res = await api.get('/api/waf/actors?limit=200')
        setActors(res.data)
      }
    } catch (error) {
      console.error('Failed to fetch threat data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // ── Actions ──────────────────────────────────────────────────

  const handleBlockIp = async (ip: string) => {
    if (!(await confirm({ description: `Block IP ${ip} permanently?`, variant: 'destructive' }))) return
    try {
      await api.post(`/api/waf/actors/${encodeURIComponent(ip)}/block`)
      fetchData()
    } catch (error) {
      console.error('Failed to block IP:', error)
    }
  }

  const handleUnblockIp = async (ip: string) => {
    if (!(await confirm({ description: `Unblock IP ${ip}?` }))) return
    try {
      await api.post(`/api/waf/actors/${encodeURIComponent(ip)}/unblock`)
      fetchData()
    } catch (error) {
      console.error('Failed to unblock IP:', error)
    }
  }

  const handleDeleteEvent = async (eventId: string) => {
    try {
      await api.delete(`/api/waf/events/${eventId}`)
      setEvents(prev => prev.filter(e => e.id !== eventId))
    } catch (error) {
      console.error('Failed to delete event:', error)
    }
  }

  const handlePurgeEvents = async () => {
    if (!(await confirm({ description: 'Purge ALL threat events? This cannot be undone.', variant: 'destructive' }))) return
    try {
      await api.delete('/api/waf/events')
      setEvents([])
      fetchData()
    } catch (error) {
      console.error('Failed to purge events:', error)
    }
  }

  const handleDeleteActor = async (actorId: string, ip: string) => {
    if (!(await confirm({ description: `Delete threat actor ${ip}? This also removes their events.`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/waf/actors/${actorId}`)
      setActors(prev => prev.filter(a => a.id !== actorId))
    } catch (error) {
      console.error('Failed to delete actor:', error)
    }
  }

  const toggleActorEvents = async (ip: string) => {
    if (expandedActorIp === ip) {
      setExpandedActorIp(null)
      setActorEvents([])
      return
    }
    setExpandedActorIp(ip)
    setLoadingActorEvents(true)
    try {
      const res = await api.get(`/api/waf/events?client_ip=${encodeURIComponent(ip)}&limit=200`)
      setActorEvents(res.data)
    } catch (error) {
      console.error('Failed to fetch actor events:', error)
      setActorEvents([])
    } finally {
      setLoadingActorEvents(false)
    }
  }

  // ── Filtered data (client-side) ──────────────────────────────

  const filteredEvents = useMemo(() => {
    let result = events
    if (evFilterIp) result = result.filter(e => e.client_ip.includes(evFilterIp))
    if (evFilterSeverity) result = result.filter(e => e.severity === evFilterSeverity)
    if (evFilterCategory) result = result.filter(e => e.category === evFilterCategory)
    return result
  }, [events, evFilterIp, evFilterSeverity, evFilterCategory])

  const filteredActors = useMemo(() => {
    let result = actors
    if (actorFilterIp) result = result.filter(a => a.ip_address.includes(actorFilterIp))
    if (actorFilterStatus) result = result.filter(a => a.current_status === actorFilterStatus)
    return result
  }, [actors, actorFilterIp, actorFilterStatus])

  // ── Column defs (memoized) ───────────────────────────────────

  const eventColumns = useMemo(
    () => createEventColumns({ onBlock: handleBlockIp, onDelete: handleDeleteEvent }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  const actorColumns = useMemo(
    () => createActorColumns({
      onBlock: handleBlockIp,
      onUnblock: handleUnblockIp,
      onDelete: handleDeleteActor,
      onToggleExpand: toggleActorEvents,
      expandedIp: expandedActorIp,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [expandedActorIp]
  )

  const formatDate = (d: string) => {
    try { return new Date(d).toLocaleString() } catch { return d }
  }

  // ── Render ───────────────────────────────────────────────────

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
        <DataTable
          columns={eventColumns}
          data={filteredEvents}
          pageSize={25}
          emptyMessage="No threat events found"
          emptyIcon={<ShieldCheck className="h-10 w-10 text-green-500 opacity-50" />}
          toolbar={
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
              <div className="flex flex-wrap gap-2 items-center">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={evFilterIp}
                    onChange={(e) => setEvFilterIp(e.target.value)}
                    placeholder="Filter by IP..."
                    className="w-44 pl-8 h-9 text-sm"
                  />
                </div>
                <select
                  value={evFilterSeverity}
                  onChange={(e) => setEvFilterSeverity(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">All Severities</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
                <select
                  value={evFilterCategory}
                  onChange={(e) => setEvFilterCategory(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">All Categories</option>
                  <option value="sqli">SQL Injection</option>
                  <option value="xss">XSS</option>
                  <option value="path_traversal">Path Traversal</option>
                  <option value="rce">RCE</option>
                  <option value="scanner">Scanner</option>
                  <option value="injection">Injection</option>
                  <option value="sensitive_data">Sensitive Data</option>
                  <option value="recon">Recon</option>
                  <option value="dos">DoS</option>
                  <option value="blocked_ip">Blocked IP</option>
                </select>
                {(evFilterIp || evFilterSeverity || evFilterCategory) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 text-xs"
                    onClick={() => { setEvFilterIp(''); setEvFilterSeverity(''); setEvFilterCategory('') }}
                  >
                    <X className="h-3 w-3 mr-1" /> Clear
                  </Button>
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-9 text-xs border-red-500/30 text-red-500 hover:bg-red-500/10"
                onClick={handlePurgeEvents}
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Purge All
              </Button>
            </div>
          }
        />

      ) : activeTab === 'actors' ? (
        <DataTable
          columns={actorColumns}
          data={filteredActors}
          pageSize={25}
          emptyMessage="No threat actors tracked"
          emptyIcon={<ShieldCheck className="h-10 w-10 text-green-500 opacity-50" />}
          expandedRowId={expandedActorIp}
          getRowExpansionId={(actor) => actor.ip_address}
          renderSubRow={(actor) => {
            if (actor.ip_address !== expandedActorIp) return null
            return (
              <div className="p-4 bg-muted/30 border-t border-border">
                {loadingActorEvents ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading events...
                  </div>
                ) : actorEvents.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">No events found for this actor</p>
                ) : (
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground mb-2">
                      Events for {actor.ip_address} ({actorEvents.length})
                    </p>
                    <div className="max-h-72 overflow-y-auto space-y-1">
                      {actorEvents.map((event) => (
                        <div key={event.id} className="flex items-center justify-between gap-3 rounded-lg bg-background px-3 py-2 text-xs border border-border/50">
                          <div className="flex items-center gap-2 min-w-0 flex-1 flex-wrap">
                            <span className="text-muted-foreground shrink-0">
                              {formatDate(event.timestamp)}
                            </span>
                            {event.host && (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shrink-0">
                                <Globe className="h-3 w-3" />
                                {event.host}
                              </span>
                            )}
                            <span className={`px-1.5 py-0.5 rounded capitalize shrink-0 ${
                              categoryColors[event.category] || 'bg-muted'
                            }`}>
                              {event.category.replace(/_/g, ' ')}
                            </span>
                            <span className={`px-1.5 py-0.5 rounded border capitalize shrink-0 ${
                              severityColors[event.severity] || severityColors.medium
                            }`}>
                              {event.severity}
                            </span>
                            {event.rule_name && (
                              <span className="text-muted-foreground truncate" title={event.rule_name}>
                                {event.rule_name}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            {event.request_uri && (
                              <code className="text-muted-foreground truncate max-w-48 hidden lg:block" title={`${event.request_method} ${event.request_uri}`}>
                                {event.request_method} {event.request_uri}
                              </code>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-muted-foreground hover:text-red-500"
                              onClick={() => handleDeleteEvent(event.id)}
                              title="Delete event"
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          }}
          toolbar={
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={actorFilterIp}
                  onChange={(e) => setActorFilterIp(e.target.value)}
                  placeholder="Filter by IP..."
                  className="w-44 pl-8 h-9 text-sm"
                />
              </div>
              <select
                value={actorFilterStatus}
                onChange={(e) => setActorFilterStatus(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">All Statuses</option>
                <option value="monitored">Monitored</option>
                <option value="warned">Warned</option>
                <option value="temp_blocked">Temp Blocked</option>
                <option value="perm_blocked">Perm Blocked</option>
                <option value="firewall_banned">Firewall Banned</option>
              </select>
              {(actorFilterIp || actorFilterStatus) && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-xs"
                  onClick={() => { setActorFilterIp(''); setActorFilterStatus('') }}
                >
                  <X className="h-3 w-3 mr-1" /> Clear
                </Button>
              )}
            </div>
          }
        />
      ) : null}
    </div>
  )
}
