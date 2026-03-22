'use client'

import { useState, useEffect } from 'react'
import {
  Map,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  Search,
  Globe,
} from 'lucide-react'
import api from '@/lib/api'

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

interface GeoipSettings {
  id: string
  provider: string
  database_path: string | null
  auto_update: boolean
  last_updated_at: string | null
  enabled: boolean
}

interface LookupResult {
  ip: string
  country_code: string | null
  country_name: string | null
  continent_code: string | null
}

const modeColors: Record<string, string> = {
  blocklist: 'bg-red-500/10 text-red-500',
  allowlist: 'bg-green-500/10 text-green-500',
}

const actionColors: Record<string, string> = {
  block: 'bg-red-500/10 text-red-500',
  log: 'bg-slate-500/10 text-slate-400',
  challenge: 'bg-yellow-500/10 text-yellow-500',
}

// Common country codes for the selector
const COUNTRIES = [
  { code: 'US', name: 'United States' }, { code: 'GB', name: 'United Kingdom' },
  { code: 'DE', name: 'Germany' }, { code: 'FR', name: 'France' },
  { code: 'CN', name: 'China' }, { code: 'RU', name: 'Russia' },
  { code: 'JP', name: 'Japan' }, { code: 'KR', name: 'South Korea' },
  { code: 'BR', name: 'Brazil' }, { code: 'IN', name: 'India' },
  { code: 'AU', name: 'Australia' }, { code: 'CA', name: 'Canada' },
  { code: 'NL', name: 'Netherlands' }, { code: 'IT', name: 'Italy' },
  { code: 'ES', name: 'Spain' }, { code: 'SE', name: 'Sweden' },
  { code: 'PL', name: 'Poland' }, { code: 'UA', name: 'Ukraine' },
  { code: 'RO', name: 'Romania' }, { code: 'TH', name: 'Thailand' },
  { code: 'VN', name: 'Vietnam' }, { code: 'ID', name: 'Indonesia' },
  { code: 'TR', name: 'Turkey' }, { code: 'IR', name: 'Iran' },
  { code: 'KP', name: 'North Korea' }, { code: 'NG', name: 'Nigeria' },
  { code: 'PK', name: 'Pakistan' }, { code: 'BD', name: 'Bangladesh' },
  { code: 'ZA', name: 'South Africa' }, { code: 'MX', name: 'Mexico' },
  { code: 'AR', name: 'Argentina' }, { code: 'EG', name: 'Egypt' },
  { code: 'SG', name: 'Singapore' }, { code: 'HK', name: 'Hong Kong' },
  { code: 'TW', name: 'Taiwan' }, { code: 'NZ', name: 'New Zealand' },
]

