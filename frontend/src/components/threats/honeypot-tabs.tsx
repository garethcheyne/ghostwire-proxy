'use client'

import { useState, useEffect } from 'react'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Bug,
  Plus,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Download,
  Search,
  Shield,
  Eye,
  RefreshCw,
  Crosshair,
  AlertTriangle,
  Globe,
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
  severity: string
  auto_block: boolean
  enabled: boolean
  proxy_host_id: string | null
  hit_count: number
}

interface HoneypotHit {
  id: string
  trap_id: string
  trap_path: string
  client_ip: string
  request_method: string | null
  request_uri: string | null
  user_agent: string | null
  country_code: string | null
  country_name: string | null
  action_taken: string
  timestamp: string
}

interface HoneypotStats {
  total_traps: number
  active_traps: number
  total_hits: number
  hits_today: number
  unique_ips: number
  top_traps: Array<{ path: string; hit_count: number }>
  top_attackers: Array<{ ip: string; hits: number; country: string | null }>
  recent_hits: Array<{ ip: string; path: string; timestamp: string; country: string | null }>
}

const trapTypeColors: Record<string, string> = {
  wordpress: 'bg-blue-500/10 text-blue-500',
  phpmyadmin: 'bg-orange-500/10 text-orange-500',
  admin: 'bg-red-500/10 text-red-500',
  api: 'bg-purple-500/10 text-purple-500',
  generic: 'bg-slate-500/10 text-slate-400',
}

