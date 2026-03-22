'use client'

import { useState, useEffect } from 'react'
import {
  Globe,
  Plus,
  MoreHorizontal,
  Shield,
  ShieldOff,
  Pencil,
  Trash2,
  Power,
  PowerOff,
  Cloud,
  CloudOff,
  Loader2,
  ExternalLink,
  MapPin,
  Settings,
  Layers,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import type { ProxyHost, ProxyLocation, Certificate, AccessList, AuthWall } from '@/types'

type TabType = 'details' | 'locations' | 'advanced'

interface FormData {
  domain_names: string[]
  forward_scheme: 'http' | 'https'
  forward_host: string
  forward_port: number
  ssl_enabled: boolean
  certificate_id?: string
  access_list_id?: string
  auth_wall_id?: string
  http2_support: boolean
  hsts_enabled: boolean
  hsts_subdomains: boolean
  websockets_support: boolean
  block_exploits: boolean
  advanced_config?: string
  server_advanced_config?: string
  client_max_body_size: string
  proxy_buffering: boolean
  proxy_buffer_size: string
  proxy_buffers: string
  cache_enabled: boolean
  cache_valid?: string
  cache_bypass?: string
  rate_limit_enabled: boolean
  rate_limit_requests: number
  rate_limit_period: string
  rate_limit_burst: number
  custom_error_pages?: Record<string, string>
  traffic_logging_enabled: boolean
}

interface LocationFormData {
  path: string
  match_type: 'prefix' | 'exact' | 'regex' | 'regex_case_insensitive'
  priority: number
  forward_scheme: 'http' | 'https'
  forward_host: string
  forward_port: number
  websockets_support: boolean
  cache_enabled: boolean
  cache_valid?: string
  rate_limit_enabled: boolean
  rate_limit_requests: number
  rate_limit_period: string
  rate_limit_burst: number
  proxy_connect_timeout: number
  proxy_send_timeout: number
  proxy_read_timeout: number
  advanced_config?: string
}

const defaultFormData: FormData = {
  domain_names: [],
  forward_scheme: 'http',
  forward_host: '',
  forward_port: 80,
  ssl_enabled: false,
  http2_support: true,
  hsts_enabled: false,
  hsts_subdomains: false,
  websockets_support: true,
  block_exploits: true,
  client_max_body_size: '100m',
  proxy_buffering: true,
  proxy_buffer_size: '4k',
  proxy_buffers: '8 4k',
  cache_enabled: false,
  rate_limit_enabled: false,
  rate_limit_requests: 100,
  rate_limit_period: '1s',
  rate_limit_burst: 50,
  traffic_logging_enabled: false,
}

const defaultLocationData: LocationFormData = {
  path: '/',
  match_type: 'prefix',
  priority: 0,
  forward_scheme: 'http',
  forward_host: '',
  forward_port: 80,
  websockets_support: false,
  cache_enabled: false,
  rate_limit_enabled: false,
  rate_limit_requests: 100,
  rate_limit_period: '1s',
  rate_limit_burst: 50,
  proxy_connect_timeout: 60,
  proxy_send_timeout: 60,
  proxy_read_timeout: 60,
}

export default function ProxyHostsPage() {
  const confirm = useConfirm()
  const [hosts, setHosts] = useState<ProxyHost[]>([])
  const [certificates, setCertificates] = useState<Certificate[]>([])
  const [accessLists, setAccessLists] = useState<AccessList[]>([])
  const [authWalls, setAuthWalls] = useState<AuthWall[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editingHost, setEditingHost] = useState<ProxyHost | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabType>('details')

  // Form state
  const [formData, setFormData] = useState<FormData>(defaultFormData)
  const [domainInput, setDomainInput] = useState('')

  // Location state
  const [locations, setLocations] = useState<ProxyLocation[]>([])
  const [showLocationDialog, setShowLocationDialog] = useState(false)
  const [editingLocation, setEditingLocation] = useState<ProxyLocation | null>(null)
  const [locationForm, setLocationForm] = useState<LocationFormData>(defaultLocationData)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [hostsRes, certsRes, accessRes, authRes] = await Promise.all([
        api.get('/api/proxy-hosts'),
        api.get('/api/certificates'),
        api.get('/api/access-lists'),
        api.get('/api/auth-walls'),
      ])
      setHosts(hostsRes.data)
      setCertificates(certsRes.data)
      setAccessLists(accessRes.data)
      setAuthWalls(authRes.data)
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormData(defaultFormData)
    setDomainInput('')
    setError('')
    setActiveTab('details')
    setLocations([])
  }

  const handleCreate = () => {
    resetForm()
    setEditingHost(null)
    setShowDialog(true)
  }

  const handleEdit = (host: ProxyHost) => {
    setFormData({
      domain_names: host.domain_names,
      forward_scheme: host.forward_scheme,
      forward_host: host.forward_host,
      forward_port: host.forward_port,
      ssl_enabled: host.ssl_enabled,
      certificate_id: host.certificate_id || undefined,
      access_list_id: host.access_list_id || undefined,
      auth_wall_id: host.auth_wall_id || undefined,
      http2_support: host.http2_support,
      hsts_enabled: host.hsts_enabled,
      hsts_subdomains: host.hsts_subdomains,
      websockets_support: host.websockets_support,
      block_exploits: host.block_exploits,
      advanced_config: host.advanced_config || undefined,
      server_advanced_config: host.server_advanced_config || undefined,
      client_max_body_size: host.client_max_body_size,
      proxy_buffering: host.proxy_buffering,
      proxy_buffer_size: host.proxy_buffer_size,
      proxy_buffers: host.proxy_buffers,
      cache_enabled: host.cache_enabled,
      cache_valid: host.cache_valid || undefined,
      cache_bypass: host.cache_bypass || undefined,
      rate_limit_enabled: host.rate_limit_enabled,
      rate_limit_requests: host.rate_limit_requests,
      rate_limit_period: host.rate_limit_period,
      rate_limit_burst: host.rate_limit_burst,
      custom_error_pages: host.custom_error_pages || undefined,
      traffic_logging_enabled: host.traffic_logging_enabled,
    })
    setLocations(host.locations || [])
    setDomainInput('')
    setEditingHost(host)
    setShowDialog(true)
    setActiveTab('details')
    setActiveDropdown(null)
  }

  const handleAddDomain = () => {
    if (domainInput.trim() && !formData.domain_names.includes(domainInput.trim())) {
      setFormData({
        ...formData,
        domain_names: [...formData.domain_names, domainInput.trim()],
      })
      setDomainInput('')
    }
  }

  const handleRemoveDomain = (domain: string) => {
    setFormData({
      ...formData,
      domain_names: formData.domain_names.filter((d) => d !== domain),
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      if (formData.domain_names.length === 0) {
        setError('At least one domain is required')
        setIsSubmitting(false)
        return
      }

      if (editingHost) {
        await api.put(`/api/proxy-hosts/${editingHost.id}`, formData)
      } else {
        await api.post('/api/proxy-hosts', formData)
      }

      setShowDialog(false)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save proxy host')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleToggleEnabled = async (host: ProxyHost) => {
    try {
      if (host.enabled) {
        await api.post(`/api/proxy-hosts/${host.id}/disable`)
      } else {
        await api.post(`/api/proxy-hosts/${host.id}/enable`)
      }
      fetchData()
    } catch (error) {
      console.error('Failed to toggle host:', error)
    }
    setActiveDropdown(null)
  }

  const handleDelete = async (host: ProxyHost) => {
    if (!(await confirm({ description: `Are you sure you want to delete ${host.domain_names[0]}?`, variant: 'destructive' }))) return

    try {
      await api.delete(`/api/proxy-hosts/${host.id}`)
      fetchData()
    } catch (error) {
      console.error('Failed to delete host:', error)
    }
    setActiveDropdown(null)
  }

  // Location handlers
  const handleAddLocation = () => {
    setLocationForm(defaultLocationData)
    setEditingLocation(null)
    setShowLocationDialog(true)
  }

  const handleEditLocation = (location: ProxyLocation) => {
    setLocationForm({
      path: location.path,
      match_type: location.match_type,
      priority: location.priority,
      forward_scheme: location.forward_scheme,
      forward_host: location.forward_host,
      forward_port: location.forward_port,
      websockets_support: location.websockets_support,
      cache_enabled: location.cache_enabled,
      cache_valid: location.cache_valid || undefined,
      rate_limit_enabled: location.rate_limit_enabled,
      rate_limit_requests: location.rate_limit_requests,
      rate_limit_period: location.rate_limit_period,
      rate_limit_burst: location.rate_limit_burst,
      proxy_connect_timeout: location.proxy_connect_timeout,
      proxy_send_timeout: location.proxy_send_timeout,
      proxy_read_timeout: location.proxy_read_timeout,
      advanced_config: location.advanced_config || undefined,
    })
    setEditingLocation(location)
    setShowLocationDialog(true)
  }

  const handleSaveLocation = async () => {
    if (!editingHost) return

    try {
      if (editingLocation) {
        await api.put(
          `/api/proxy-hosts/${editingHost.id}/locations/${editingLocation.id}`,
          locationForm
        )
      } else {
        await api.post(`/api/proxy-hosts/${editingHost.id}/locations`, locationForm)
      }

      // Refresh locations
      const res = await api.get(`/api/proxy-hosts/${editingHost.id}/locations`)
      setLocations(res.data)
      setShowLocationDialog(false)
    } catch (err: any) {
      console.error('Failed to save location:', err)
    }
  }

  const handleDeleteLocation = async (location: ProxyLocation) => {
    if (!editingHost) return
    if (!(await confirm({ description: `Delete location ${location.path}?`, variant: 'destructive' }))) return

    try {
      await api.delete(`/api/proxy-hosts/${editingHost.id}/locations/${location.id}`)
      const res = await api.get(`/api/proxy-hosts/${editingHost.id}/locations`)
      setLocations(res.data)
    } catch (err) {
      console.error('Failed to delete location:', err)
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading proxy hosts...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Proxy Hosts</h1>
          <p className="text-muted-foreground">
            Manage your reverse proxy configurations
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add Proxy Host
        </button>
      </div>

      {/* Proxy Hosts Table */}
      <div className="rounded-xl border border-border bg-card overflow-visible">
        <div className="overflow-x-auto overflow-y-visible">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Source
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Destination
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  SSL
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Locations
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {hosts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-muted-foreground">
                    <Globe className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No proxy hosts configured</p>
                    <p className="text-sm mt-1">Click "Add Proxy Host" to create one</p>
                  </td>
                </tr>
              ) : (
                hosts.map((host) => (
                  <tr key={host.id} className="hover:bg-muted/50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="font-medium">{host.domain_names[0]}</p>
                          {host.domain_names.length > 1 && (
                            <p className="text-xs text-muted-foreground">
                              +{host.domain_names.length - 1} more
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">→</span>
                        <code className="text-sm">
                          {host.forward_scheme}://{host.forward_host}:{host.forward_port}
                        </code>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {host.ssl_enabled ? (
                        <div className="flex items-center gap-1 text-green-500">
                          <Shield className="h-4 w-4" />
                          <span className="text-xs">Secured</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <ShieldOff className="h-4 w-4" />
                          <span className="text-xs">None</span>
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <Layers className="h-4 w-4" />
                        <span className="text-xs">{(host.locations || []).length}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          host.enabled
                            ? 'bg-green-500/10 text-green-500'
                            : 'bg-gray-500/10 text-gray-500'
                        }`}
                      >
                        {host.enabled ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="relative">
                        <button
                          onClick={() =>
                            setActiveDropdown(activeDropdown === host.id ? null : host.id)
                          }
                          className="rounded-lg p-2 hover:bg-muted"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>

                        {activeDropdown === host.id && (
                          <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-lg border border-border bg-card shadow-lg">
                            <div className="p-1">
                              <button
                                onClick={() => handleEdit(host)}
                                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                              >
                                <Pencil className="h-4 w-4" />
                                Edit
                              </button>
                              <button
                                onClick={() => handleToggleEnabled(host)}
                                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                              >
                                {host.enabled ? (
                                  <>
                                    <PowerOff className="h-4 w-4" />
                                    Disable
                                  </>
                                ) : (
                                  <>
                                    <Power className="h-4 w-4" />
                                    Enable
                                  </>
                                )}
                              </button>
                              <a
                                href={`${host.ssl_enabled ? 'https' : 'http'}://${host.domain_names[0]}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                              >
                                <ExternalLink className="h-4 w-4" />
                                Open Site
                              </a>
                              <hr className="my-1 border-border" />
                              <button
                                onClick={() => handleDelete(host)}
                                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"
                              >
                                <Trash2 className="h-4 w-4" />
                                Delete
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create/Edit Dialog */}
      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-3xl max-h-[90vh] overflow-hidden rounded-xl bg-card border border-border shadow-xl flex flex-col">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingHost ? 'Edit Proxy Host' : 'Add Proxy Host'}
              </h2>
            </div>

            {/* Tabs */}
            <div className="border-b border-border px-6">
              <div className="flex gap-4">
                <button
                  onClick={() => setActiveTab('details')}
                  className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'details'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4" />
                    Details
                  </div>
                </button>
                {editingHost && (
                  <button
                    onClick={() => setActiveTab('locations')}
                    className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                      activeTab === 'locations'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4" />
                      Locations ({locations.length})
                    </div>
                  </button>
                )}
                <button
                  onClick={() => setActiveTab('advanced')}
                  className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === 'advanced'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Settings className="h-4 w-4" />
                    Advanced
                  </div>
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {activeTab === 'details' && (
                <form onSubmit={handleSubmit} className="p-6 space-y-6">
                  {/* Domain Names */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Domain Names</label>
                    <div className="flex gap-2 mb-2">
                      <input
                        type="text"
                        value={domainInput}
                        onChange={(e) => setDomainInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            handleAddDomain()
                          }
                        }}
                        className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="example.com"
                      />
                      <button
                        type="button"
                        onClick={handleAddDomain}
                        className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                      >
                        Add
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {formData.domain_names.map((domain) => (
                        <span
                          key={domain}
                          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
                        >
                          {domain}
                          <button
                            type="button"
                            onClick={() => handleRemoveDomain(domain)}
                            className="hover:text-primary/70"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Forward Settings */}
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">Scheme</label>
                      <select
                        value={formData.forward_scheme}
                        onChange={(e) =>
                          setFormData({ ...formData, forward_scheme: e.target.value as 'http' | 'https' })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                      >
                        <option value="http">http</option>
                        <option value="https">https</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Forward Host</label>
                      <input
                        type="text"
                        value={formData.forward_host}
                        onChange={(e) => setFormData({ ...formData, forward_host: e.target.value })}
                        className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                        placeholder="192.168.1.1"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Forward Port</label>
                      <input
                        type="number"
                        value={formData.forward_port}
                        onChange={(e) =>
                          setFormData({ ...formData, forward_port: parseInt(e.target.value) || 80 })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                        min={1}
                        max={65535}
                        required
                      />
                    </div>
                  </div>

                  {/* SSL Settings */}
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        id="ssl_enabled"
                        checked={formData.ssl_enabled}
                        onChange={(e) => setFormData({ ...formData, ssl_enabled: e.target.checked })}
                        className="h-4 w-4 rounded border-input"
                      />
                      <label htmlFor="ssl_enabled" className="text-sm font-medium">
                        Enable SSL
                      </label>
                    </div>

                    {formData.ssl_enabled && (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium mb-2">SSL Certificate</label>
                          <select
                            value={formData.certificate_id || ''}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                certificate_id: e.target.value || undefined,
                              })
                            }
                            className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                          >
                            <option value="">Select certificate...</option>
                            {certificates.map((cert) => (
                              <option key={cert.id} value={cert.id}>
                                {cert.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-2">
                          <label className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={formData.http2_support}
                              onChange={(e) =>
                                setFormData({ ...formData, http2_support: e.target.checked })
                              }
                              className="h-4 w-4 rounded border-input"
                            />
                            <span className="text-sm">HTTP/2 Support</span>
                          </label>
                          <label className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={formData.hsts_enabled}
                              onChange={(e) =>
                                setFormData({ ...formData, hsts_enabled: e.target.checked })
                              }
                              className="h-4 w-4 rounded border-input"
                            />
                            <span className="text-sm">Enable HSTS</span>
                          </label>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Access Control */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">Access List</label>
                      <select
                        value={formData.access_list_id || ''}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            access_list_id: e.target.value || undefined,
                          })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                      >
                        <option value="">None</option>
                        {accessLists.map((list) => (
                          <option key={list.id} value={list.id}>
                            {list.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">Auth Wall</label>
                      <select
                        value={formData.auth_wall_id || ''}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            auth_wall_id: e.target.value || undefined,
                          })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                      >
                        <option value="">None</option>
                        {authWalls.map((wall) => (
                          <option key={wall.id} value={wall.id}>
                            {wall.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Options */}
                  <div className="space-y-3">
                    <p className="text-sm font-medium">Options</p>
                    <div className="flex flex-wrap gap-6">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formData.websockets_support}
                          onChange={(e) =>
                            setFormData({ ...formData, websockets_support: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-input"
                        />
                        <span className="text-sm">WebSocket Support</span>
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formData.block_exploits}
                          onChange={(e) =>
                            setFormData({ ...formData, block_exploits: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-input"
                        />
                        <span className="text-sm">Block Common Exploits</span>
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formData.traffic_logging_enabled}
                          onChange={(e) =>
                            setFormData({ ...formData, traffic_logging_enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-input"
                        />
                        <span className="text-sm">Traffic Logging</span>
                      </label>
                    </div>
                  </div>

                  {error && (
                    <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                      {error}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-4 border-t border-border">
                    <button
                      type="button"
                      onClick={() => setShowDialog(false)}
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
                      {editingHost ? 'Save Changes' : 'Create'}
                    </button>
                  </div>
                </form>
              )}

              {activeTab === 'locations' && editingHost && (
                <div className="p-6 space-y-4">
                  <div className="flex justify-between items-center">
                    <p className="text-sm text-muted-foreground">
                      Custom locations allow different paths to be proxied to different backends.
                    </p>
                    <button
                      onClick={handleAddLocation}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90"
                    >
                      <Plus className="h-4 w-4" />
                      Add Location
                    </button>
                  </div>

                  {locations.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <MapPin className="mx-auto h-8 w-8 mb-2 opacity-50" />
                      <p>No custom locations configured</p>
                      <p className="text-sm">All requests use the default backend</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {locations.map((loc) => (
                        <div
                          key={loc.id}
                          className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/50"
                        >
                          <div className="flex items-center gap-4">
                            <code className="text-sm font-mono bg-background px-2 py-1 rounded">
                              {loc.match_type === 'exact' && '= '}
                              {loc.match_type === 'regex' && '~ '}
                              {loc.match_type === 'regex_case_insensitive' && '~* '}
                              {loc.path}
                            </code>
                            <span className="text-muted-foreground">→</span>
                            <span className="text-sm">
                              {loc.forward_scheme}://{loc.forward_host}:{loc.forward_port}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              priority: {loc.priority}
                            </span>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleEditLocation(loc)}
                              className="p-1.5 rounded hover:bg-muted"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteLocation(loc)}
                              className="p-1.5 rounded hover:bg-muted text-red-500"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="pt-4 border-t border-border">
                    <p className="text-sm text-muted-foreground">
                      <strong>Default location (/)</strong>: {formData.forward_scheme}://
                      {formData.forward_host}:{formData.forward_port}
                    </p>
                  </div>
                </div>
              )}

              {activeTab === 'advanced' && (
                <div className="p-6 space-y-6">
                  {/* Server Settings */}
                  <div>
                    <h3 className="text-sm font-medium mb-4">Server Settings</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm mb-1">Client Max Body Size</label>
                        <input
                          type="text"
                          value={formData.client_max_body_size}
                          onChange={(e) =>
                            setFormData({ ...formData, client_max_body_size: e.target.value })
                          }
                          className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                          placeholder="100m"
                        />
                      </div>
                      <div className="flex items-end">
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={formData.proxy_buffering}
                            onChange={(e) =>
                              setFormData({ ...formData, proxy_buffering: e.target.checked })
                            }
                            className="h-4 w-4 rounded border-input"
                          />
                          <span className="text-sm">Proxy Buffering</span>
                        </label>
                      </div>
                    </div>
                  </div>

                  {/* Caching */}
                  <div>
                    <h3 className="text-sm font-medium mb-4">Caching</h3>
                    <div className="space-y-4">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formData.cache_enabled}
                          onChange={(e) =>
                            setFormData({ ...formData, cache_enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-input"
                        />
                        <span className="text-sm">Enable Caching</span>
                      </label>
                      {formData.cache_enabled && (
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm mb-1">Cache Valid</label>
                            <input
                              type="text"
                              value={formData.cache_valid || ''}
                              onChange={(e) =>
                                setFormData({ ...formData, cache_valid: e.target.value || undefined })
                              }
                              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                              placeholder="200 302 10m"
                            />
                          </div>
                          <div>
                            <label className="block text-sm mb-1">Cache Bypass</label>
                            <input
                              type="text"
                              value={formData.cache_bypass || ''}
                              onChange={(e) =>
                                setFormData({ ...formData, cache_bypass: e.target.value || undefined })
                              }
                              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                              placeholder="$http_cache_control"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Rate Limiting */}
                  <div>
                    <h3 className="text-sm font-medium mb-4">Rate Limiting</h3>
                    <div className="space-y-4">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formData.rate_limit_enabled}
                          onChange={(e) =>
                            setFormData({ ...formData, rate_limit_enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded border-input"
                        />
                        <span className="text-sm">Enable Rate Limiting</span>
                      </label>
                      {formData.rate_limit_enabled && (
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <label className="block text-sm mb-1">Requests</label>
                            <input
                              type="number"
                              value={formData.rate_limit_requests}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  rate_limit_requests: parseInt(e.target.value) || 100,
                                })
                              }
                              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-sm mb-1">Period</label>
                            <select
                              value={formData.rate_limit_period}
                              onChange={(e) =>
                                setFormData({ ...formData, rate_limit_period: e.target.value })
                              }
                              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                            >
                              <option value="1s">Per Second</option>
                              <option value="1m">Per Minute</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-sm mb-1">Burst</label>
                            <input
                              type="number"
                              value={formData.rate_limit_burst}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  rate_limit_burst: parseInt(e.target.value) || 50,
                                })
                              }
                              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Advanced Config */}
                  <div>
                    <h3 className="text-sm font-medium mb-4">Custom Nginx Configuration</h3>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm mb-1">Server-Level Config</label>
                        <textarea
                          value={formData.server_advanced_config || ''}
                          onChange={(e) =>
                            setFormData({
                              ...formData,
                              server_advanced_config: e.target.value || undefined,
                            })
                          }
                          className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm font-mono"
                          rows={3}
                          placeholder="# Directives added at server block level"
                        />
                      </div>
                      <div>
                        <label className="block text-sm mb-1">Location-Level Config</label>
                        <textarea
                          value={formData.advanced_config || ''}
                          onChange={(e) =>
                            setFormData({
                              ...formData,
                              advanced_config: e.target.value || undefined,
                            })
                          }
                          className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm font-mono"
                          rows={3}
                          placeholder="# Directives added inside default location block"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-3 pt-4 border-t border-border">
                    <button
                      type="button"
                      onClick={() => setShowDialog(false)}
                      className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSubmit}
                      disabled={isSubmitting}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                      Save Changes
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Location Dialog */}
      {showLocationDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-4">
              <h3 className="text-lg font-semibold">
                {editingLocation ? 'Edit Location' : 'Add Location'}
              </h3>
            </div>

            <div className="p-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Path</label>
                  <input
                    type="text"
                    value={locationForm.path}
                    onChange={(e) => setLocationForm({ ...locationForm, path: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                    placeholder="/api"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Match Type</label>
                  <select
                    value={locationForm.match_type}
                    onChange={(e) =>
                      setLocationForm({
                        ...locationForm,
                        match_type: e.target.value as any,
                      })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                  >
                    <option value="prefix">Prefix</option>
                    <option value="exact">Exact</option>
                    <option value="regex">Regex</option>
                    <option value="regex_case_insensitive">Regex (case insensitive)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Priority</label>
                <input
                  type="number"
                  value={locationForm.priority}
                  onChange={(e) =>
                    setLocationForm({ ...locationForm, priority: parseInt(e.target.value) || 0 })
                  }
                  className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                />
                <p className="text-xs text-muted-foreground mt-1">Higher priority = processed first</p>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">Scheme</label>
                  <select
                    value={locationForm.forward_scheme}
                    onChange={(e) =>
                      setLocationForm({
                        ...locationForm,
                        forward_scheme: e.target.value as 'http' | 'https',
                      })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                  >
                    <option value="http">http</option>
                    <option value="https">https</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Host</label>
                  <input
                    type="text"
                    value={locationForm.forward_host}
                    onChange={(e) =>
                      setLocationForm({ ...locationForm, forward_host: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                    placeholder="backend"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Port</label>
                  <input
                    type="number"
                    value={locationForm.forward_port}
                    onChange={(e) =>
                      setLocationForm({
                        ...locationForm,
                        forward_port: parseInt(e.target.value) || 80,
                      })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
                  />
                </div>
              </div>

              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={locationForm.websockets_support}
                    onChange={(e) =>
                      setLocationForm({ ...locationForm, websockets_support: e.target.checked })
                    }
                    className="h-4 w-4 rounded border-input"
                  />
                  <span className="text-sm">WebSocket</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={locationForm.cache_enabled}
                    onChange={(e) =>
                      setLocationForm({ ...locationForm, cache_enabled: e.target.checked })
                    }
                    className="h-4 w-4 rounded border-input"
                  />
                  <span className="text-sm">Caching</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={locationForm.rate_limit_enabled}
                    onChange={(e) =>
                      setLocationForm({ ...locationForm, rate_limit_enabled: e.target.checked })
                    }
                    className="h-4 w-4 rounded border-input"
                  />
                  <span className="text-sm">Rate Limit</span>
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  onClick={() => setShowLocationDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted text-sm"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveLocation}
                  className="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-sm"
                >
                  {editingLocation ? 'Update' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Click outside to close dropdown */}
      {activeDropdown && (
        <div className="fixed inset-0 z-0" onClick={() => setActiveDropdown(null)} />
      )}
    </div>
  )
}
