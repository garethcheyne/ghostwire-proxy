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
  Crosshair,
  RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataTable } from '@/components/data-table'
import { createEventColumns, type ThreatEvent } from '@/components/threats/event-columns'
import { createActorColumns, type ThreatActor } from '@/components/threats/actor-columns'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { IpAddress } from '@/components/ip-address'

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
  const [evFilterSeverity, setEvFilterSeverity] = useState<string[]>([])
  const [evFilterCategory, setEvFilterCategory] = useState<string[]>([])

  // Actor filters
  const [actorFilterIp, setActorFilterIp] = useState('')
  const [actorFilterStatus, setActorFilterStatus] = useState<string[]>([])

  // Multi-select dropdown open state
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)

  // Actor expanded events
  const [expandedActorIp, setExpandedActorIp] = useState<string | null>(null)
  const [actorEvents, setActorEvents] = useState<ThreatEvent[]>([])
  const [loadingActorEvents, setLoadingActorEvents] = useState(false)

  // IP Intel panel
  const [intelIp, setIntelIp] = useState<string | null>(null)
  const [intelData, setIntelData] = useState<any | null>(null)
  const [loadingIntel, setLoadingIntel] = useState(false)

  useEffect(() => {
    fetchData()
  }, [activeTab])

  // Close multi-select dropdowns on outside click
  useEffect(() => {
    if (!openDropdown) return
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-dropdown]')) setOpenDropdown(null)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [openDropdown])

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
      await api.delete(`/api/waf/actors/${encodeURIComponent(ip)}`)
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

  const handleInvestigateIp = async (ip: string) => {
    setIntelIp(ip)
    setLoadingIntel(true)
    setIntelData(null)
    try {
      const res = await api.get(`/api/honeypot/enrich/${encodeURIComponent(ip)}`)
      setIntelData(res.data)
    } catch (error) {
      console.error('Failed to enrich IP:', error)
    } finally {
      setLoadingIntel(false)
    }
  }

  // ── Filtered data (client-side) ──────────────────────────────

  const filteredEvents = useMemo(() => {
    let result = events
    if (evFilterIp) result = result.filter(e => e.client_ip.includes(evFilterIp))
    if (evFilterSeverity.length > 0) result = result.filter(e => evFilterSeverity.includes(e.severity))
    if (evFilterCategory.length > 0) result = result.filter(e => evFilterCategory.includes(e.category))
    return result
  }, [events, evFilterIp, evFilterSeverity, evFilterCategory])

  const filteredActors = useMemo(() => {
    let result = actors
    if (actorFilterIp) result = result.filter(a => a.ip_address.includes(actorFilterIp))
    if (actorFilterStatus.length > 0) result = result.filter(a => actorFilterStatus.includes(a.current_status))
    return result
  }, [actors, actorFilterIp, actorFilterStatus])

  const toggleFilter = (setter: React.Dispatch<React.SetStateAction<string[]>>, value: string) => {
    setter(prev => prev.includes(value) ? prev.filter(v => v !== value) : [...prev, value])
  }

  // ── Column defs (memoized) ───────────────────────────────────

  const eventColumns = useMemo(
    () => createEventColumns({ onBlock: handleBlockIp, onDelete: handleDeleteEvent, onInvestigate: handleInvestigateIp }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  const actorColumns = useMemo(
    () => createActorColumns({
      onBlock: handleBlockIp,
      onUnblock: handleUnblockIp,
      onDelete: handleDeleteActor,
      onToggleExpand: toggleActorEvents,
      onInvestigate: handleInvestigateIp,
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
                      <IpAddress ip={actor.ip} />
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
                <div className="relative" data-dropdown>
                  <button
                    type="button"
                    onClick={() => setOpenDropdown(openDropdown === 'severity' ? null : 'severity')}
                    className={`h-9 rounded-md border border-input bg-background px-3 text-sm flex items-center gap-1 ${evFilterSeverity.length > 0 ? 'text-foreground' : 'text-muted-foreground'}`}
                    title="Filter by severity"
                  >
                    {evFilterSeverity.length === 0 ? 'All Severities' : `${evFilterSeverity.length} selected`}
                  </button>
                  {openDropdown === 'severity' && (
                    <div className="absolute top-full left-0 z-20 mt-1 w-44 rounded-lg border border-border bg-card shadow-lg p-1">
                      {[{v:'critical',l:'Critical'},{v:'high',l:'High'},{v:'medium',l:'Medium'},{v:'low',l:'Low'}].map(o => (
                        <label key={o.v} className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md hover:bg-muted cursor-pointer">
                          <input type="checkbox" checked={evFilterSeverity.includes(o.v)} onChange={() => toggleFilter(setEvFilterSeverity, o.v)} className="h-3.5 w-3.5" />
                          {o.l}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div className="relative" data-dropdown>
                  <button
                    type="button"
                    onClick={() => setOpenDropdown(openDropdown === 'category' ? null : 'category')}
                    className={`h-9 rounded-md border border-input bg-background px-3 text-sm flex items-center gap-1 ${evFilterCategory.length > 0 ? 'text-foreground' : 'text-muted-foreground'}`}
                    title="Filter by category"
                  >
                    {evFilterCategory.length === 0 ? 'All Categories' : `${evFilterCategory.length} selected`}
                  </button>
                  {openDropdown === 'category' && (
                    <div className="absolute top-full left-0 z-20 mt-1 w-48 rounded-lg border border-border bg-card shadow-lg p-1 max-h-64 overflow-y-auto">
                      {[{v:'sqli',l:'SQL Injection'},{v:'xss',l:'XSS'},{v:'path_traversal',l:'Path Traversal'},{v:'rce',l:'RCE'},{v:'scanner',l:'Scanner'},{v:'injection',l:'Injection'},{v:'sensitive_data',l:'Sensitive Data'},{v:'recon',l:'Recon'},{v:'dos',l:'DoS'},{v:'blocked_ip',l:'Blocked IP'}].map(o => (
                        <label key={o.v} className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md hover:bg-muted cursor-pointer">
                          <input type="checkbox" checked={evFilterCategory.includes(o.v)} onChange={() => toggleFilter(setEvFilterCategory, o.v)} className="h-3.5 w-3.5" />
                          {o.l}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                {(evFilterIp || evFilterSeverity.length > 0 || evFilterCategory.length > 0) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 text-xs"
                    onClick={() => { setEvFilterIp(''); setEvFilterSeverity([]); setEvFilterCategory([]); setOpenDropdown(null) }}
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
              <div className="relative" data-dropdown>
                <button
                  type="button"
                  onClick={() => setOpenDropdown(openDropdown === 'status' ? null : 'status')}
                  className={`h-9 rounded-md border border-input bg-background px-3 text-sm flex items-center gap-1 ${actorFilterStatus.length > 0 ? 'text-foreground' : 'text-muted-foreground'}`}
                  title="Filter by status"
                >
                  {actorFilterStatus.length === 0 ? 'All Statuses' : `${actorFilterStatus.length} selected`}
                </button>
                {openDropdown === 'status' && (
                  <div className="absolute top-full left-0 z-20 mt-1 w-48 rounded-lg border border-border bg-card shadow-lg p-1">
                    {[{v:'monitored',l:'Monitored'},{v:'warned',l:'Warned'},{v:'temp_blocked',l:'Temp Blocked'},{v:'perm_blocked',l:'Perm Blocked'},{v:'firewall_banned',l:'Firewall Banned'}].map(o => (
                      <label key={o.v} className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md hover:bg-muted cursor-pointer">
                        <input type="checkbox" checked={actorFilterStatus.includes(o.v)} onChange={() => toggleFilter(setActorFilterStatus, o.v)} className="h-3.5 w-3.5" />
                        {o.l}
                      </label>
                    ))}
                  </div>
                )}
              </div>
              {(actorFilterIp || actorFilterStatus.length > 0) && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-xs"
                    onClick={() => { setActorFilterIp(''); setActorFilterStatus([]); setOpenDropdown(null) }}
                >
                  <X className="h-3 w-3 mr-1" /> Clear
                </Button>
              )}
            </div>
          }
        />
      ) : null}

      {/* ── IP Intel Slide-out Panel ── */}
      {intelIp && (
        <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-background border-l shadow-2xl overflow-y-auto">
          <div className="sticky top-0 bg-background border-b px-4 py-3 flex items-center justify-between z-10">
            <h3 className="font-semibold flex items-center gap-2">
              <Crosshair className="h-4 w-4 text-blue-500" />
              IP Intelligence: <code className="text-sm">{intelIp}</code>
            </h3>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleInvestigateIp(intelIp)} title="Refresh">
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setIntelIp(null); setIntelData(null) }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="p-4 space-y-4">
            {loadingIntel ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Enriching IP data...</span>
              </div>
            ) : intelData ? (
              <>
                {/* Location */}
                <div className="bg-card border rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <Globe className="h-3.5 w-3.5 text-blue-500" /> Location
                  </h4>
                  <div className="space-y-2 text-sm">
                    <IntelRow label="Country" value={intelData.country_name ? `${intelData.country_name} (${intelData.country_code})` : null} />
                    <IntelRow label="Region" value={intelData.region} />
                    <IntelRow label="City" value={intelData.city} />
                    <IntelRow label="Timezone" value={intelData.timezone} />
                    <IntelRow label="Coordinates" value={
                      intelData.latitude && intelData.longitude
                        ? `${intelData.latitude}, ${intelData.longitude}`
                        : null
                    } />
                  </div>
                </div>

                {/* Network */}
                <div className="bg-card border rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <Shield className="h-3.5 w-3.5 text-purple-500" /> Network
                  </h4>
                  <div className="space-y-2 text-sm">
                    <IntelRow label="ISP" value={intelData.isp} />
                    <IntelRow label="Organization" value={intelData.org} />
                    <IntelRow label="ASN" value={intelData.asn} mono />
                    <IntelRow label="AS Name" value={intelData.as_name} />
                    <IntelRow label="Reverse DNS" value={intelData.reverse_dns} mono />
                  </div>
                </div>

                {/* Reputation */}
                <div className="bg-card border rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> Reputation
                  </h4>
                  <div className="space-y-2 text-sm">
                    {intelData.abuse_score !== null && intelData.abuse_score !== undefined ? (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">Abuse Score</span>
                          <span className={`font-bold ${
                            intelData.abuse_score > 75 ? 'text-red-500' :
                            intelData.abuse_score > 50 ? 'text-orange-500' :
                            intelData.abuse_score > 25 ? 'text-yellow-500' : 'text-green-500'
                          }`}>
                            {intelData.abuse_score}%
                          </span>
                        </div>
                        <IntelRow label="Reports" value={String(intelData.abuse_reports ?? 0)} />
                      </>
                    ) : (
                      <p className="text-xs text-muted-foreground">AbuseIPDB unavailable (set API key in Settings)</p>
                    )}
                  </div>
                </div>

                {/* Indicators */}
                <div className="bg-card border rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                    <Crosshair className="h-3.5 w-3.5 text-red-500" /> Indicators
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    <IntelFlag label="Tor" value={intelData.is_tor} />
                    <IntelFlag label="Proxy" value={intelData.is_proxy} />
                    <IntelFlag label="VPN" value={intelData.is_vpn} />
                    <IntelFlag label="Datacenter" value={intelData.is_datacenter} />
                    <IntelFlag label="Crawler" value={intelData.is_crawler} />
                  </div>
                  {intelData.enriched_at && (
                    <p className="text-xs text-muted-foreground mt-3">Enriched: {formatDate(intelData.enriched_at)}</p>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-10">Failed to load intelligence data</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Helper Components ───────────────────────────────────────

function IntelRow({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`text-right truncate ${mono ? 'font-mono text-xs' : ''} ${value ? '' : 'text-muted-foreground/50 italic'}`}>
        {value || 'Unknown'}
      </span>
    </div>
  )
}

function IntelFlag({ label, value }: { label: string; value: boolean | null }) {
  if (value === null || value === undefined) {
    return <span className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground">{label}: ?</span>
  }
  return (
    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
      value
        ? 'bg-red-500/10 text-red-500 border border-red-500/20'
        : 'bg-green-500/10 text-green-500 border border-green-500/20'
    }`}>
      {label}: {value ? 'Yes' : 'No'}
    </span>
  )
}
