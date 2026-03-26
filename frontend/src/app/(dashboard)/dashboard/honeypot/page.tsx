'use client'

import { useState, useEffect } from 'react'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Bug,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Download,
  Search,
  Globe,
  Shield,
  Eye,
  RefreshCw,
  Crosshair,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { IpAddress, CountryBadge } from '@/components/ip-address'

interface HoneypotTrap {
  id: string
  path: string
  name: string
  description: string | null
  trap_type: string
  response_code: number
  response_body: string | null
  severity: string
  auto_block: boolean
  enabled: boolean
  proxy_host_id: string | null
  hit_count: number
  created_at: string
  updated_at: string
}

interface HoneypotHit {
  id: string
  trap_id: string
  trap_path: string
  client_ip: string
  request_method: string | null
  request_uri: string | null
  request_headers: string | null
  request_body: string | null
  user_agent: string | null
  host: string | null
  referer: string | null
  country_code: string | null
  country_name: string | null
  action_taken: string
  timestamp: string
}

interface IpEnrichment {
  id: string
  ip_address: string
  country_code: string | null
  country_name: string | null
  city: string | null
  region: string | null
  latitude: string | null
  longitude: string | null
  timezone: string | null
  isp: string | null
  org: string | null
  asn: string | null
  as_name: string | null
  reverse_dns: string | null
  abuse_score: number | null
  abuse_reports: number | null
  abuse_last_reported: string | null
  is_tor: boolean | null
  is_proxy: boolean | null
  is_vpn: boolean | null
  is_datacenter: boolean | null
  is_crawler: boolean | null
  enriched_at: string
}

interface HoneypotStats {
  total_traps: number
  active_traps: number
  total_hits: number
  hits_today: number
  hits_this_week: number
  unique_ips: number
  auto_blocked: number
  top_traps: Array<{ path: string; hit_count: number }>
  top_attackers: Array<{ ip: string; hits: number; country: string | null }>
  recent_hits: Array<{ ip: string; path: string; timestamp: string; country: string | null; user_agent: string | null }>
}

const trapTypeLabels: Record<string, string> = {
  wordpress: 'WordPress',
  phpmyadmin: 'phpMyAdmin',
  admin: 'Admin Panel',
  api: 'API Endpoint',
  generic: 'Generic',
}

