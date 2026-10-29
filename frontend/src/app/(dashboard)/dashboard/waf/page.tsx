'use client'

import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Shield,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'
import { Textarea } from '@/components/ui/textarea'
import { Modal, ModalBody } from '@/components/ui/modal'
import { useConfirm } from '@/components/confirm-dialog'
import { PageHeader } from '@/components/page-header'
import { ShieldAlert as HeaderIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { HostMultiPicker } from '@/components/host-multi-picker'
import { ContentSkeleton, LoadError } from '@/components/load-state'

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
  sqli: 'bg-red-500/10 text-red-600 dark:text-red-400',
  xss: 'bg-orange-500/10 text-orange-700 dark:text-orange-400',
  path_traversal: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400',
  rce: 'bg-purple-500/10 text-brand-2',
  scanner: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  probe: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
  protocol: 'bg-slate-500/10 text-muted-foreground',
  file_upload: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  injection: 'bg-red-500/10 text-red-600 dark:text-red-400',
  recon: 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
  dos: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
  custom: 'bg-cyan-500/10 text-brand',
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
}

const actionColors: Record<string, string> = {
  log: 'bg-slate-500/10 text-muted-foreground',
  block: 'bg-red-500/10 text-red-600 dark:text-red-400',
  blocklist: 'bg-purple-500/10 text-brand-2',
}

export default function WafPage() {
  const searchParams = useSearchParams()
  const highlightId = searchParams.get('highlight')
  const highlightRef = useRef<HTMLDivElement>(null)

  const [rules, setRules] = useState<WafRule[]>([])
  const [ruleSets, setRuleSets] = useState<WafRuleSet[]>([])
  const [hosts, setHosts] = useState<ProxyHostBasic[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingRule, setEditingRule] = useState<WafRule | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
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
  const confirm = useConfirm()

  useEffect(() => {
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  }, [])

  // Scroll to highlighted rule when data loads
  useEffect(() => {
    if (highlightId && !isLoading && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlightId, isLoading])

  const fetchData = async () => {
    try {
      setLoadError(false)
      const params = filterCategory ? `?category=${filterCategory}` : ''
      const [rulesRes, setsRes] = await Promise.all([
        api.get(`/api/waf/rules${params}`),
        api.get('/api/waf/rules/sets'),
      ])
      setRules(rulesRes.data)
      setRuleSets(setsRes.data)
    } catch (error) {
      console.error('Failed to fetch WAF data:', error)
      setLoadError(true)
    } finally {
      setIsLoading(false)
    }
  }

  usePageData(() => { fetchData() }, [filterCategory])

  const resetForm = () => {
    setFormName('')
    setFormDescription('')
    setFormCategory('custom')
    setFormPattern('')
    setFormSeverity('medium')
    setFormAction('log')
    setFormEnabled(true)
    setFormHostIds([])
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

  const categories = ['sqli', 'xss', 'path_traversal', 'rce', 'scanner', 'custom']

  return (
    <div className="space-y-6">
      <PageHeader
        icon={HeaderIcon}
        title="WAF Rules"
        description="Manage Web Application Firewall detection rules"
        actions={
          <>
            <Button
              size="lg"
              onClick={handleCreate}
              disabled={isLoading}
            >
              <Plus className="h-4 w-4" />
              Add Rule
            </Button>
          </>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={!filterCategory ? 'default' : 'outline'}
          onClick={() => setFilterCategory('')}
        >
          All
        </Button>
        {categories.map((cat) => (
          <Button
            key={cat}
            size="sm"
            variant={filterCategory === cat ? 'default' : 'outline'}
            onClick={() => setFilterCategory(cat)}
            className="capitalize"
          >
            {cat.replace('_', ' ')}
          </Button>
        ))}
      </div>

      {/* Rules List */}
      <div className="space-y-3">
        {isLoading ? (
          <ContentSkeleton rows={5} />
        ) : loadError ? (
          <LoadError what="WAF rules" onRetry={fetchData} />
        ) : rules.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Shield className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No WAF rules configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click &quot;Add Rule&quot; to create detection patterns
            </p>
          </div>
        ) : (
          rules.map((rule) => (
            <div
              key={rule.id}
              ref={rule.id === highlightId ? highlightRef : undefined}
              className={`rounded-xl border bg-card p-4 transition-all duration-500 ${
                rule.id === highlightId
                  ? 'border-blue-500 ring-2 ring-blue-500/30 bg-blue-500/5'
                  : 'border-border'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <Switch checked={rule.enabled} onCheckedChange={() => handleToggle(rule)} aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`} />
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
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400">
                        {rule.proxy_host_id ? hosts.find(h => h.id === rule.proxy_host_id)?.domain_names[0] || 'Specific host' : 'All hosts'}
                      </span>
                    </div>
                    {rule.description && (
                      <p className="text-sm text-muted-foreground mt-1">{rule.description}</p>
                    )}
                    <code className="text-xs text-muted-foreground mt-1 block truncate">{rule.pattern}</code>
                  </div>
                </div>

                <div className="shrink-0 ml-4" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label="Actions">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      <DropdownMenuItem
                        onSelect={() => handleEdit(rule)}
                        className="gap-2"
                      >
                        <Pencil className="h-4 w-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onSelect={() => handleDelete(rule)}
                        className="gap-2 text-red-600 dark:text-red-400 focus:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Modal
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        size="lg"
        srTitle="Waf — Create"
      >
        <ModalBody className="p-0">
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
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                  placeholder="SQL Injection - UNION SELECT"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Description</label>
                <Textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  className="w-full rounded-lg bg-background"
                  rows={2}
                  placeholder="Optional description"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Category</label>
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background font-mono text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
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

              <div>
                <label className="block text-sm font-medium mb-2">Apply to Host</label>
                <HostMultiPicker hosts={hosts} value={formHostIds} onChange={setFormHostIds} />
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <Button
                  variant="outline"
                  size="lg"
                  type="button"
                  onClick={() => setShowCreateDialog(false)}
                >
                  Cancel
                </Button>
                <Button
                  size="lg"
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editingRule ? 'Save Changes' : 'Create Rule'}
                </Button>
              </div>
            </form>
        </ModalBody>
      </Modal>
    </div>
  )
}
