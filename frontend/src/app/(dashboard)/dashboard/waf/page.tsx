'use client'

import { useState, useEffect } from 'react'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Shield,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'

interface WafRule {
  id: string
  rule_set_id: string | null
  proxy_host_id: string | null
  name: string
  description: string | null
  category: string
  pattern: string
  severity: string
  action: string
  enabled: boolean
  is_lua: boolean
  created_at: string
}

interface WafRuleSet {
  id: string
  name: string
  description: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

interface ProxyHostBasic {
  id: string
  domain_names: string[]
}

const categoryColors: Record<string, string> = {
  sqli: 'bg-red-500/10 text-red-500',
  xss: 'bg-orange-500/10 text-orange-500',
  path_traversal: 'bg-yellow-500/10 text-yellow-500',
  rce: 'bg-purple-500/10 text-purple-500',
  scanner: 'bg-blue-500/10 text-blue-500',
  custom: 'bg-cyan-500/10 text-cyan-500',
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

const actionColors: Record<string, string> = {
  log: 'bg-slate-500/10 text-slate-400',
  block: 'bg-red-500/10 text-red-500',
  blocklist: 'bg-purple-500/10 text-purple-500',
}

export default function WafPage() {
  const [rules, setRules] = useState<WafRule[]>([])
  const [ruleSets, setRuleSets] = useState<WafRuleSet[]>([])
  const [hosts, setHosts] = useState<ProxyHostBasic[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingRule, setEditingRule] = useState<WafRule | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [filterCategory, setFilterCategory] = useState('')

  // Form state
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formCategory, setFormCategory] = useState('custom')
  const [formPattern, setFormPattern] = useState('')
  const [formSeverity, setFormSeverity] = useState('medium')
  const [formAction, setFormAction] = useState('log')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formHostIds, setFormHostIds] = useState<string[]>([])
  const [hostDropdownOpen, setHostDropdownOpen] = useState(false)
  const confirm = useConfirm()

  usePageData(() => { fetchData() }, [filterCategory])

  useEffect(() => {
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!hostDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-host-dropdown]')) setHostDropdownOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [hostDropdownOpen])

  const fetchData = async () => {
    try {
      const params = filterCategory ? `?category=${filterCategory}` : ''
      const [rulesRes, setsRes] = await Promise.all([
        api.get(`/api/waf/rules${params}`),
        api.get('/api/waf/rules/sets'),
      ])
      setRules(rulesRes.data)
      setRuleSets(setsRes.data)
    } catch (error) {
      console.error('Failed to fetch WAF data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormDescription('')
    setFormCategory('custom')
    setFormPattern('')
    setFormSeverity('medium')
    setFormAction('log')
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

  const handleEdit = (rule: WafRule) => {
    setFormName(rule.name)
    setFormDescription(rule.description || '')
    setFormCategory(rule.category)
    setFormPattern(rule.pattern)
    setFormSeverity(rule.severity)
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

    // Validate regex pattern before submitting
    try {
      new RegExp(formPattern)
    } catch {
      setError('Invalid regex pattern — please check syntax')
      return
    }

    setIsSubmitting(true)

    try {
      const baseData = {
        name: formName,
        description: formDescription || null,
        category: formCategory,
        pattern: formPattern,
        severity: formSeverity,
        action: formAction,
        enabled: formEnabled,
      }

      if (editingRule) {
        await api.put(`/api/waf/rules/${editingRule.id}`, { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else if (formHostIds.length <= 1) {
        await api.post('/api/waf/rules', { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else {
        const results = await Promise.allSettled(
          formHostIds.map(hostId => api.post('/api/waf/rules', { ...baseData, proxy_host_id: hostId }))
        )
        const failures = results.filter(r => r.status === 'rejected')
        if (failures.length > 0 && failures.length < formHostIds.length) {
          setError(`Created for ${formHostIds.length - failures.length} hosts, failed for ${failures.length}`)
        } else if (failures.length === formHostIds.length) {
          throw (failures[0] as PromiseRejectedResult).reason
        }
      }

      setShowCreateDialog(false)
      fetchData()
      toastSuccess(editingRule ? 'WAF rule updated' : 'WAF rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save WAF rule')
      toastError('Failed to save WAF rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (rule: WafRule) => {
    if (!(await confirm({ description: `Are you sure you want to delete "${rule.name}"?`, variant: 'destructive' }))) return

    try {
      await api.delete(`/api/waf/rules/${rule.id}`)
      fetchData()
      toastSuccess('WAF rule deleted')
    } catch (error) {
      console.error('Failed to delete rule:', error)
      toastError('Failed to delete rule')
    }
    setActiveDropdown(null)
  }

  const handleToggle = async (rule: WafRule) => {
    try {
      await api.put(`/api/waf/rules/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      console.error('Failed to toggle rule:', error)
      toastError('Failed to toggle rule')
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading WAF rules...</div>
      </div>
    )
  }

  const categories = ['sqli', 'xss', 'path_traversal', 'rce', 'scanner', 'custom']

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">WAF Rules</h1>
          <p className="text-muted-foreground">
            Manage Web Application Firewall detection rules
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

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilterCategory('')}
          className={`rounded-lg px-3 py-1.5 text-sm ${!filterCategory ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/80'}`}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilterCategory(cat)}
            className={`rounded-lg px-3 py-1.5 text-sm capitalize ${filterCategory === cat ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/80'}`}
          >
            {cat.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Rules List */}
      <div className="space-y-3">
        {rules.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Shield className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No WAF rules configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click &quot;Add Rule&quot; to create detection patterns
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
                      <h3 className="font-semibold truncate">{rule.name}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${categoryColors[rule.category] || categoryColors.custom}`}>
                        {rule.category.replace('_', ' ')}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${severityColors[rule.severity] || severityColors.medium}`}>
                        {rule.severity}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${actionColors[rule.action] || actionColors.log}`}>
                        {rule.action}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500">
                        {rule.proxy_host_id ? hosts.find(h => h.id === rule.proxy_host_id)?.domain_names[0] || 'Specific host' : 'All hosts'}
                      </span>
                    </div>
                    {rule.description && (
                      <p className="text-sm text-muted-foreground mt-1">{rule.description}</p>
                    )}
                    <code className="text-xs text-muted-foreground mt-1 block truncate">{rule.pattern}</code>
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
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingRule ? 'Edit WAF Rule' : 'Add WAF Rule'}
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
                  placeholder="SQL Injection - UNION SELECT"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Description</label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  rows={2}
                  placeholder="Optional description"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Category</label>
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {categories.map((c) => (
                      <option key={c} value={c}>{c.replace('_', ' ')}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Severity</label>
                  <select
                    value={formSeverity}
                    onChange={(e) => setFormSeverity(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select
                    value={formAction}
                    onChange={(e) => setFormAction(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="log">Log only</option>
                    <option value="block">Block request</option>
                    <option value="blocklist">Block + Blocklist IP</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Pattern (Regex)</label>
                <input
                  type="text"
                  value={formPattern}
                  onChange={(e) => setFormPattern(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="union(\s)+select"
                  required
                />
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
