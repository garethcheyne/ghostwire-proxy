'use client'

import { useState, useEffect } from 'react'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Gauge,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Zap,
  Clock,
  Timer,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'

interface RateLimitRule {
  id: string
  proxy_host_id: string | null
  name: string
  requests_per_second: number | null
  requests_per_minute: number | null
  requests_per_hour: number | null
  burst_size: number
  action: string
  enabled: boolean
  created_at: string
  updated_at: string
}

const actionColors: Record<string, string> = {
  reject: 'bg-red-500/10 text-red-500',
  delay: 'bg-yellow-500/10 text-yellow-500',
  log: 'bg-slate-500/10 text-slate-400',
}

interface ProxyHostBasic {
  id: string
  domain_names: string[]
}

export default function RateLimitsPage() {
  const [rules, setRules] = useState<RateLimitRule[]>([])
  const [hosts, setHosts] = useState<ProxyHostBasic[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingRule, setEditingRule] = useState<RateLimitRule | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)

  // Form state
  const [formName, setFormName] = useState('')
  const [formRps, setFormRps] = useState('')
  const [formRpm, setFormRpm] = useState('')
  const [formRph, setFormRph] = useState('')
  const [formBurst, setFormBurst] = useState('10')
  const [formAction, setFormAction] = useState('reject')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formHostIds, setFormHostIds] = useState<string[]>([])
  const [hostDropdownOpen, setHostDropdownOpen] = useState(false)
  const confirm = useConfirm()

  usePageData(() => {
    fetchRules()
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  })

  useEffect(() => {
    if (!hostDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-host-dropdown]')) setHostDropdownOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [hostDropdownOpen])

  const fetchRules = async () => {
    try {
      const res = await api.get('/api/rate-limits')
      setRules(res.data)
    } catch (error) {
      console.error('Failed to fetch rate limits:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormRps('')
    setFormRpm('')
    setFormRph('')
    setFormBurst('10')
    setFormAction('reject')
    setFormEnabled(true)
    setFormHostIds([])
    setHostDropdownOpen(false)
    setError('')
  }

  const handleCreate = () => {
    resetForm()
    setEditingRule(null)
    setShowCreateDialog(true)
  }

  const handleEdit = (rule: RateLimitRule) => {
    setFormName(rule.name)
    setFormRps(rule.requests_per_second?.toString() || '')
    setFormRpm(rule.requests_per_minute?.toString() || '')
    setFormRph(rule.requests_per_hour?.toString() || '')
    setFormBurst(rule.burst_size.toString())
    setFormAction(rule.action)
    setFormEnabled(rule.enabled)
    setFormHostIds(rule.proxy_host_id ? [rule.proxy_host_id] : [])
    setEditingRule(rule)
    setShowCreateDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!formRps && !formRpm && !formRph) {
      setError('Set at least one rate limit (per second, minute, or hour)')
      return
    }

    setIsSubmitting(true)

    try {
      const baseData = {
        name: formName,
        requests_per_second: formRps ? parseInt(formRps) : null,
        requests_per_minute: formRpm ? parseInt(formRpm) : null,
        requests_per_hour: formRph ? parseInt(formRph) : null,
        burst_size: parseInt(formBurst) || 10,
        action: formAction,
        enabled: formEnabled,
      }

      if (editingRule) {
        await api.put(`/api/rate-limits/${editingRule.id}`, { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else if (formHostIds.length <= 1) {
        await api.post('/api/rate-limits', { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else {
        const results = await Promise.allSettled(
          formHostIds.map(hostId => api.post('/api/rate-limits', { ...baseData, proxy_host_id: hostId }))
        )
        const failures = results.filter(r => r.status === 'rejected')
        if (failures.length > 0 && failures.length < formHostIds.length) {
          setError(`Created for ${formHostIds.length - failures.length} hosts, failed for ${failures.length}`)
        } else if (failures.length === formHostIds.length) {
          throw (failures[0] as PromiseRejectedResult).reason
        }
      }

      setShowCreateDialog(false)
      fetchRules()
      toastSuccess(editingRule ? 'Rate limit rule updated' : 'Rate limit rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save rate limit rule')
      toastError('Failed to save rate limit rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (rule: RateLimitRule) => {
    if (!(await confirm({ description: `Delete rule "${rule.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/rate-limits/${rule.id}`)
      fetchRules()
      toastSuccess('Rate limit rule deleted')
    } catch (error) {
      console.error('Failed to delete rule:', error)
      toastError('Failed to delete rule')
    }
    setActiveDropdown(null)
  }

  const handleToggle = async (rule: RateLimitRule) => {
    try {
      await api.put(`/api/rate-limits/${rule.id}`, { enabled: !rule.enabled })
      fetchRules()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      console.error('Failed to toggle rule:', error)
      toastError('Failed to toggle rule')
    }
  }

  const formatLimit = (rule: RateLimitRule) => {
    const parts: string[] = []
    if (rule.requests_per_second) parts.push(`${rule.requests_per_second}/s`)
    if (rule.requests_per_minute) parts.push(`${rule.requests_per_minute}/min`)
    if (rule.requests_per_hour) parts.push(`${rule.requests_per_hour}/hr`)
    return parts.join(' · ') || 'No limits set'
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading rate limits...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Rate Limiting</h1>
          <p className="text-muted-foreground">
            Control request rates to protect your services
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add Rule
        </button>
      </div>

      <div className="space-y-3">
        {rules.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Gauge className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No rate limit rules configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Protect your services from excessive requests
            </p>
          </div>
        ) : (
          rules.map((rule) => (
            <div key={rule.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <button onClick={() => handleToggle(rule)} className="shrink-0">
                    {rule.enabled ? (
                      <ToggleRight className="h-6 w-6 text-green-500" />
                    ) : (
                      <ToggleLeft className="h-6 w-6 text-muted-foreground" />
                    )}
                  </button>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold">{rule.name}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${actionColors[rule.action] || actionColors.reject}`}>
                        {rule.action}
                      </span>
                      {!rule.proxy_host_id && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500">
                          All hosts
                        </span>
                      )}
                      {rule.proxy_host_id && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500">
                          {hosts.find(h => h.id === rule.proxy_host_id)?.domain_names[0] || 'Specific host'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-sm text-muted-foreground">
                      {rule.requests_per_second && (
                        <span className="flex items-center gap-1">
                          <Zap className="h-3.5 w-3.5" />
                          {rule.requests_per_second}/s
                        </span>
                      )}
                      {rule.requests_per_minute && (
                        <span className="flex items-center gap-1">
                          <Timer className="h-3.5 w-3.5" />
                          {rule.requests_per_minute}/min
                        </span>
                      )}
                      {rule.requests_per_hour && (
                        <span className="flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          {rule.requests_per_hour}/hr
                        </span>
                      )}
                      <span className="text-xs">
                        burst: {rule.burst_size}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="relative shrink-0 ml-4" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => setActiveDropdown(activeDropdown === rule.id ? null : rule.id)}
                    className="rounded-lg p-2 hover:bg-muted"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {activeDropdown === rule.id && (
                    <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-lg border border-border bg-card shadow-lg">
                      <div className="p-1">
                        <button
                          onClick={() => handleEdit(rule)}
                          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                        >
                          <Pencil className="h-4 w-4" />
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(rule)}
                          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create/Edit Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingRule ? 'Edit Rate Limit Rule' : 'Add Rate Limit Rule'}
              </h2>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="API rate limit"
                  required
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Per Second</label>
                  <input
                    type="number"
                    value={formRps}
                    onChange={(e) => setFormRps(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="—"
                    min="1"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Per Minute</label>
                  <input
                    type="number"
                    value={formRpm}
                    onChange={(e) => setFormRpm(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="—"
                    min="1"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Per Hour</label>
                  <input
                    type="number"
                    value={formRph}
                    onChange={(e) => setFormRph(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="—"
                    min="1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Burst Size</label>
                  <input
                    type="number"
                    value={formBurst}
                    onChange={(e) => setFormBurst(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    min="1"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select
                    value={formAction}
                    onChange={(e) => setFormAction(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="reject">Reject (429)</option>
                    <option value="delay">Delay</option>
                    <option value="log">Log only</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enabled"
                  checked={formEnabled}
                  onChange={(e) => setFormEnabled(e.target.checked)}
                  className="h-4 w-4"
                />
                <label htmlFor="enabled" className="text-sm">Enabled</label>
              </div>

              <div className="relative" data-host-dropdown>
                <label className="block text-sm font-medium mb-2">Apply to Host</label>
                <button
                  type="button"
                  onClick={() => setHostDropdownOpen(!hostDropdownOpen)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background text-sm text-left flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-primary"
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

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowCreateDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editingRule ? 'Save Changes' : 'Create Rule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
