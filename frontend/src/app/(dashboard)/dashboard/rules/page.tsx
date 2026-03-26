'use client'

import { useState, useEffect } from 'react'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Shield,
  ShieldAlert,
  Map,
  Gauge,
  Sparkles,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Search,
  Database,
  RefreshCw,
  CheckCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Info,
  Zap,
  Clock,
  Timer,
  Globe,
  AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { IpAddress } from '@/components/ip-address'
import { COUNTRIES, COUNTRY_MAP } from '@/lib/countries'

type TabType = 'waf' | 'geoip' | 'rate-limits' | 'presets'

// ═══════════════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════════════

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

interface GeoipRule {
  id: string
  proxy_host_id: string | null
  name: string
  mode: string
  countries: string
  action: string
  enabled: boolean
  created_at: string
  updated_at: string
}

interface GeoipDbInfo {
  installed: boolean
  size_bytes: number
  last_modified: string | null
}

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

interface PresetSummary {
  id: string
  name: string
  description: string
  category: string
  severity: string
  tags: string[]
  version: string
  rule_count: number
  applied: boolean
}

interface PresetDetail {
  id: string
  name: string
  description: string
  category: string
  severity: string
  tags: string[]
  version: string
  author: string
  rules?: Array<{ name: string; notes?: string }>
  thresholds?: Array<{ name: string; notes?: string }>
}

interface ProxyHostBasic {
  id: string
  domain_names: string[]
}

// ═══════════════════════════════════════════════════════════════
// COLOR MAPS
// ═══════════════════════════════════════════════════════════════

const wafCategoryColors: Record<string, string> = {
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
  reject: 'bg-red-500/10 text-red-500',
  delay: 'bg-yellow-500/10 text-yellow-500',
  challenge: 'bg-yellow-500/10 text-yellow-500',
}

const geoModeColors: Record<string, string> = {
  blocklist: 'bg-red-500/10 text-red-500',
  allowlist: 'bg-green-500/10 text-green-500',
}

const presetCategoryConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  waf: { label: 'WAF Rules', icon: Shield, color: 'text-red-400' },
  geoip: { label: 'GeoIP', icon: Globe, color: 'text-blue-400' },
  rate_limit: { label: 'Rate Limiting', icon: Gauge, color: 'text-yellow-400' },
  threat_response: { label: 'Threat Response', icon: AlertTriangle, color: 'text-purple-400' },
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export default function RulesPage() {
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<TabType>('waf')
  const [hosts, setHosts] = useState<ProxyHostBasic[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // WAF State
  const [wafRules, setWafRules] = useState<WafRule[]>([])
  const [wafFilterCategory, setWafFilterCategory] = useState('')
  const [showWafDialog, setShowWafDialog] = useState(false)
  const [editingWafRule, setEditingWafRule] = useState<WafRule | null>(null)

  // GeoIP State
  const [geoRules, setGeoRules] = useState<GeoipRule[]>([])
  const [geoDbInfo, setGeoDbInfo] = useState<GeoipDbInfo | null>(null)
  const [showGeoDialog, setShowGeoDialog] = useState(false)
  const [editingGeoRule, setEditingGeoRule] = useState<GeoipRule | null>(null)
  const [isUpdatingGeoDb, setIsUpdatingGeoDb] = useState(false)
  const [geoSubTab, setGeoSubTab] = useState<'rules' | 'lookup'>('rules')
  const [lookupIp, setLookupIp] = useState('')
  const [lookupResult, setLookupResult] = useState<any>(null)
  const [lookupLoading, setLookupLoading] = useState(false)

  // Rate Limit State
  const [rateLimitRules, setRateLimitRules] = useState<RateLimitRule[]>([])
  const [showRateLimitDialog, setShowRateLimitDialog] = useState(false)
  const [editingRateLimitRule, setEditingRateLimitRule] = useState<RateLimitRule | null>(null)

  // Presets State
  const [presets, setPresets] = useState<PresetSummary[]>([])
  const [expandedPreset, setExpandedPreset] = useState<string | null>(null)
  const [presetDetail, setPresetDetail] = useState<PresetDetail | null>(null)
  const [presetDetailLoading, setPresetDetailLoading] = useState(false)
  const [applyingPreset, setApplyingPreset] = useState<string | null>(null)
  const [removingPreset, setRemovingPreset] = useState<string | null>(null)
  const [presetFilter, setPresetFilter] = useState<string | null>(null)

  // General
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Form state for WAF
  const [wafForm, setWafForm] = useState({
    name: '', description: '', category: 'custom', pattern: '', severity: 'medium', action: 'log', enabled: true, hostId: ''
  })

  // Form state for GeoIP
  const [geoForm, setGeoForm] = useState({
    name: '', mode: 'blocklist', countries: [] as string[], action: 'block', enabled: true, hostIds: [] as string[]
  })
  const [countrySearch, setCountrySearch] = useState('')
  const [hostDropdownOpen, setHostDropdownOpen] = useState(false)

  // Form state for Rate Limits
  const [rateLimitForm, setRateLimitForm] = useState({
    name: '', rps: '', rpm: '', rph: '', burst: '10', action: 'reject', enabled: true, hostIds: [] as string[]
  })
  const [rlHostDropdownOpen, setRlHostDropdownOpen] = useState(false)

  // ─────────────────────────────────────────────────────────────
  // DATA FETCHING
  // ─────────────────────────────────────────────────────────────

  usePageData(() => {
    fetchData()
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  }, [activeTab, wafFilterCategory])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'waf') {
        const params = wafFilterCategory ? `?category=${wafFilterCategory}` : ''
        const res = await api.get(`/api/waf/rules${params}`)
        setWafRules(res.data)
      } else if (activeTab === 'geoip') {
        const [rulesRes, dbRes] = await Promise.all([
          api.get('/api/geoip/rules'),
          api.get('/api/geoip/database/status').catch(() => ({ data: null })),
        ])
        setGeoRules(rulesRes.data)
        if (dbRes.data) setGeoDbInfo(dbRes.data)
      } else if (activeTab === 'rate-limits') {
        const res = await api.get('/api/rate-limits')
        setRateLimitRules(res.data)
      } else if (activeTab === 'presets') {
        const res = await api.get('/api/presets')
        setPresets(res.data)
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Close dropdowns on outside click
  useEffect(() => {
    if (!hostDropdownOpen && !rlHostDropdownOpen) return
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-host-dropdown]')) {
        setHostDropdownOpen(false)
        setRlHostDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [hostDropdownOpen, rlHostDropdownOpen])

  // ─────────────────────────────────────────────────────────────
  // WAF HANDLERS
  // ─────────────────────────────────────────────────────────────

  const resetWafForm = () => {
    setWafForm({ name: '', description: '', category: 'custom', pattern: '', severity: 'medium', action: 'log', enabled: true, hostId: '' })
    setError('')
  }

  const handleCreateWaf = () => {
    resetWafForm()
    setEditingWafRule(null)
    setShowWafDialog(true)
  }

  const handleEditWaf = (rule: WafRule) => {
    setWafForm({
      name: rule.name,
      description: rule.description || '',
      category: rule.category,
      pattern: rule.pattern,
      severity: rule.severity,
      action: rule.action,
      enabled: rule.enabled,
      hostId: rule.proxy_host_id || ''
    })
    setEditingWafRule(rule)
    setShowWafDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitWaf = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try { new RegExp(wafForm.pattern) } catch { setError('Invalid regex pattern'); return }
    setIsSubmitting(true)
    try {
      const data = {
        name: wafForm.name,
        description: wafForm.description || null,
        category: wafForm.category,
        pattern: wafForm.pattern,
        severity: wafForm.severity,
        action: wafForm.action,
        enabled: wafForm.enabled,
        proxy_host_id: wafForm.hostId || null,
      }
      if (editingWafRule) {
        await api.put(`/api/waf/rules/${editingWafRule.id}`, data)
      } else {
        await api.post('/api/waf/rules', data)
      }
      setShowWafDialog(false)
      fetchData()
      toastSuccess(editingWafRule ? 'WAF rule updated' : 'WAF rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save WAF rule')
      toastError('Failed to save WAF rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteWaf = async (rule: WafRule) => {
    if (!(await confirm({ description: `Delete "${rule.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/waf/rules/${rule.id}`)
      fetchData()
      toastSuccess('WAF rule deleted')
    } catch (error) {
      toastError('Failed to delete rule')
    }
    setActiveDropdown(null)
  }

  const handleToggleWaf = async (rule: WafRule) => {
    try {
      await api.put(`/api/waf/rules/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      toastError('Failed to toggle rule')
    }
  }

  // ─────────────────────────────────────────────────────────────
  // GEOIP HANDLERS
  // ─────────────────────────────────────────────────────────────

  const resetGeoForm = () => {
    setGeoForm({ name: '', mode: 'blocklist', countries: [], action: 'block', enabled: true, hostIds: [] })
    setCountrySearch('')
    setHostDropdownOpen(false)
    setError('')
  }

  const handleCreateGeo = () => {
    resetGeoForm()
    setEditingGeoRule(null)
    setShowGeoDialog(true)
  }

  const handleEditGeo = (rule: GeoipRule) => {
    let countries: string[] = []
    try { countries = JSON.parse(rule.countries) } catch {}
    setGeoForm({
      name: rule.name,
      mode: rule.mode,
      countries,
      action: rule.action,
      enabled: rule.enabled,
      hostIds: rule.proxy_host_id ? [rule.proxy_host_id] : []
    })
    setEditingGeoRule(rule)
    setShowGeoDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitGeo = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (geoForm.countries.length === 0) { setError('Select at least one country'); return }
    setIsSubmitting(true)
    try {
      const baseData = {
        name: geoForm.name,
        mode: geoForm.mode,
        countries: JSON.stringify(geoForm.countries),
        action: geoForm.action,
        enabled: geoForm.enabled,
      }
      if (editingGeoRule) {
        await api.put(`/api/geoip/rules/${editingGeoRule.id}`, { ...baseData, proxy_host_id: geoForm.hostIds[0] || null })
      } else if (geoForm.hostIds.length <= 1) {
        await api.post('/api/geoip/rules', { ...baseData, proxy_host_id: geoForm.hostIds[0] || null })
      } else {
        await Promise.all(geoForm.hostIds.map(hostId => api.post('/api/geoip/rules', { ...baseData, proxy_host_id: hostId })))
      }
      setShowGeoDialog(false)
      fetchData()
      toastSuccess(editingGeoRule ? 'GeoIP rule updated' : 'GeoIP rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save GeoIP rule')
      toastError('Failed to save GeoIP rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteGeo = async (rule: GeoipRule) => {
    if (!(await confirm({ description: `Delete rule "${rule.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/geoip/rules/${rule.id}`)
      fetchData()
      toastSuccess('GeoIP rule deleted')
    } catch (error) {
      toastError('Failed to delete rule')
    }
    setActiveDropdown(null)
  }

  const handleToggleGeo = async (rule: GeoipRule) => {
    try {
      await api.put(`/api/geoip/rules/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      toastError('Failed to toggle rule')
    }
  }

  const handleUpdateGeoDb = async () => {
    setIsUpdatingGeoDb(true)
    try {
      await api.post('/api/geoip/database/update')
      const res = await api.get('/api/geoip/database/status')
      setGeoDbInfo(res.data)
      toastSuccess('GeoIP database updated')
    } catch (err: any) {
      toastError('Failed to update GeoIP database')
    } finally {
      setIsUpdatingGeoDb(false)
    }
  }

  const handleGeoLookup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lookupIp.trim()) return
    setLookupLoading(true)
    setLookupResult(null)
    try {
      const res = await api.get(`/api/geoip/lookup/${lookupIp.trim()}`)
      setLookupResult(res.data)
    } catch (err: any) {
      toastError('Lookup failed')
    } finally {
      setLookupLoading(false)
    }
  }

  const toggleCountry = (code: string) => {
    setGeoForm(f => ({
      ...f,
      countries: f.countries.includes(code) ? f.countries.filter(c => c !== code) : [...f.countries, code]
    }))
  }

  // ─────────────────────────────────────────────────────────────
  // RATE LIMIT HANDLERS
  // ─────────────────────────────────────────────────────────────

  const resetRateLimitForm = () => {
    setRateLimitForm({ name: '', rps: '', rpm: '', rph: '', burst: '10', action: 'reject', enabled: true, hostIds: [] })
    setRlHostDropdownOpen(false)
    setError('')
  }

  const handleCreateRateLimit = () => {
    resetRateLimitForm()
    setEditingRateLimitRule(null)
    setShowRateLimitDialog(true)
  }

  const handleEditRateLimit = (rule: RateLimitRule) => {
    setRateLimitForm({
      name: rule.name,
      rps: rule.requests_per_second?.toString() || '',
      rpm: rule.requests_per_minute?.toString() || '',
      rph: rule.requests_per_hour?.toString() || '',
      burst: rule.burst_size.toString(),
      action: rule.action,
      enabled: rule.enabled,
      hostIds: rule.proxy_host_id ? [rule.proxy_host_id] : []
    })
    setEditingRateLimitRule(rule)
    setShowRateLimitDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitRateLimit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!rateLimitForm.rps && !rateLimitForm.rpm && !rateLimitForm.rph) {
      setError('Set at least one rate limit')
      return
    }
    setIsSubmitting(true)
    try {
      const baseData = {
        name: rateLimitForm.name,
        requests_per_second: rateLimitForm.rps ? parseInt(rateLimitForm.rps) : null,
        requests_per_minute: rateLimitForm.rpm ? parseInt(rateLimitForm.rpm) : null,
        requests_per_hour: rateLimitForm.rph ? parseInt(rateLimitForm.rph) : null,
        burst_size: parseInt(rateLimitForm.burst) || 10,
        action: rateLimitForm.action,
        enabled: rateLimitForm.enabled,
      }
      if (editingRateLimitRule) {
        await api.put(`/api/rate-limits/${editingRateLimitRule.id}`, { ...baseData, proxy_host_id: rateLimitForm.hostIds[0] || null })
      } else if (rateLimitForm.hostIds.length <= 1) {
        await api.post('/api/rate-limits', { ...baseData, proxy_host_id: rateLimitForm.hostIds[0] || null })
      } else {
        await Promise.all(rateLimitForm.hostIds.map(hostId => api.post('/api/rate-limits', { ...baseData, proxy_host_id: hostId })))
      }
      setShowRateLimitDialog(false)
      fetchData()
      toastSuccess(editingRateLimitRule ? 'Rate limit rule updated' : 'Rate limit rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save rate limit rule')
      toastError('Failed to save rate limit rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteRateLimit = async (rule: RateLimitRule) => {
    if (!(await confirm({ description: `Delete rule "${rule.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/rate-limits/${rule.id}`)
      fetchData()
      toastSuccess('Rate limit rule deleted')
    } catch (error) {
      toastError('Failed to delete rule')
    }
    setActiveDropdown(null)
  }

  const handleToggleRateLimit = async (rule: RateLimitRule) => {
    try {
      await api.put(`/api/rate-limits/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      toastError('Failed to toggle rule')
    }
  }

  // ─────────────────────────────────────────────────────────────
  // PRESET HANDLERS
  // ─────────────────────────────────────────────────────────────

  const togglePresetExpand = async (presetId: string) => {
    if (expandedPreset === presetId) {
      setExpandedPreset(null)
      setPresetDetail(null)
      return
    }
    setExpandedPreset(presetId)
    setPresetDetailLoading(true)
    try {
      const { data } = await api.get(`/api/presets/${presetId}`)
      setPresetDetail(data)
    } catch (err) {
      console.error('Failed to fetch preset detail:', err)
    } finally {
      setPresetDetailLoading(false)
    }
  }

  const applyPreset = async (presetId: string) => {
    setApplyingPreset(presetId)
    try {
      await api.post(`/api/presets/${presetId}/apply`)
      setPresets(prev => prev.map(p => p.id === presetId ? { ...p, applied: true } : p))
      toastSuccess('Preset applied')
    } catch (err) {
      toastError('Failed to apply preset')
    } finally {
      setApplyingPreset(null)
    }
  }

  const removePreset = async (presetId: string) => {
    setRemovingPreset(presetId)
    try {
      await api.delete(`/api/presets/${presetId}/remove`)
      setPresets(prev => prev.map(p => p.id === presetId ? { ...p, applied: false } : p))
      toastSuccess('Preset removed')
    } catch (err) {
      toastError('Failed to remove preset')
    } finally {
      setRemovingPreset(null)
    }
  }

  // ─────────────────────────────────────────────────────────────
  // HELPERS
  // ─────────────────────────────────────────────────────────────

  const parseCountries = (countries: string): string[] => {
    try { return JSON.parse(countries) } catch { return [] }
  }

  const wafCategories = ['sqli', 'xss', 'path_traversal', 'rce', 'scanner', 'custom']
  const presetCategories = ['waf', 'geoip', 'rate_limit', 'threat_response']
  const filteredPresets = presetFilter ? presets.filter(p => p.category === presetFilter) : presets

  // ═══════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6 text-cyan-400" />
            Security Rules
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground">
            Configure WAF, GeoIP blocking, rate limiting, and security presets
          </p>
        </div>
        {activeTab !== 'presets' && (
          <Button
            onClick={() => {
              if (activeTab === 'waf') handleCreateWaf()
              else if (activeTab === 'geoip') handleCreateGeo()
              else if (activeTab === 'rate-limits') handleCreateRateLimit()
            }}
            className="shrink-0"
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Rule
          </Button>
        )}
      </div>

      {/* Main Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1 overflow-x-auto">
        {[
          { key: 'waf', label: 'WAF Rules', icon: ShieldAlert },
          { key: 'geoip', label: 'GeoIP', icon: Map },
          { key: 'rate-limits', label: 'Rate Limits', icon: Gauge },
          { key: 'presets', label: 'Presets', icon: Sparkles },
        ].map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as TabType)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.key
                  ? 'bg-background shadow-sm'
                  : 'hover:bg-background/50 text-muted-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          )
        })}
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* ════════════════ WAF TAB ════════════════ */}
          {activeTab === 'waf' && (
            <div className="space-y-4">
              {/* Category Filters */}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setWafFilterCategory('')}
                  className={`rounded-lg px-3 py-1.5 text-sm ${!wafFilterCategory ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/80'}`}
                >
                  All
                </button>
                {wafCategories.map(cat => (
                  <button
                    key={cat}
                    onClick={() => setWafFilterCategory(cat)}
                    className={`rounded-lg px-3 py-1.5 text-sm capitalize ${wafFilterCategory === cat ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/80'}`}
                  >
                    {cat.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {/* Rules List */}
              <div className="space-y-3">
                {wafRules.length === 0 ? (
                  <div className="rounded-xl border border-border bg-card p-8 sm:p-12 text-center">
                    <ShieldAlert className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
                    <p className="text-muted-foreground">No WAF rules configured</p>
                  </div>
                ) : (
                  wafRules.map(rule => (
                    <div key={rule.id} className="rounded-xl border border-border bg-card p-3 sm:p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
                          <button onClick={() => handleToggleWaf(rule)} className="shrink-0">
                            {rule.enabled ? <ToggleRight className="h-5 w-5 sm:h-6 sm:w-6 text-green-500" /> : <ToggleLeft className="h-5 w-5 sm:h-6 sm:w-6 text-muted-foreground" />}
                          </button>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                              <h3 className="font-semibold text-sm sm:text-base truncate">{rule.name}</h3>
                              <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${wafCategoryColors[rule.category] || wafCategoryColors.custom}`}>
                                {rule.category.replace('_', ' ')}
                              </span>
                              <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full border ${severityColors[rule.severity]}`}>
                                {rule.severity}
                              </span>
                            </div>
                            <code className="text-xs text-muted-foreground mt-1 block truncate">{rule.pattern}</code>
                          </div>
                        </div>
                        <div className="relative shrink-0 ml-2">
                          <button onClick={() => setActiveDropdown(activeDropdown === rule.id ? null : rule.id)} className="rounded-lg p-2 hover:bg-muted">
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                          {activeDropdown === rule.id && (
                            <div className="absolute right-0 top-full z-10 mt-1 w-32 sm:w-40 rounded-lg border border-border bg-card shadow-lg">
                              <div className="p-1">
                                <button onClick={() => handleEditWaf(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted">
                                  <Pencil className="h-4 w-4" /> Edit
                                </button>
                                <button onClick={() => handleDeleteWaf(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted">
                                  <Trash2 className="h-4 w-4" /> Delete
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
            </div>
          )}

          {/* ════════════════ GEOIP TAB ════════════════ */}
          {activeTab === 'geoip' && (
            <div className="space-y-4">
              {/* GeoIP Database Status */}
              <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Database className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <h3 className="font-semibold text-sm sm:text-base">GeoIP Database</h3>
                      <p className="text-xs sm:text-sm text-muted-foreground">DB-IP Country Lite</p>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleUpdateGeoDb} disabled={isUpdatingGeoDb}>
                    {isUpdatingGeoDb ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    <span className="ml-1.5">{isUpdatingGeoDb ? 'Updating...' : 'Update'}</span>
                  </Button>
                </div>
                {geoDbInfo && (
                  <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-4">
                    <div className="rounded-lg border border-border p-2 sm:p-3">
                      <p className="text-xs text-muted-foreground">Status</p>
                      <div className="flex items-center gap-1 mt-1">
                        {geoDbInfo.installed ? <><CheckCircle className="h-3 w-3 sm:h-4 sm:w-4 text-green-500" /><span className="text-xs sm:text-sm font-medium text-green-500">OK</span></> : <span className="text-xs sm:text-sm text-red-500">Missing</span>}
                      </div>
                    </div>
                    <div className="rounded-lg border border-border p-2 sm:p-3">
                      <p className="text-xs text-muted-foreground">Size</p>
                      <p className="text-xs sm:text-sm font-medium mt-1">{geoDbInfo.size_bytes ? `${(geoDbInfo.size_bytes / 1024 / 1024).toFixed(1)} MB` : '-'}</p>
                    </div>
                    <div className="rounded-lg border border-border p-2 sm:p-3">
                      <p className="text-xs text-muted-foreground">Updated</p>
                      <p className="text-xs sm:text-sm font-medium mt-1">{geoDbInfo.last_modified ? new Date(geoDbInfo.last_modified).toLocaleDateString() : '-'}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Sub-tabs */}
              <div className="flex gap-1 rounded-lg bg-muted/50 p-1">
                {(['rules', 'lookup'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setGeoSubTab(tab)}
                    className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize transition-colors ${geoSubTab === tab ? 'bg-background shadow-sm' : 'hover:bg-background/50 text-muted-foreground'}`}
                  >
                    {tab === 'lookup' ? 'IP Lookup' : 'Rules'}
                  </button>
                ))}
              </div>

              {geoSubTab === 'rules' ? (
                <div className="space-y-3">
                  {geoRules.length === 0 ? (
                    <div className="rounded-xl border border-border bg-card p-8 sm:p-12 text-center">
                      <Map className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
                      <p className="text-muted-foreground">No GeoIP rules configured</p>
                    </div>
                  ) : (
                    geoRules.map(rule => {
                      const countries = parseCountries(rule.countries)
                      return (
                        <div key={rule.id} className="rounded-xl border border-border bg-card p-3 sm:p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
                              <button onClick={() => handleToggleGeo(rule)} className="shrink-0">
                                {rule.enabled ? <ToggleRight className="h-5 w-5 sm:h-6 sm:w-6 text-green-500" /> : <ToggleLeft className="h-5 w-5 sm:h-6 sm:w-6 text-muted-foreground" />}
                              </button>
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                  <h3 className="font-semibold text-sm sm:text-base">{rule.name}</h3>
                                  <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${geoModeColors[rule.mode]}`}>{rule.mode}</span>
                                  <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${actionColors[rule.action]}`}>{rule.action}</span>
                                </div>
                                <div className="flex flex-wrap gap-1 mt-1.5">
                                  {countries.slice(0, 6).map(code => (
                                    <span key={code} className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono">{code}</span>
                                  ))}
                                  {countries.length > 6 && <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">+{countries.length - 6}</span>}
                                </div>
                              </div>
                            </div>
                            <div className="relative shrink-0 ml-2">
                              <button onClick={() => setActiveDropdown(activeDropdown === rule.id ? null : rule.id)} className="rounded-lg p-2 hover:bg-muted">
                                <MoreHorizontal className="h-4 w-4" />
                              </button>
                              {activeDropdown === rule.id && (
                                <div className="absolute right-0 top-full z-10 mt-1 w-32 sm:w-40 rounded-lg border border-border bg-card shadow-lg">
                                  <div className="p-1">
                                    <button onClick={() => handleEditGeo(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"><Pencil className="h-4 w-4" /> Edit</button>
                                    <button onClick={() => handleDeleteGeo(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"><Trash2 className="h-4 w-4" /> Delete</button>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              ) : (
                <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
                  <form onSubmit={handleGeoLookup} className="flex gap-2 sm:gap-3 mb-6">
                    <input
                      type="text"
                      value={lookupIp}
                      onChange={e => setLookupIp(e.target.value)}
                      className="flex-1 px-3 sm:px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                      placeholder="8.8.8.8"
                    />
                    <Button type="submit" disabled={lookupLoading}>
                      {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                      <span className="ml-1.5 hidden sm:inline">Lookup</span>
                    </Button>
                  </form>
                  {lookupResult && (
                    <div className="rounded-lg border border-border p-3 sm:p-4 space-y-2">
                      <div className="grid grid-cols-2 gap-3 sm:gap-4 text-sm">
                        <div><span className="text-muted-foreground">IP:</span><div className="mt-0.5"><IpAddress ip={lookupResult.ip} countryCode={lookupResult.country_code} countryName={lookupResult.country_name} /></div></div>
                        <div><span className="text-muted-foreground">Country:</span><p className="font-medium">{lookupResult.country_name || 'Unknown'}</p></div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ════════════════ RATE LIMITS TAB ════════════════ */}
          {activeTab === 'rate-limits' && (
            <div className="space-y-3">
              {rateLimitRules.length === 0 ? (
                <div className="rounded-xl border border-border bg-card p-8 sm:p-12 text-center">
                  <Gauge className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
                  <p className="text-muted-foreground">No rate limit rules configured</p>
                </div>
              ) : (
                rateLimitRules.map(rule => (
                  <div key={rule.id} className="rounded-xl border border-border bg-card p-3 sm:p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
                        <button onClick={() => handleToggleRateLimit(rule)} className="shrink-0">
                          {rule.enabled ? <ToggleRight className="h-5 w-5 sm:h-6 sm:w-6 text-green-500" /> : <ToggleLeft className="h-5 w-5 sm:h-6 sm:w-6 text-muted-foreground" />}
                        </button>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                            <h3 className="font-semibold text-sm sm:text-base">{rule.name}</h3>
                            <span className={`text-xs px-1.5 sm:px-2 py-0.5 rounded-full ${actionColors[rule.action]}`}>{rule.action}</span>
                            <span className="text-xs px-1.5 sm:px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500">
                              {rule.proxy_host_id ? hosts.find(h => h.id === rule.proxy_host_id)?.domain_names[0] || 'Host' : 'All'}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 sm:gap-3 mt-1.5 text-xs sm:text-sm text-muted-foreground flex-wrap">
                            {rule.requests_per_second && <span className="flex items-center gap-1"><Zap className="h-3 w-3" />{rule.requests_per_second}/s</span>}
                            {rule.requests_per_minute && <span className="flex items-center gap-1"><Timer className="h-3 w-3" />{rule.requests_per_minute}/min</span>}
                            {rule.requests_per_hour && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{rule.requests_per_hour}/hr</span>}
                            <span className="text-xs">burst: {rule.burst_size}</span>
                          </div>
                        </div>
                      </div>
                      <div className="relative shrink-0 ml-2">
                        <button onClick={() => setActiveDropdown(activeDropdown === rule.id ? null : rule.id)} className="rounded-lg p-2 hover:bg-muted">
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                        {activeDropdown === rule.id && (
                          <div className="absolute right-0 top-full z-10 mt-1 w-32 sm:w-40 rounded-lg border border-border bg-card shadow-lg">
                            <div className="p-1">
                              <button onClick={() => handleEditRateLimit(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"><Pencil className="h-4 w-4" /> Edit</button>
                              <button onClick={() => handleDeleteRateLimit(rule)} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"><Trash2 className="h-4 w-4" /> Delete</button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* ════════════════ PRESETS TAB ════════════════ */}
          {activeTab === 'presets' && (
            <div className="space-y-4">
              {/* Category Filters */}
              <div className="flex flex-wrap gap-2">
                <Button variant={!presetFilter ? 'default' : 'outline'} size="sm" onClick={() => setPresetFilter(null)}>All</Button>
                {presetCategories.map(cat => {
                  const config = presetCategoryConfig[cat]
                  const Icon = config.icon
                  return (
                    <Button key={cat} variant={presetFilter === cat ? 'default' : 'outline'} size="sm" onClick={() => setPresetFilter(presetFilter === cat ? null : cat)}>
                      <Icon className={`h-4 w-4 mr-1 ${config.color}`} /> {config.label}
                    </Button>
                  )
                })}
              </div>

              {/* Presets List */}
              <div className="space-y-3">
                {filteredPresets.length === 0 ? (
                  <div className="text-center text-muted-foreground py-12">No presets available</div>
                ) : (
                  filteredPresets.map(preset => {
                    const isExpanded = expandedPreset === preset.id
                    const isApplied = preset.applied
                    const isApplying = applyingPreset === preset.id
                    const isRemoving = removingPreset === preset.id
                    return (
                      <div key={preset.id} className="border border-border rounded-lg bg-card overflow-hidden">
                        <div
                          className="flex items-center justify-between p-3 sm:p-4 cursor-pointer hover:bg-muted/50 transition-colors"
                          onClick={() => togglePresetExpand(preset.id)}
                        >
                          <div className="flex items-center gap-2 sm:gap-3 flex-1 min-w-0">
                            {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />}
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                <span className="font-medium text-sm sm:text-base">{preset.name}</span>
                                <Badge variant="outline" className={severityColors[preset.severity]}>{preset.severity}</Badge>
                                {preset.tags.includes('recommended') && <Badge className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20">recommended</Badge>}
                                {isApplied && <Badge className="bg-green-500/10 text-green-400 border-green-500/20"><Check className="h-3 w-3 mr-1" />Applied</Badge>}
                              </div>
                              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 truncate">{preset.description}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0 ml-2 sm:ml-4">
                            <span className="text-xs sm:text-sm text-muted-foreground hidden sm:inline">{preset.rule_count} rules</span>
                            {isApplied ? (
                              <Button size="sm" variant="outline" disabled={isRemoving} onClick={e => { e.stopPropagation(); removePreset(preset.id) }} className="border-red-500/30 text-red-400 hover:bg-red-500/10">
                                {isRemoving ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Trash2 className="h-4 w-4 mr-1" />Remove</>}
                              </Button>
                            ) : (
                              <Button size="sm" disabled={isApplying} onClick={e => { e.stopPropagation(); applyPreset(preset.id) }}>
                                {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Sparkles className="h-4 w-4 mr-1" />Apply</>}
                              </Button>
                            )}
                          </div>
                        </div>
                        {isExpanded && (
                          <div className="border-t border-border bg-muted/30 p-3 sm:p-4">
                            {presetDetailLoading ? (
                              <div className="flex items-center justify-center py-4"><Loader2 className="h-5 w-5 animate-spin text-cyan-500" /></div>
                            ) : presetDetail ? (
                              <div className="space-y-3">
                                <p className="text-xs sm:text-sm text-muted-foreground">{presetDetail.description}</p>
                                <div className="text-xs text-muted-foreground flex items-center gap-4">
                                  <span>v{presetDetail.version}</span>
                                  <span>by {presetDetail.author}</span>
                                </div>
                                <div className="space-y-2">
                                  <h4 className="text-xs sm:text-sm font-medium">Rules that will be created:</h4>
                                  {(presetDetail.rules || presetDetail.thresholds || []).map((rule, idx) => (
                                    <div key={idx} className="flex items-start gap-2 pl-4 py-1.5 border-l-2 border-border">
                                      <Info className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                                      <div className="text-xs sm:text-sm">
                                        <span>{rule.name}</span>
                                        {rule.notes && <p className="text-muted-foreground text-xs mt-0.5">{rule.notes}</p>}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* DIALOGS */}
      {/* ═══════════════════════════════════════════════════════════════ */}

      {/* WAF Dialog */}
      {showWafDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-semibold">{editingWafRule ? 'Edit WAF Rule' : 'Add WAF Rule'}</h2>
            </div>
            <form onSubmit={handleSubmitWaf} className="p-4 sm:p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input type="text" value={wafForm.name} onChange={e => setWafForm({ ...wafForm, name: e.target.value })} className="w-full px-3 sm:px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary text-sm" placeholder="SQL Injection - UNION SELECT" required />
              </div>
              <div className="grid grid-cols-3 gap-3 sm:gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Category</label>
                  <select value={wafForm.category} onChange={e => setWafForm({ ...wafForm, category: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    {wafCategories.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Severity</label>
                  <select value={wafForm.severity} onChange={e => setWafForm({ ...wafForm, severity: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select value={wafForm.action} onChange={e => setWafForm({ ...wafForm, action: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    <option value="log">Log only</option>
                    <option value="block">Block</option>
                    <option value="blocklist">Blocklist IP</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Pattern (Regex)</label>
                <input type="text" value={wafForm.pattern} onChange={e => setWafForm({ ...wafForm, pattern: e.target.value })} className="w-full px-3 sm:px-4 py-2 rounded-lg border border-input bg-background font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="union(\s)+select" required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Apply to Host</label>
                <select value={wafForm.hostId} onChange={e => setWafForm({ ...wafForm, hostId: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                  <option value="">All Hosts (global)</option>
                  {hosts.map(h => <option key={h.id} value={h.id}>{h.domain_names[0]}</option>)}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="wafEnabled" checked={wafForm.enabled} onChange={e => setWafForm({ ...wafForm, enabled: e.target.checked })} className="h-4 w-4" />
                <label htmlFor="wafEnabled" className="text-sm">Enabled</label>
              </div>
              {error && <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">{error}</div>}
              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <Button type="button" variant="outline" onClick={() => setShowWafDialog(false)}>Cancel</Button>
                <Button type="submit" disabled={isSubmitting}>{isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1" />}{editingWafRule ? 'Save' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* GeoIP Dialog */}
      {showGeoDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-semibold">{editingGeoRule ? 'Edit GeoIP Rule' : 'Add GeoIP Rule'}</h2>
            </div>
            <form onSubmit={handleSubmitGeo} className="p-4 sm:p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input type="text" value={geoForm.name} onChange={e => setGeoForm({ ...geoForm, name: e.target.value })} className="w-full px-3 sm:px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary text-sm" placeholder="Block high-risk countries" required />
              </div>
              <div className="grid grid-cols-2 gap-3 sm:gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Mode</label>
                  <select value={geoForm.mode} onChange={e => setGeoForm({ ...geoForm, mode: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    <option value="blocklist">Blocklist</option>
                    <option value="allowlist">Allowlist</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select value={geoForm.action} onChange={e => setGeoForm({ ...geoForm, action: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    <option value="block">Block</option>
                    <option value="log">Log only</option>
                    <option value="challenge">Challenge</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Countries ({geoForm.countries.length})</label>
                <div className="rounded-lg border border-input">
                  <div className="p-2 border-b border-input">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <input type="text" value={countrySearch} onChange={e => setCountrySearch(e.target.value)} className="w-full pl-8 pr-3 py-1.5 rounded-md border border-input bg-background text-sm" placeholder="Search..." />
                    </div>
                    {geoForm.countries.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {geoForm.countries.map(code => (
                          <span key={code} className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary cursor-pointer hover:bg-primary/20" onClick={() => toggleCountry(code)}>
                            {code} ×
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="max-h-40 overflow-y-auto p-2 grid grid-cols-2 gap-1">
                    {COUNTRIES.filter(c => !countrySearch || c.code.toLowerCase().includes(countrySearch.toLowerCase()) || c.name.toLowerCase().includes(countrySearch.toLowerCase())).map(c => (
                      <label key={c.code} className={`flex items-center gap-2 rounded px-2 py-1.5 cursor-pointer text-xs sm:text-sm hover:bg-muted ${geoForm.countries.includes(c.code) ? 'bg-primary/10 text-primary' : ''}`}>
                        <input type="checkbox" checked={geoForm.countries.includes(c.code)} onChange={() => toggleCountry(c.code)} className="h-3.5 w-3.5" />
                        <span className="font-mono text-xs">{c.code}</span>
                        <span className="truncate">{c.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="geoEnabled" checked={geoForm.enabled} onChange={e => setGeoForm({ ...geoForm, enabled: e.target.checked })} className="h-4 w-4" />
                <label htmlFor="geoEnabled" className="text-sm">Enabled</label>
              </div>
              {error && <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">{error}</div>}
              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <Button type="button" variant="outline" onClick={() => setShowGeoDialog(false)}>Cancel</Button>
                <Button type="submit" disabled={isSubmitting}>{isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1" />}{editingGeoRule ? 'Save' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rate Limit Dialog */}
      {showRateLimitDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-semibold">{editingRateLimitRule ? 'Edit Rate Limit Rule' : 'Add Rate Limit Rule'}</h2>
            </div>
            <form onSubmit={handleSubmitRateLimit} className="p-4 sm:p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input type="text" value={rateLimitForm.name} onChange={e => setRateLimitForm({ ...rateLimitForm, name: e.target.value })} className="w-full px-3 sm:px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary text-sm" placeholder="API rate limit" required />
              </div>
              <div className="grid grid-cols-3 gap-3 sm:gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Per Second</label>
                  <input type="number" value={rateLimitForm.rps} onChange={e => setRateLimitForm({ ...rateLimitForm, rps: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm" placeholder="—" min="1" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Per Minute</label>
                  <input type="number" value={rateLimitForm.rpm} onChange={e => setRateLimitForm({ ...rateLimitForm, rpm: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm" placeholder="—" min="1" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Per Hour</label>
                  <input type="number" value={rateLimitForm.rph} onChange={e => setRateLimitForm({ ...rateLimitForm, rph: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm" placeholder="—" min="1" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Burst Size</label>
                  <input type="number" value={rateLimitForm.burst} onChange={e => setRateLimitForm({ ...rateLimitForm, burst: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm" min="1" required />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select value={rateLimitForm.action} onChange={e => setRateLimitForm({ ...rateLimitForm, action: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm">
                    <option value="reject">Reject (429)</option>
                    <option value="delay">Delay</option>
                    <option value="log">Log only</option>
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="rlEnabled" checked={rateLimitForm.enabled} onChange={e => setRateLimitForm({ ...rateLimitForm, enabled: e.target.checked })} className="h-4 w-4" />
                <label htmlFor="rlEnabled" className="text-sm">Enabled</label>
              </div>
              {error && <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">{error}</div>}
              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <Button type="button" variant="outline" onClick={() => setShowRateLimitDialog(false)}>Cancel</Button>
                <Button type="submit" disabled={isSubmitting}>{isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1" />}{editingRateLimitRule ? 'Save' : 'Create'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Click outside to close dropdowns */}
      {activeDropdown && <div className="fixed inset-0 z-0" onClick={() => setActiveDropdown(null)} />}
    </div>
  )
}