export default function GeoIPPage() {
  const [rules, setRules] = useState<GeoipRule[]>([])
  const [settings, setSettings] = useState<GeoipSettings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingRule, setEditingRule] = useState<GeoipRule | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'rules' | 'lookup'>('rules')

  // Form state
  const [formName, setFormName] = useState('')
  const [formMode, setFormMode] = useState('blocklist')
  const [formCountries, setFormCountries] = useState<string[]>([])
  const [formAction, setFormAction] = useState('block')
  const [formEnabled, setFormEnabled] = useState(true)

  // Lookup state
  const [lookupIp, setLookupIp] = useState('')
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [rulesRes, settingsRes] = await Promise.all([
        api.get('/api/geoip/rules'),
        api.get('/api/geoip/settings').catch(() => ({ data: null })),
      ])
      setRules(rulesRes.data)
      setSettings(settingsRes.data)
    } catch (error) {
      console.error('Failed to fetch GeoIP data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormMode('blocklist')
    setFormCountries([])
    setFormAction('block')
    setFormEnabled(true)
    setError('')
  }

  const handleCreate = () => {
    resetForm()
    setEditingRule(null)
    setShowCreateDialog(true)
  }

  const handleEdit = (rule: GeoipRule) => {
    setFormName(rule.name)
    setFormMode(rule.mode)
    try {
      setFormCountries(JSON.parse(rule.countries))
    } catch {
      setFormCountries([])
    }
    setFormAction(rule.action)
    setFormEnabled(rule.enabled)
    setEditingRule(rule)
    setShowCreateDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (formCountries.length === 0) {
      setError('Select at least one country')
      return
    }

    setIsSubmitting(true)

    try {
      const data = {
        name: formName,
        mode: formMode,
        countries: JSON.stringify(formCountries),
        action: formAction,
        enabled: formEnabled,
      }

      if (editingRule) {
        await api.put(`/api/geoip/rules/${editingRule.id}`, data)
      } else {
        await api.post('/api/geoip/rules', data)
      }

      setShowCreateDialog(false)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save GeoIP rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (rule: GeoipRule) => {
    if (!confirm(`Delete rule "${rule.name}"?`)) return
    try {
      await api.delete(`/api/geoip/rules/${rule.id}`)
      fetchData()
    } catch (error) {
      console.error('Failed to delete rule:', error)
    }
    setActiveDropdown(null)
  }

  const handleToggle = async (rule: GeoipRule) => {
    try {
      await api.put(`/api/geoip/rules/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
    } catch (error) {
      console.error('Failed to toggle rule:', error)
    }
  }

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lookupIp.trim()) return
    setLookupLoading(true)
    setLookupResult(null)
    try {
      const res = await api.get(`/api/geoip/lookup/${lookupIp.trim()}`)
      setLookupResult(res.data)
    } catch (err: any) {
      setLookupResult(null)
      setError(err.response?.data?.detail || 'Lookup failed')
    } finally {
      setLookupLoading(false)
    }
  }

  const toggleCountry = (code: string) => {
    setFormCountries((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    )
  }

  const parseCountries = (countries: string): string[] => {
    try {
      return JSON.parse(countries)
    } catch {
      return []
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading GeoIP settings...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">GeoIP Blocking</h1>
          <p className="text-muted-foreground">
            Block or allow traffic by country
          </p>
        </div>
        {activeTab === 'rules' && (
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Add Rule
          </button>
        )}
      </div>

      {/* GeoIP Status */}
      {settings && (
        <div className="rounded-xl border border-border bg-card p-4 flex items-center gap-4">
          <Globe className="h-5 w-5 text-muted-foreground" />
          <div className="text-sm">
            <span className="font-medium">Provider:</span>{' '}
            <span className="capitalize">{settings.provider}</span>
            {settings.enabled ? (
              <span className="ml-3 text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-500">Active</span>
            ) : (
              <span className="ml-3 text-xs px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-400">Disabled</span>
            )}
            {settings.last_updated_at && (
              <span className="ml-3 text-muted-foreground">
                DB updated: {new Date(settings.last_updated_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(['rules', 'lookup'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'bg-background shadow-sm'
                : 'hover:bg-background/50 text-muted-foreground'
            }`}
          >
            {tab === 'lookup' ? 'IP Lookup' : tab}
          </button>
        ))}
      </div>

      {activeTab === 'rules' ? (
        <div className="space-y-3">
          {rules.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <Map className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">No GeoIP rules configured</p>
              <p className="text-sm text-muted-foreground mt-1">
                Block or allow traffic from specific countries
              </p>
            </div>
          ) : (
            rules.map((rule) => {
              const countries = parseCountries(rule.countries)
              return (
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
                          <span className={`text-xs px-2 py-0.5 rounded-full ${modeColors[rule.mode] || 'bg-muted'}`}>
                            {rule.mode}
                          </span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${actionColors[rule.action] || actionColors.block}`}>
                            {rule.action}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {countries.slice(0, 8).map((code) => (
                            <span key={code} className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono">
                              {code}
                            </span>
                          ))}
                          {countries.length > 8 && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                              +{countries.length - 8} more
                            </span>
                          )}
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
              )
            })
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card p-6">
          <form onSubmit={handleLookup} className="flex gap-3 mb-6">
            <input
              type="text"
              value={lookupIp}
              onChange={(e) => setLookupIp(e.target.value)}
              className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary font-mono"
              placeholder="Enter IP address (e.g., 8.8.8.8)"
            />
            <button
              type="submit"
              disabled={lookupLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Lookup
            </button>
          </form>

          {lookupResult && (
            <div className="rounded-lg border border-border p-4 space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">IP Address:</span>
                  <p className="font-mono font-medium">{lookupResult.ip}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Country:</span>
                  <p className="font-medium">
                    {lookupResult.country_name || 'Unknown'}
                    {lookupResult.country_code && (
                      <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-muted font-mono">
                        {lookupResult.country_code}
                      </span>
                    )}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Continent:</span>
                  <p className="font-medium">{lookupResult.continent_code || 'Unknown'}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create/Edit Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingRule ? 'Edit GeoIP Rule' : 'Add GeoIP Rule'}
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
                  placeholder="Block high-risk countries"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Mode</label>
                  <select
                    value={formMode}
                    onChange={(e) => setFormMode(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="blocklist">Blocklist (deny listed)</option>
                    <option value="allowlist">Allowlist (only allow listed)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Action</label>
                  <select
                    value={formAction}
                    onChange={(e) => setFormAction(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="block">Block</option>
                    <option value="log">Log only</option>
                    <option value="challenge">Challenge</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Countries ({formCountries.length} selected)
                </label>
                <div className="max-h-48 overflow-y-auto rounded-lg border border-input p-2 grid grid-cols-2 gap-1">
                  {COUNTRIES.map((c) => (
                    <label
                      key={c.code}
                      className={`flex items-center gap-2 rounded px-2 py-1.5 cursor-pointer text-sm hover:bg-muted ${
                        formCountries.includes(c.code) ? 'bg-primary/10 text-primary' : ''
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={formCountries.includes(c.code)}
                        onChange={() => toggleCountry(c.code)}
                        className="h-3.5 w-3.5"
                      />
                      <span className="font-mono text-xs">{c.code}</span>
                      <span className="truncate">{c.name}</span>
                    </label>
                  ))}
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