const trapTypeColors: Record<string, string> = {
  wordpress: 'bg-blue-500/10 text-blue-500',
  phpmyadmin: 'bg-orange-500/10 text-orange-500',
  admin: 'bg-red-500/10 text-red-500',
  api: 'bg-purple-500/10 text-purple-500',
  generic: 'bg-slate-500/10 text-slate-400',
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

export default function HoneypotPage() {
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<'overview' | 'traps' | 'hits' | 'intel'>('overview')
  const [stats, setStats] = useState<HoneypotStats | null>(null)
  const [traps, setTraps] = useState<HoneypotTrap[]>([])
  const [hits, setHits] = useState<HoneypotHit[]>([])
  const [hosts, setHosts] = useState<Array<{ id: string; domain_names: string[] }>>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingTrap, setEditingTrap] = useState<HoneypotTrap | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [installingDefaults, setInstallingDefaults] = useState(false)
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // IP Intel
  const [lookupIp, setLookupIp] = useState('')
  const [enrichment, setEnrichment] = useState<IpEnrichment | null>(null)
  const [loadingIntel, setLoadingIntel] = useState(false)

  // Form state
  const [formName, setFormName] = useState('')
  const [formPath, setFormPath] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formTrapType, setFormTrapType] = useState('generic')
  const [formSeverity, setFormSeverity] = useState('high')
  const [formResponseCode, setFormResponseCode] = useState('200')
  const [formAutoBlock, setFormAutoBlock] = useState(true)
  const [formEnabled, setFormEnabled] = useState(true)
  const [formHostIds, setFormHostIds] = useState<string[]>([])
  const [hostDropdownOpen, setHostDropdownOpen] = useState(false)

  useEffect(() => {
    if (!hostDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-host-dropdown]')) setHostDropdownOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [hostDropdownOpen])

  useEffect(() => {
    if (!notification) return
    const timer = setTimeout(() => setNotification(null), 5000)
    return () => clearTimeout(timer)
  }, [notification])

  usePageData(() => {
    fetchData()
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  }, [activeTab])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'overview') {
        const res = await api.get('/api/honeypot/stats')
        setStats(res.data)
      } else if (activeTab === 'traps') {
        const res = await api.get('/api/honeypot/traps')
        setTraps(res.data)
      } else if (activeTab === 'hits') {
        const res = await api.get('/api/honeypot/hits?limit=200')
        setHits(res.data)
      }
    } catch (error) {
      console.error('Failed to fetch honeypot data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const installDefaults = async () => {
    setInstallingDefaults(true)
    try {
      const res = await api.post('/api/honeypot/traps/install-defaults')
      setNotification({ type: 'success', message: `Installed ${res.data.count} default traps` })
      toastSuccess(`Installed ${res.data.count} default traps`)
      fetchData()
    } catch {
      setNotification({ type: 'error', message: 'Failed to install defaults' })
      toastError('Failed to install defaults')
    } finally {
      setInstallingDefaults(false)
    }
  }

  const lookupIpIntel = async (ip?: string) => {
    const targetIp = ip || lookupIp
    if (!targetIp.trim()) return
    setLoadingIntel(true)
    setEnrichment(null)
    try {
      const res = await api.get(`/api/honeypot/enrich/${targetIp}`)
      setEnrichment(res.data)
      setLookupIp(targetIp)
      setActiveTab('intel')
    } catch {
      setNotification({ type: 'error', message: 'Failed to look up IP' })
    } finally {
      setLoadingIntel(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormPath('')
    setFormDescription('')
    setFormTrapType('generic')
    setFormSeverity('high')
    setFormResponseCode('200')
    setFormAutoBlock(true)
    setFormEnabled(true)
    setFormHostIds([])
    setHostDropdownOpen(false)
    setEditingTrap(null)
    setError('')
  }

  const openEditForm = (trap: HoneypotTrap) => {
    setFormName(trap.name)
    setFormPath(trap.path)
    setFormDescription(trap.description || '')
    setFormTrapType(trap.trap_type)
    setFormSeverity(trap.severity)
    setFormResponseCode(String(trap.response_code))
    setFormAutoBlock(trap.auto_block)
    setFormEnabled(trap.enabled)
    setFormHostIds(trap.proxy_host_id ? [trap.proxy_host_id] : [])
    setEditingTrap(trap)
    setShowCreateDialog(true)
    setError('')
  }

  const handleSubmit = async () => {
    if (!formName.trim() || !formPath.trim()) {
      setError('Name and path are required')
      return
    }
    setIsSubmitting(true)
    setError('')
    try {
      const basePayload = {
        name: formName,
        path: formPath,
        description: formDescription || null,
        trap_type: formTrapType,
        severity: formSeverity,
        response_code: parseInt(formResponseCode),
        auto_block: formAutoBlock,
        enabled: formEnabled,
      }
      if (editingTrap) {
        await api.put(`/api/honeypot/traps/${editingTrap.id}`, { ...basePayload, proxy_host_id: formHostIds[0] || null })
      } else if (formHostIds.length === 0) {
        // Global trap
        await api.post('/api/honeypot/traps', { ...basePayload, proxy_host_id: null })
      } else {
        // Create one trap per selected host
        const results = await Promise.allSettled(
          formHostIds.map(hostId => api.post('/api/honeypot/traps', { ...basePayload, proxy_host_id: hostId }))
        )
        const failures = results.filter(r => r.status === 'rejected')
        if (failures.length > 0 && failures.length < formHostIds.length) {
          setError(`Created for ${formHostIds.length - failures.length} hosts, failed for ${failures.length}`)
        } else if (failures.length === formHostIds.length) {
          throw (failures[0] as PromiseRejectedResult).reason
        }
      }
      setShowCreateDialog(false)
      resetForm()
      fetchData()
      toastSuccess(editingTrap ? 'Trap updated' : 'Trap created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save trap')
      toastError('Failed to save trap')
    } finally {
      setIsSubmitting(false)
    }
  }

  const deleteTrap = async (trap: HoneypotTrap) => {
    const ok = await confirm({
      title: 'Delete Honeypot Trap',
      description: `Delete "${trap.name}" (${trap.path})? This cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await api.delete(`/api/honeypot/traps/${trap.id}`)
      fetchData()
      toastSuccess('Trap deleted')
    } catch {
      setNotification({ type: 'error', message: 'Failed to delete trap' })
      toastError('Failed to delete trap')
    }
  }

  const toggleTrap = async (trap: HoneypotTrap) => {
    try {
      await api.put(`/api/honeypot/traps/${trap.id}`, { enabled: !trap.enabled })
      fetchData()
      toastSuccess(trap.enabled ? 'Trap disabled' : 'Trap enabled')
    } catch {
      setNotification({ type: 'error', message: 'Failed to toggle trap' })
      toastError('Failed to toggle trap')
    }
  }

  const formatDate = (d: string) => {
    return new Date(d).toLocaleString()
  }

  // ── Render ──────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Notification banner */}
      {notification && (
        <div className={`rounded-md px-4 py-3 text-sm flex items-center justify-between ${
          notification.type === 'success' ? 'bg-green-500/15 text-green-600 dark:text-green-400' : 'bg-destructive/15 text-destructive'
        }`}>
          <span>{notification.message}</span>
          <button onClick={() => setNotification(null)} className="ml-4 hover:opacity-70">&times;</button>
        </div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Bug className="h-6 w-6 text-amber-500" />
            Honeypot Traps
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Fake endpoints that catch scanners and gather attacker intelligence
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={installDefaults} disabled={installingDefaults}>
            {installingDefaults ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
            Install Defaults
          </Button>
          <Button size="sm" onClick={() => { resetForm(); setShowCreateDialog(true) }}>
            <Plus className="h-4 w-4 mr-1" /> Add Trap
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-muted/50 p-1 rounded-lg w-fit">
        {(['overview', 'traps', 'hits', 'intel'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab === 'overview' ? 'Overview' : tab === 'traps' ? 'Traps' : tab === 'hits' ? 'Hit Log' : 'IP Intel'}
          </button>
        ))}
      </div>

      {isLoading && activeTab !== 'intel' ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* ── Overview Tab ── */}
          {activeTab === 'overview' && stats && (
            <div className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-card border rounded-lg p-4">
                  <div className="text-sm text-muted-foreground">Active Traps</div>
                  <div className="text-2xl font-bold">{stats.active_traps} <span className="text-sm font-normal text-muted-foreground">/ {stats.total_traps}</span></div>
                </div>
                <div className="bg-card border rounded-lg p-4">
                  <div className="text-sm text-muted-foreground">Total Hits</div>
                  <div className="text-2xl font-bold text-amber-500">{stats.total_hits}</div>
                </div>
                <div className="bg-card border rounded-lg p-4">
                  <div className="text-sm text-muted-foreground">Hits Today</div>
                  <div className="text-2xl font-bold text-orange-500">{stats.hits_today}</div>
                </div>
                <div className="bg-card border rounded-lg p-4">
                  <div className="text-sm text-muted-foreground">Unique IPs Caught</div>
                  <div className="text-2xl font-bold text-red-500">{stats.unique_ips}</div>
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-6">
                {/* Top Traps */}
                <div className="bg-card border rounded-lg p-4">
                  <h3 className="font-semibold mb-3 flex items-center gap-2">
                    <Crosshair className="h-4 w-4 text-amber-500" /> Most Triggered Traps
                  </h3>
                  {stats.top_traps.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No hits yet</p>
                  ) : (
                    <div className="space-y-2">
                      {stats.top_traps.map((t, i) => (
                        <div key={i} className="flex items-center justify-between text-sm">
                          <code className="bg-muted px-2 py-0.5 rounded text-xs">{t.path}</code>
                          <span className="font-mono font-bold text-amber-500">{t.hit_count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Top Attackers */}
                <div className="bg-card border rounded-lg p-4">
                  <h3 className="font-semibold mb-3 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" /> Top Attackers
                  </h3>
                  {stats.top_attackers.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No attackers caught yet</p>
                  ) : (
                    <div className="space-y-2">
                      {stats.top_attackers.map((a, i) => (
                        <div key={i} className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <IpAddress ip={a.ip} />
                            {a.country && (
                              <span className="text-xs text-muted-foreground">{a.country}</span>
                            )}
                          </div>
                          <span className="font-mono font-bold text-red-500">{a.hits} hits</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Recent Hits */}
              <div className="bg-card border rounded-lg p-4">
                <h3 className="font-semibold mb-3">Recent Hits</h3>
                {stats.recent_hits.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No hits recorded yet. Install default traps to get started.</p>
                ) : (
                  <div className="space-y-2">
                    {stats.recent_hits.map((h, i) => (
                      <div key={i} className="flex items-center gap-3 text-sm py-1 border-b border-border/50 last:border-0">
                        <span className="text-xs text-muted-foreground w-36">{formatDate(h.timestamp)}</span>
                        <span className="w-32">
                          <IpAddress ip={h.ip} />
                        </span>
                        <code className="bg-muted px-2 py-0.5 rounded text-xs">{h.path}</code>
                        {h.country && <span className="text-xs text-muted-foreground">{h.country}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Traps Tab ── */}
          {activeTab === 'traps' && (
            <div className="space-y-4">
              {traps.length === 0 ? (
                <div className="text-center py-20 text-muted-foreground">
                  <Bug className="h-12 w-12 mx-auto mb-4 opacity-30" />
                  <p>No honeypot traps configured</p>
                  <p className="text-sm mt-1">Click &quot;Install Defaults&quot; to set up common traps</p>
                </div>
              ) : (
                <div className="grid gap-3">
                  {traps.map(trap => (
                    <div key={trap.id} className={`bg-card border rounded-lg p-4 ${!trap.enabled ? 'opacity-50' : ''}`}>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold">{trap.name}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${trapTypeColors[trap.trap_type] || trapTypeColors.generic}`}>
                              {trapTypeLabels[trap.trap_type] || trap.trap_type}
                            </span>
                            <span className={`text-xs px-2 py-0.5 rounded-full border ${severityColors[trap.severity] || severityColors.medium}`}>
                              {trap.severity}
                            </span>
                            {trap.auto_block && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-500">
                                <Shield className="h-3 w-3 inline mr-1" />auto-block
                              </span>
                            )}
                          </div>
                          <code className="text-sm text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded">{trap.path}</code>
                          {trap.description && (
                            <p className="text-sm text-muted-foreground mt-1">{trap.description}</p>
                          )}
                          <div className="text-xs text-muted-foreground mt-2">
                            {trap.hit_count} hits · Response: {trap.response_code} · {trap.proxy_host_id ? hosts.find(h => h.id === trap.proxy_host_id)?.domain_names[0] || 'Specific host' : 'All hosts'}
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button variant="ghost" size="icon" onClick={() => toggleTrap(trap)}>
                            {trap.enabled ? <ToggleRight className="h-4 w-4 text-green-500" /> : <ToggleLeft className="h-4 w-4" />}
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => openEditForm(trap)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => deleteTrap(trap)}>
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Hits Tab ── */}
          {activeTab === 'hits' && (
            <div className="space-y-4">
              {hits.length === 0 ? (
                <div className="text-center py-20 text-muted-foreground">
                  <Eye className="h-12 w-12 mx-auto mb-4 opacity-30" />
                  <p>No honeypot hits recorded yet</p>
                </div>
              ) : (
                <div className="bg-card border rounded-lg overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/30">
                          <th className="text-left px-4 py-3 font-medium">Time</th>
                          <th className="text-left px-4 py-3 font-medium">IP Address</th>
                          <th className="text-left px-4 py-3 font-medium">Trap</th>
                          <th className="text-left px-4 py-3 font-medium">Method</th>
                          <th className="text-left px-4 py-3 font-medium">Country</th>
                          <th className="text-left px-4 py-3 font-medium">User Agent</th>
                          <th className="text-left px-4 py-3 font-medium">Action</th>
                          <th className="text-left px-4 py-3 font-medium">Intel</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hits.map(hit => (
                          <tr key={hit.id} className="border-b border-border/50 hover:bg-muted/20">
                            <td className="px-4 py-2 text-xs text-muted-foreground whitespace-nowrap">
                              {formatDate(hit.timestamp)}
                            </td>
                            <td className="px-4 py-2">
                              <IpAddress ip={hit.client_ip} />
                            </td>
                            <td className="px-4 py-2">
                              <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{hit.trap_path}</code>
                            </td>
                            <td className="px-4 py-2 text-xs">{hit.request_method || '-'}</td>
                            <td className="px-4 py-2 text-xs">
                              {hit.country_code ? (
                                <CountryBadge code={hit.country_code} name={hit.country_name} />
                              ) : '-'}
                            </td>
                            <td className="px-4 py-2 text-xs max-w-[200px] truncate text-muted-foreground" title={hit.user_agent || ''}>
                              {hit.user_agent || '-'}
                            </td>
                            <td className="px-4 py-2">
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                hit.action_taken === 'blocked'
                                  ? 'bg-red-500/10 text-red-500'
                                  : 'bg-slate-500/10 text-slate-400'
                              }`}>
                                {hit.action_taken}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => lookupIpIntel(hit.client_ip)}
                                title="Full IP intel lookup"
                              >
                                <Eye className="h-3 w-3" />
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── IP Intel Tab ── */}
          {activeTab === 'intel' && (
            <div className="space-y-6">
              <div className="flex gap-2">
                <Input
                  placeholder="Enter IP address to investigate..."
                  value={lookupIp}
                  onChange={e => setLookupIp(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && lookupIpIntel()}
                  className="max-w-md font-mono"
                />
                <Button onClick={() => lookupIpIntel()} disabled={loadingIntel}>
                  {loadingIntel ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Search className="h-4 w-4 mr-1" />}
                  Look Up
                </Button>
                {enrichment && (
                  <Button variant="outline" onClick={() => lookupIpIntel(lookupIp)} disabled={loadingIntel}>
                    <RefreshCw className="h-4 w-4 mr-1" /> Refresh
                  </Button>
                )}
              </div>

              {loadingIntel && (
                <div className="flex items-center justify-center py-20">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  <span className="ml-2 text-muted-foreground">Enriching IP data...</span>
                </div>
              )}

              {enrichment && !loadingIntel && (
                <div className="grid md:grid-cols-2 gap-6">
                  {/* Location */}
                  <div className="bg-card border rounded-lg p-5">
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <Globe className="h-4 w-4 text-blue-500" /> Location
                    </h3>
                    <div className="space-y-3 text-sm">
                      <InfoRow label="IP Address" value={enrichment.ip_address} mono />
                      <InfoRow label="Country" value={enrichment.country_name ? `${enrichment.country_name} (${enrichment.country_code})` : null} />
                      <InfoRow label="Region" value={enrichment.region} />
                      <InfoRow label="City" value={enrichment.city} />
                      <InfoRow label="Timezone" value={enrichment.timezone} />
                      <InfoRow label="Coordinates" value={
                        enrichment.latitude && enrichment.longitude
                          ? `${enrichment.latitude}, ${enrichment.longitude}`
                          : null
                      } />
                    </div>
                  </div>

                  {/* Network */}
                  <div className="bg-card border rounded-lg p-5">
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <Shield className="h-4 w-4 text-purple-500" /> Network
                    </h3>
                    <div className="space-y-3 text-sm">
                      <InfoRow label="ISP" value={enrichment.isp} />
                      <InfoRow label="Organization" value={enrichment.org} />
                      <InfoRow label="ASN" value={enrichment.asn} mono />
                      <InfoRow label="AS Name" value={enrichment.as_name} />
                      <InfoRow label="Reverse DNS" value={enrichment.reverse_dns} mono />
                    </div>
                  </div>

                  {/* Reputation */}
                  <div className="bg-card border rounded-lg p-5">
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-500" /> Reputation
                    </h3>
                    <div className="space-y-3 text-sm">
                      {enrichment.abuse_score !== null ? (
                        <>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Abuse Score</span>
                            <div className="flex items-center gap-2">
                              <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    enrichment.abuse_score > 75 ? 'bg-red-500' :
                                    enrichment.abuse_score > 50 ? 'bg-orange-500' :
                                    enrichment.abuse_score > 25 ? 'bg-yellow-500' : 'bg-green-500'
                                  }`}
                                  style={{ width: `${enrichment.abuse_score}%` }}
                                />
                              </div>
                              <span className={`font-bold ${
                                enrichment.abuse_score > 75 ? 'text-red-500' :
                                enrichment.abuse_score > 50 ? 'text-orange-500' :
                                enrichment.abuse_score > 25 ? 'text-yellow-500' : 'text-green-500'
                              }`}>
                                {enrichment.abuse_score}%
                              </span>
                            </div>
                          </div>
                          <InfoRow label="Abuse Reports" value={String(enrichment.abuse_reports ?? 0)} />
                          <InfoRow label="Last Reported" value={enrichment.abuse_last_reported ? formatDate(enrichment.abuse_last_reported) : null} />
                        </>
                      ) : (
                        <p className="text-muted-foreground text-xs">
                          AbuseIPDB data unavailable. Set your API key in Settings to enable.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Flags */}
                  <div className="bg-card border rounded-lg p-5">
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <Crosshair className="h-4 w-4 text-red-500" /> Indicators
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      <FlagBadge label="Tor" value={enrichment.is_tor} />
                      <FlagBadge label="Proxy" value={enrichment.is_proxy} />
                      <FlagBadge label="VPN / Hosting" value={enrichment.is_vpn} />
                      <FlagBadge label="Datacenter" value={enrichment.is_datacenter} />
                      <FlagBadge label="Crawler" value={enrichment.is_crawler} />
                    </div>
                    <div className="text-xs text-muted-foreground mt-4">
                      Enriched: {formatDate(enrichment.enriched_at)}
                    </div>
                  </div>
                </div>
              )}

              {!enrichment && !loadingIntel && (
                <div className="text-center py-20 text-muted-foreground">
                  <Search className="h-12 w-12 mx-auto mb-4 opacity-30" />
                  <p>Enter an IP address to investigate</p>
                  <p className="text-sm mt-1">Or click any IP in the Hit Log to auto-look up</p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Create/Edit Dialog ── */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={() => setShowCreateDialog(false)}>
          <div className="bg-background border rounded-lg p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-bold mb-4">{editingTrap ? 'Edit' : 'Create'} Honeypot Trap</h2>

            {error && <div className="text-sm text-red-500 bg-red-500/10 px-3 py-2 rounded mb-3">{error}</div>}

            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium">Name</label>
                <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="WordPress Login" />
              </div>
              <div>
                <label className="text-sm font-medium">Path</label>
                <Input value={formPath} onChange={e => setFormPath(e.target.value)} placeholder="/wp-login.php" className="font-mono" />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <Input value={formDescription} onChange={e => setFormDescription(e.target.value)} placeholder="Catches WordPress scanners" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Type</label>
                  <select
                    value={formTrapType}
                    onChange={e => setFormTrapType(e.target.value)}
                    className="w-full h-9 px-3 rounded-md border bg-background text-sm"
                    title="Trap type"
                  >
                    <option value="wordpress">WordPress</option>
                    <option value="phpmyadmin">phpMyAdmin</option>
                    <option value="admin">Admin Panel</option>
                    <option value="api">API Endpoint</option>
                    <option value="generic">Generic</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Severity</label>
                  <select
                    value={formSeverity}
                    onChange={e => setFormSeverity(e.target.value)}
                    className="w-full h-9 px-3 rounded-md border bg-background text-sm"
                    title="Severity level"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Response Code</label>
                  <Input type="number" value={formResponseCode} onChange={e => setFormResponseCode(e.target.value)} />
                </div>
                <div className="flex items-end pb-1">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={formAutoBlock} onChange={e => setFormAutoBlock(e.target.checked)} className="rounded" />
                    <span className="text-sm">Auto-block attacker</span>
                  </label>
                </div>
              </div>
              <div className="relative" data-host-dropdown>
                <label className="text-sm font-medium">Apply to Host</label>
                <button
                  type="button"
                  onClick={() => setHostDropdownOpen(!hostDropdownOpen)}
                  className="w-full h-9 px-3 rounded-md border bg-background text-sm text-left flex items-center justify-between"
                >
                  <span className="truncate">
                    {formHostIds.length === 0
                      ? 'All Hosts (global)'
                      : formHostIds.length === 1
                        ? hosts.find(h => h.id === formHostIds[0])?.domain_names[0] || '1 host'
                        : `${formHostIds.length} hosts selected`}
                  </span>
                  <svg className={`h-4 w-4 shrink-0 opacity-50 transition-transform ${hostDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                </button>
                {hostDropdownOpen && (
                  <div className="absolute z-50 mt-1 w-full bg-background border rounded-md shadow-lg max-h-48 overflow-y-auto">
                    <label className="flex items-center gap-2 px-3 py-2 hover:bg-muted cursor-pointer border-b">
                      <input
                        type="checkbox"
                        checked={formHostIds.length === 0}
                        onChange={() => { setFormHostIds([]); setHostDropdownOpen(false) }}
                        className="rounded"
                      />
                      <span className="text-sm">All Hosts (global)</span>
                    </label>
                    {hosts.map(h => (
                      <label key={h.id} className="flex items-center gap-2 px-3 py-2 hover:bg-muted cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formHostIds.includes(h.id)}
                          onChange={() => {
                            setFormHostIds(prev =>
                              prev.includes(h.id) ? prev.filter(id => id !== h.id) : [...prev, h.id]
                            )
                          }}
                          className="rounded"
                        />
                        <span className="text-sm truncate">{h.domain_names[0]}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button variant="outline" onClick={() => { setShowCreateDialog(false); resetForm() }}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                {editingTrap ? 'Save' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Helper Components ─────────────────────────────────────────

function InfoRow({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`text-right truncate ${mono ? 'font-mono text-xs' : ''} ${value ? '' : 'text-muted-foreground/50 italic'}`}>
        {value || 'Unknown'}
      </span>
    </div>
  )
}

function FlagBadge({ label, value }: { label: string; value: boolean | null }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-xs px-2.5 py-1 rounded-full bg-muted text-muted-foreground">
        {label}: ?
      </span>
    )
  }
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
      value
        ? 'bg-red-500/10 text-red-500 border border-red-500/20'
        : 'bg-green-500/10 text-green-500 border border-green-500/20'
    }`}>
      {label}: {value ? 'Yes' : 'No'}
    </span>
  )
}
