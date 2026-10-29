'use client'

import { useState } from 'react'
import { Modal, ModalBody } from '@/components/ui/modal'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Map,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  Search,
  Globe,
  Database,
  RefreshCw,
  CheckCircle,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import { IpAddress } from '@/components/ip-address'
import { COUNTRIES, COUNTRY_MAP } from '@/lib/countries'
import { PageHeader } from '@/components/page-header'
import { Earth as HeaderIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { StatCard } from '@/components/stat-card'
import { HostMultiPicker } from '@/components/host-multi-picker'
import { ContentSkeleton, LoadError } from '@/components/load-state'

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

interface ProxyHostBasic {
  id: string
  domain_names: string[]
}

interface LookupResult {
  ip: string
  country_code: string | null
  country_name: string | null
  continent_code: string | null
}

const modeColors: Record<string, string> = {
  blocklist: 'bg-red-500/10 text-red-600 dark:text-red-400',
  allowlist: 'bg-green-500/10 text-green-600 dark:text-green-400',
}

const actionColors: Record<string, string> = {
  block: 'bg-red-500/10 text-red-600 dark:text-red-400',
  log: 'bg-slate-500/10 text-muted-foreground',
  challenge: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400',
}



export default function GeoIPPage() {
  const [rules, setRules] = useState<GeoipRule[]>([])
  const [hosts, setHosts] = useState<ProxyHostBasic[]>([])
  const [settings, setSettings] = useState<GeoipSettings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingRule, setEditingRule] = useState<GeoipRule | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'rules' | 'lookup'>('rules')
  const [dbInfo, setDbInfo] = useState<{ installed: boolean; size_bytes: number; last_modified: string | null } | null>(null)
  const [isUpdatingDb, setIsUpdatingDb] = useState(false)

  // Form state
  const [formName, setFormName] = useState('')
  const [formMode, setFormMode] = useState('blocklist')
  const [formCountries, setFormCountries] = useState<string[]>([])
  const [formAction, setFormAction] = useState('block')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formHostIds, setFormHostIds] = useState<string[]>([])
  const [countrySearch, setCountrySearch] = useState('')

  // Lookup state
  const [lookupIp, setLookupIp] = useState('')
  const [lookupResult, setLookupResult] = useState<LookupResult | null>(null)
  const [lookupLoading, setLookupLoading] = useState(false)
  const confirm = useConfirm()

  const fetchData = async () => {
    try {
      setLoadError(false)
      const [rulesRes, settingsRes, dbRes] = await Promise.all([
        api.get('/api/geoip/rules'),
        api.get('/api/geoip/settings').catch(() => ({ data: null })),
        api.get('/api/geoip/database/status').catch(() => ({ data: null })),
      ])
      setRules(rulesRes.data)
      setSettings(settingsRes.data)
      if (dbRes.data) setDbInfo(dbRes.data)
    } catch (error) {
      console.error('Failed to fetch GeoIP data:', error)
      setLoadError(true)
    } finally {
      setIsLoading(false)
    }
  }

  usePageData(() => {
    fetchData()
    api.get('/api/proxy-hosts').then(res => setHosts(res.data)).catch(() => {})
  })

  const resetForm = () => {
    setFormName('')
    setFormMode('blocklist')
    setFormCountries([])
    setFormAction('block')
    setFormEnabled(true)
    setFormHostIds([])
    setCountrySearch('')
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
    setFormHostIds(rule.proxy_host_id ? [rule.proxy_host_id] : [])
    setEditingRule(rule)
    setShowCreateDialog(true)
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
      const baseData = {
        name: formName,
        mode: formMode,
        countries: JSON.stringify(formCountries),
        action: formAction,
        enabled: formEnabled,
      }

      if (editingRule) {
        await api.put(`/api/geoip/rules/${editingRule.id}`, { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else if (formHostIds.length <= 1) {
        await api.post('/api/geoip/rules', { ...baseData, proxy_host_id: formHostIds[0] || null })
      } else {
        const results = await Promise.allSettled(
          formHostIds.map(hostId => api.post('/api/geoip/rules', { ...baseData, proxy_host_id: hostId }))
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
      toastSuccess(editingRule ? 'GeoIP rule updated' : 'GeoIP rule created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save GeoIP rule')
      toastError('Failed to save GeoIP rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (rule: GeoipRule) => {
    if (!(await confirm({ description: `Delete rule "${rule.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/geoip/rules/${rule.id}`)
      fetchData()
      toastSuccess('GeoIP rule deleted')
    } catch (error) {
      console.error('Failed to delete rule:', error)
      toastError('Failed to delete rule')
    }
  }

  const handleToggle = async (rule: GeoipRule) => {
    try {
      await api.put(`/api/geoip/rules/${rule.id}`, { enabled: !rule.enabled })
      fetchData()
      toastSuccess(rule.enabled ? 'Rule disabled' : 'Rule enabled')
    } catch (error) {
      console.error('Failed to toggle rule:', error)
      toastError('Failed to toggle rule')
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

  return (
    <div className="space-y-6">
      <PageHeader
        icon={HeaderIcon}
        title="GeoIP Blocking"
        description="Block or allow traffic by country"
        actions={
          <>
            {activeTab === 'rules' && (
              <Button
                size="lg"
                onClick={handleCreate}
                disabled={isLoading}
              >
                <Plus className="h-4 w-4" />
                Add Rule
              </Button>
            )}
          </>
        }
      />

      {isLoading ? (
        <ContentSkeleton rows={4} />
      ) : (
      <>
      {/* GeoIP Database Status */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-muted-foreground" />
            <div>
              <h3 className="font-semibold">GeoIP Database</h3>
              <p className="text-sm text-muted-foreground">
                DB-IP Country Lite — free database updated monthly
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="lg"
            onClick={async () => {
              setIsUpdatingDb(true)
              try {
                await api.post('/api/geoip/database/update')
                const res = await api.get('/api/geoip/database/status')
                setDbInfo(res.data)
                toastSuccess('GeoIP database updated')
              } catch (err: any) {
                setError(err.response?.data?.detail || 'Failed to update GeoIP database')
                toastError('Failed to update GeoIP database')
              } finally {
                setIsUpdatingDb(false)
              }
            }}
            disabled={isUpdatingDb}
          >
            {isUpdatingDb ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {isUpdatingDb ? 'Updating...' : 'Update Now'}
          </Button>
        </div>
        {dbInfo && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard
              title="Status"
              value={dbInfo.installed ? 'Installed' : 'Not Installed'}
              icon={dbInfo.installed ? CheckCircle : Database}
              tone={dbInfo.installed ? 'success' : 'danger'}
            />
            <StatCard
              title="Size"
              value={dbInfo.size_bytes ? `${(dbInfo.size_bytes / 1024 / 1024).toFixed(1)} MB` : '-'}
            />
            <StatCard
              title="Last Updated"
              value={dbInfo.last_modified ? new Date(dbInfo.last_modified).toLocaleDateString() : '-'}
            />
          </div>
        )}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          {(['rules', 'lookup'] as const).map((tab) => (
            <TabsTrigger key={tab} value={tab} className="capitalize">
              {tab === 'lookup' ? 'IP Lookup' : tab}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {activeTab === 'rules' ? (
        <div className="space-y-3">
          {loadError ? (
            <LoadError what="GeoIP rules" onRetry={fetchData} />
          ) : rules.length === 0 ? (
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
                      <Switch checked={rule.enabled} onCheckedChange={() => handleToggle(rule)} aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold">{rule.name}</h3>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${modeColors[rule.mode] || 'bg-muted'}`}>
                            {rule.mode}
                          </span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${actionColors[rule.action] || actionColors.block}`}>
                            {rule.action}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400">
                            {rule.proxy_host_id ? hosts.find(h => h.id === rule.proxy_host_id)?.domain_names[0] || 'Specific host' : 'All hosts'}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {countries.slice(0, 8).map((code) => (
                            <span key={code} className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono" title={COUNTRY_MAP.get(code) || code}>
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
              )
            })
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card p-6">
          <form onSubmit={handleLookup} className="flex flex-wrap gap-3 mb-6">
            <input
              type="text"
              value={lookupIp}
              onChange={(e) => setLookupIp(e.target.value)}
              className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary font-mono"
              placeholder="Enter IP address (e.g., 8.8.8.8)"
            />
            <Button
              size="lg"
              type="submit"
              disabled={lookupLoading}
            >
              {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Lookup
            </Button>
          </form>

          {lookupResult && (
            <div className="rounded-lg border border-border p-4 space-y-2">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">IP Address:</span>
                  <div className="mt-0.5"><IpAddress ip={lookupResult.ip} countryCode={lookupResult.country_code} countryName={lookupResult.country_name} /></div>
                </div>
                <div>
                  <span className="text-muted-foreground">Country:</span>
                  <p className="font-medium">{lookupResult.country_name || 'Unknown'}</p>
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
      </>
      )}

      {/* Create/Edit Dialog */}
      <Modal
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        size="lg"
        srTitle="Geoip — Create"
      >
        <ModalBody className="p-0">
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
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                <div className="rounded-lg border border-input">
                  <div className="p-2 border-b border-input">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <input
                        type="text"
                        value={countrySearch}
                        onChange={(e) => setCountrySearch(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
                        placeholder="Search countries..."
                      />
                    </div>
                    {formCountries.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {formCountries.map((code) => (
                          <span
                            key={code}
                            className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary cursor-pointer hover:bg-primary/20"
                            onClick={() => toggleCountry(code)}
                          >
                            {code} {COUNTRY_MAP.get(code) || code}
                            <span className="text-primary/60">×</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="max-h-48 overflow-y-auto p-2 grid grid-cols-2 gap-1">
                    {COUNTRIES
                      .filter((c) => {
                        if (!countrySearch) return true
                        const q = countrySearch.toLowerCase()
                        return c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
                      })
                      .map((c) => (
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