const trapTypeLabels: Record<string, string> = {
  wordpress: 'WordPress', phpmyadmin: 'phpMyAdmin', admin: 'Admin', api: 'API', generic: 'Generic',
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

interface HoneypotTabsProps {
  activeSubTab: 'overview' | 'traps' | 'hits'
  onInvestigateIp: (ip: string) => void
}

export function HoneypotTabs({ activeSubTab, onInvestigateIp }: HoneypotTabsProps) {
  const confirm = useConfirm()
  const [stats, setStats] = useState<HoneypotStats | null>(null)
  const [traps, setTraps] = useState<HoneypotTrap[]>([])
  const [hits, setHits] = useState<HoneypotHit[]>([])
  const [hosts, setHosts] = useState<Array<{ id: string; domain_names: string[] }>>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editingTrap, setEditingTrap] = useState<HoneypotTrap | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [installingDefaults, setInstallingDefaults] = useState(false)

  // Form state
  const [form, setForm] = useState({
    name: '', path: '', description: '', trap_type: 'generic', severity: 'high',
    response_code: '200', auto_block: true, enabled: true, hostId: ''
  })

  useEffect(() => {
    fetchData()
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  }, [activeSubTab]) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeSubTab === 'overview') {
        const res = await api.get('/api/honeypot/stats')
        setStats(res.data)
      } else if (activeSubTab === 'traps') {
        const res = await api.get('/api/honeypot/traps')
        setTraps(res.data)
      } else if (activeSubTab === 'hits') {
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
      toastSuccess(`Installed ${res.data.count} default traps`)
      fetchData()
    } catch {
      toastError('Failed to install defaults')
    } finally {
      setInstallingDefaults(false)
    }
  }

  const resetForm = () => {
    setForm({ name: '', path: '', description: '', trap_type: 'generic', severity: 'high', response_code: '200', auto_block: true, enabled: true, hostId: '' })
    setEditingTrap(null)
    setError('')
  }

  const openEditForm = (trap: HoneypotTrap) => {
    setForm({
      name: trap.name, path: trap.path, description: trap.description || '',
      trap_type: trap.trap_type, severity: trap.severity, response_code: String(trap.response_code),
      auto_block: trap.auto_block, enabled: trap.enabled, hostId: trap.proxy_host_id || ''
    })
    setEditingTrap(trap)
    setShowDialog(true)
  }

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.path.trim()) { setError('Name and path required'); return }
    setIsSubmitting(true)
    setError('')
    try {
      const payload = {
        name: form.name, path: form.path, description: form.description || null,
        trap_type: form.trap_type, severity: form.severity, response_code: parseInt(form.response_code),
        auto_block: form.auto_block, enabled: form.enabled, proxy_host_id: form.hostId || null
      }
      if (editingTrap) {
        await api.put(`/api/honeypot/traps/${editingTrap.id}`, payload)
      } else {
        await api.post('/api/honeypot/traps', payload)
      }
      setShowDialog(false)
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
    if (!(await confirm({ title: 'Delete Trap', description: `Delete "${trap.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/honeypot/traps/${trap.id}`)
      fetchData()
      toastSuccess('Trap deleted')
    } catch {
      toastError('Failed to delete trap')
    }
  }

  const toggleTrap = async (trap: HoneypotTrap) => {
    try {
      await api.put(`/api/honeypot/traps/${trap.id}`, { enabled: !trap.enabled })
      fetchData()
      toastSuccess(trap.enabled ? 'Trap disabled' : 'Trap enabled')
    } catch {
      toastError('Failed to toggle trap')
    }
  }

  const formatDate = (d: string) => new Date(d).toLocaleString()

  if (isLoading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
  }

  // ─── OVERVIEW TAB ───────────────────────────────────────────
  if (activeSubTab === 'overview' && stats) {
    return (
      <div className="space-y-4 sm:space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <div className="bg-card border rounded-lg p-3 sm:p-4">
            <div className="text-xs sm:text-sm text-muted-foreground">Active Traps</div>
            <div className="text-xl sm:text-2xl font-bold">{stats.active_traps} <span className="text-sm font-normal text-muted-foreground">/ {stats.total_traps}</span></div>
          </div>
          <div className="bg-card border rounded-lg p-3 sm:p-4">
            <div className="text-xs sm:text-sm text-muted-foreground">Total Hits</div>
            <div className="text-xl sm:text-2xl font-bold text-amber-500">{stats.total_hits}</div>
          </div>
          <div className="bg-card border rounded-lg p-3 sm:p-4">
            <div className="text-xs sm:text-sm text-muted-foreground">Hits Today</div>
            <div className="text-xl sm:text-2xl font-bold text-orange-500">{stats.hits_today}</div>
          </div>
          <div className="bg-card border rounded-lg p-3 sm:p-4">
            <div className="text-xs sm:text-sm text-muted-foreground">Unique IPs</div>
            <div className="text-xl sm:text-2xl font-bold text-red-500">{stats.unique_ips}</div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4 sm:gap-6">
          {/* Top Traps */}
          <div className="bg-card border rounded-lg p-4 sm:p-5">
            <h3 className="font-semibold mb-3 flex items-center gap-2 text-sm sm:text-base">
              <Crosshair className="h-4 w-4 text-amber-500" /> Most Triggered
            </h3>
            {stats.top_traps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No hits yet</p>
            ) : (
              <div className="space-y-2">
                {stats.top_traps.map((t, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <code className="bg-muted px-2 py-0.5 rounded text-xs truncate max-w-[200px]">{t.path}</code>
                    <span className="font-mono font-bold text-amber-500">{t.hit_count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Top Attackers */}
          <div className="bg-card border rounded-lg p-4 sm:p-5">
            <h3 className="font-semibold mb-3 flex items-center gap-2 text-sm sm:text-base">
              <AlertTriangle className="h-4 w-4 text-red-500" /> Top Attackers
            </h3>
            {stats.top_attackers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No attackers yet</p>
            ) : (
              <div className="space-y-2">
                {stats.top_attackers.map((a, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <button onClick={() => onInvestigateIp(a.ip)} className="hover:underline"><IpAddress ip={a.ip} /></button>
                      {a.country && <span className="text-xs text-muted-foreground">{a.country}</span>}
                    </div>
                    <span className="font-mono font-bold text-red-500">{a.hits}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Hits */}
        <div className="bg-card border rounded-lg p-4 sm:p-5">
          <h3 className="font-semibold mb-3 text-sm sm:text-base">Recent Hits</h3>
          {stats.recent_hits.length === 0 ? (
            <p className="text-sm text-muted-foreground">No hits recorded yet</p>
          ) : (
            <div className="space-y-2">
              {stats.recent_hits.map((h, i) => (
                <div key={i} className="flex items-center gap-3 text-xs sm:text-sm py-1 border-b border-border/50 last:border-0 flex-wrap">
                  <span className="text-muted-foreground w-32 sm:w-36 shrink-0">{formatDate(h.timestamp)}</span>
                  <button onClick={() => onInvestigateIp(h.ip)} className="hover:underline"><IpAddress ip={h.ip} /></button>
                  <code className="bg-muted px-2 py-0.5 rounded text-xs">{h.path}</code>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  // ─── TRAPS TAB ──────────────────────────────────────────────
  if (activeSubTab === 'traps') {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={installDefaults} disabled={installingDefaults}>
            {installingDefaults ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
            Install Defaults
          </Button>
          <Button size="sm" onClick={() => { resetForm(); setShowDialog(true) }}>
            <Plus className="h-4 w-4 mr-1" /> Add Trap
          </Button>
        </div>

        {traps.length === 0 ? (
          <div className="text-center py-12 sm:py-20 text-muted-foreground">
            <Bug className="h-10 w-10 sm:h-12 sm:w-12 mx-auto mb-3 sm:mb-4 opacity-30" />
            <p>No honeypot traps configured</p>
            <p className="text-xs sm:text-sm mt-1">Click "Install Defaults" to get started</p>
          </div>
        ) : (
          <div className="space-y-3">
            {traps.map(trap => (
              <div key={trap.id} className={`bg-card border rounded-lg p-3 sm:p-4 ${!trap.enabled ? 'opacity-50' : ''}`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 sm:gap-2 mb-1 flex-wrap">
                      <span className="font-semibold text-sm sm:text-base">{trap.name}</span>
                      <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${trapTypeColors[trap.trap_type] || trapTypeColors.generic}`}>
                        {trapTypeLabels[trap.trap_type] || trap.trap_type}
                      </span>
                      <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full border ${severityColors[trap.severity]}`}>
                        {trap.severity}
                      </span>
                      {trap.auto_block && (
                        <span className="text-xs px-1.5 sm:px-2 py-0.5 rounded-full bg-red-500/10 text-red-500">
                          <Shield className="h-3 w-3 inline mr-0.5" />auto-block
                        </span>
                      )}
                    </div>
                    <code className="text-xs sm:text-sm text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded">{trap.path}</code>
                    <div className="text-xs text-muted-foreground mt-1.5">
                      {trap.hit_count} hits · Response: {trap.response_code}
                    </div>
                  </div>
                  <div className="flex items-center gap-0.5 sm:gap-1 shrink-0 ml-2">
                    <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8" onClick={() => toggleTrap(trap)}>
                      {trap.enabled ? <ToggleRight className="h-4 w-4 text-green-500" /> : <ToggleLeft className="h-4 w-4" />}
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8" onClick={() => openEditForm(trap)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8" onClick={() => deleteTrap(trap)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create/Edit Dialog */}
        {showDialog && (
          <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowDialog(false)}>
            <div className="bg-background border rounded-lg p-4 sm:p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
              <h2 className="text-lg font-bold mb-4">{editingTrap ? 'Edit' : 'Create'} Trap</h2>
              {error && <div className="text-sm text-red-500 bg-red-500/10 px-3 py-2 rounded mb-3">{error}</div>}
              <div className="space-y-3">
                <div>
                  <label className="text-sm font-medium">Name</label>
                  <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="WordPress Login" />
                </div>
                <div>
                  <label className="text-sm font-medium">Path</label>
                  <Input value={form.path} onChange={e => setForm({ ...form, path: e.target.value })} placeholder="/wp-login.php" className="font-mono" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium">Type</label>
                    <select value={form.trap_type} onChange={e => setForm({ ...form, trap_type: e.target.value })} className="w-full h-9 px-3 rounded-md border bg-background text-sm">
                      <option value="wordpress">WordPress</option>
                      <option value="phpmyadmin">phpMyAdmin</option>
                      <option value="admin">Admin</option>
                      <option value="api">API</option>
                      <option value="generic">Generic</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Severity</label>
                    <select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })} className="w-full h-9 px-3 rounded-md border bg-background text-sm">
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={form.auto_block} onChange={e => setForm({ ...form, auto_block: e.target.checked })} className="rounded" />
                    <span className="text-sm">Auto-block</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} className="rounded" />
                    <span className="text-sm">Enabled</span>
                  </label>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-6">
                <Button variant="outline" onClick={() => { setShowDialog(false); resetForm() }}>Cancel</Button>
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

  // ─── HITS TAB ───────────────────────────────────────────────
  if (activeSubTab === 'hits') {
    return (
      <div className="space-y-4">
        {hits.length === 0 ? (
          <div className="text-center py-12 sm:py-20 text-muted-foreground">
            <Eye className="h-10 w-10 sm:h-12 sm:w-12 mx-auto mb-3 sm:mb-4 opacity-30" />
            <p>No honeypot hits recorded</p>
          </div>
        ) : (
          <div className="bg-card border rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs">Time</th>
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs">IP</th>
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs">Trap</th>
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs hidden sm:table-cell">Method</th>
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs hidden md:table-cell">Country</th>
                    <th className="text-left px-2 sm:px-4 py-2 sm:py-3 font-medium text-xs">Action</th>
                    <th className="px-2 sm:px-4 py-2 sm:py-3 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {hits.map(hit => (
                    <tr key={hit.id} className="border-b border-border/50 hover:bg-muted/20">
                      <td className="px-2 sm:px-4 py-2 text-xs text-muted-foreground whitespace-nowrap">{formatDate(hit.timestamp)}</td>
                      <td className="px-2 sm:px-4 py-2"><IpAddress ip={hit.client_ip} /></td>
                      <td className="px-2 sm:px-4 py-2"><code className="text-xs bg-muted px-1.5 py-0.5 rounded">{hit.trap_path}</code></td>
                      <td className="px-2 sm:px-4 py-2 text-xs hidden sm:table-cell">{hit.request_method || '-'}</td>
                      <td className="px-2 sm:px-4 py-2 text-xs hidden md:table-cell">
                        {hit.country_code ? <CountryBadge code={hit.country_code} name={hit.country_name} /> : '-'}
                      </td>
                      <td className="px-2 sm:px-4 py-2">
                        <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${hit.action_taken === 'blocked' ? 'bg-red-500/10 text-red-500' : 'bg-slate-500/10 text-slate-400'}`}>
                          {hit.action_taken}
                        </span>
                      </td>
                      <td className="px-2 sm:px-4 py-2">
                        <Button variant="ghost" size="icon" className="h-6 w-6 sm:h-7 sm:w-7" onClick={() => onInvestigateIp(hit.client_ip)} title="Investigate">
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
    )
  }

  return null
}
