'use client'

import { useState, useEffect } from 'react'
import {
  Cloud,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  RefreshCw,
  Globe,
  CheckCircle,
  AlertTriangle,
  Link2,
  ExternalLink,
  Settings,
} from 'lucide-react'
import api from '@/lib/api'

interface DnsProvider {
  id: string
  name: string
  provider_type: 'cloudflare' | 'godaddy' | 'route53'
  enabled: boolean
  zones: DnsZone[]
}

interface DnsZone {
  id: string
  zone_id: string
  domain: string
  status: string
  records_count: number
}

interface DnsRecord {
  id: string
  type: 'A' | 'AAAA' | 'CNAME' | 'TXT' | 'MX' | 'NS'
  name: string
  content: string
  ttl: number
  proxied: boolean
  linked_proxy_host_id: string | null
}

export default function DnsPage() {
  const [providers, setProviders] = useState<DnsProvider[]>([])
  const [selectedProvider, setSelectedProvider] = useState<DnsProvider | null>(null)
  const [selectedZone, setSelectedZone] = useState<DnsZone | null>(null)
  const [records, setRecords] = useState<DnsRecord[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingRecords, setIsLoadingRecords] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)

  // Dialogs
  const [showProviderDialog, setShowProviderDialog] = useState(false)
  const [showRecordDialog, setShowRecordDialog] = useState(false)
  const [editingRecord, setEditingRecord] = useState<DnsRecord | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Provider form
  const [providerName, setProviderName] = useState('')
  const [providerType, setProviderType] = useState<'cloudflare' | 'godaddy'>('cloudflare')
  const [apiKey, setApiKey] = useState('')
  const [apiEmail, setApiEmail] = useState('')

  // Record form
  const [recordType, setRecordType] = useState<'A' | 'AAAA' | 'CNAME' | 'TXT' | 'MX'>('A')
  const [recordName, setRecordName] = useState('')
  const [recordContent, setRecordContent] = useState('')
  const [recordTtl, setRecordTtl] = useState(3600)
  const [recordProxied, setRecordProxied] = useState(true)

  useEffect(() => {
    fetchProviders()
  }, [])

  const fetchProviders = async () => {
    try {
      const response = await api.get('/api/dns/providers')
      setProviders(response.data)
      if (response.data.length > 0 && !selectedProvider) {
        setSelectedProvider(response.data[0])
        if (response.data[0].zones.length > 0) {
          setSelectedZone(response.data[0].zones[0])
          fetchRecords(response.data[0].zones[0].zone_id)
        }
      }
    } catch (error) {
      console.error('Failed to fetch providers:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchRecords = async (zoneId: string) => {
    setIsLoadingRecords(true)
    try {
      const response = await api.get(`/api/dns/zones/${zoneId}/records`)
      setRecords(response.data)
    } catch (error) {
      console.error('Failed to fetch records:', error)
    } finally {
      setIsLoadingRecords(false)
    }
  }

  const handleSelectZone = (zone: DnsZone) => {
    setSelectedZone(zone)
    fetchRecords(zone.zone_id)
  }

  const handleSyncZones = async () => {
    if (!selectedProvider) return
    setIsSyncing(true)
    try {
      await api.post(`/api/dns/providers/${selectedProvider.id}/sync`)
      fetchProviders()
    } catch (error) {
      console.error('Failed to sync zones:', error)
    } finally {
      setIsSyncing(false)
    }
  }

  const resetProviderForm = () => {
    setProviderName('')
    setProviderType('cloudflare')
    setApiKey('')
    setApiEmail('')
    setError('')
  }

  const resetRecordForm = () => {
    setRecordType('A')
    setRecordName('')
    setRecordContent('')
    setRecordTtl(3600)
    setRecordProxied(true)
    setError('')
  }

  const handleSubmitProvider = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      await api.post('/api/dns/providers', {
        name: providerName,
        provider_type: providerType,
        api_key: apiKey,
        api_email: apiEmail,
      })

      setShowProviderDialog(false)
      fetchProviders()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add provider')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCreateRecord = () => {
    resetRecordForm()
    setEditingRecord(null)
    setShowRecordDialog(true)
  }

  const handleEditRecord = (record: DnsRecord) => {
    setRecordType(record.type as any)
    setRecordName(record.name.replace(`.${selectedZone?.domain}`, ''))
    setRecordContent(record.content)
    setRecordTtl(record.ttl)
    setRecordProxied(record.proxied)
    setEditingRecord(record)
    setShowRecordDialog(true)
  }

  const handleSubmitRecord = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedZone) return
    setError('')
    setIsSubmitting(true)

    try {
      const data = {
        type: recordType,
        name: recordName,
        content: recordContent,
        ttl: recordTtl,
        proxied: recordProxied,
      }

      if (editingRecord) {
        await api.put(`/api/dns/zones/${selectedZone.zone_id}/records/${editingRecord.id}`, data)
      } else {
        await api.post(`/api/dns/zones/${selectedZone.zone_id}/records`, data)
      }

      setShowRecordDialog(false)
      fetchRecords(selectedZone.zone_id)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save record')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteRecord = async (record: DnsRecord) => {
    if (!selectedZone) return
    if (!confirm(`Are you sure you want to delete this ${record.type} record?`)) {
      return
    }

    try {
      await api.delete(`/api/dns/zones/${selectedZone.zone_id}/records/${record.id}`)
      fetchRecords(selectedZone.zone_id)
    } catch (error) {
      console.error('Failed to delete record:', error)
    }
  }

  const getRecordTypeColor = (type: string) => {
    switch (type) {
      case 'A':
        return 'bg-blue-500/10 text-blue-500'
      case 'AAAA':
        return 'bg-purple-500/10 text-purple-500'
      case 'CNAME':
        return 'bg-green-500/10 text-green-500'
      case 'TXT':
        return 'bg-yellow-500/10 text-yellow-500'
      case 'MX':
        return 'bg-orange-500/10 text-orange-500'
      default:
        return 'bg-gray-500/10 text-gray-500'
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading DNS providers...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">DNS Management</h1>
          <p className="text-muted-foreground">
            Manage DNS records with Cloudflare integration
          </p>
        </div>
        <button
          onClick={() => {
            resetProviderForm()
            setShowProviderDialog(true)
          }}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add DNS Provider
        </button>
      </div>

      {providers.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Cloud className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
          <p className="text-muted-foreground">No DNS providers configured</p>
          <p className="text-sm text-muted-foreground mt-1">
            Add a Cloudflare account to manage your DNS records
          </p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Zones Sidebar */}
          <div className="lg:col-span-1 space-y-4">
            {/* Provider Selector */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold">Provider</h3>
                <button
                  onClick={handleSyncZones}
                  disabled={isSyncing}
                  className="p-1 rounded hover:bg-muted"
                  title="Sync zones"
                >
                  <RefreshCw className={`h-4 w-4 ${isSyncing ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <select
                value={selectedProvider?.id || ''}
                onChange={(e) => {
                  const provider = providers.find((p) => p.id === e.target.value)
                  setSelectedProvider(provider || null)
                  if (provider?.zones.length) {
                    setSelectedZone(provider.zones[0])
                    fetchRecords(provider.zones[0].zone_id)
                  } else {
                    setSelectedZone(null)
                    setRecords([])
                  }
                }}
                className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
              >
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Zones List */}
            <div className="rounded-xl border border-border bg-card">
              <div className="border-b border-border p-4">
                <h3 className="font-semibold">Zones</h3>
              </div>
              <div className="p-2">
                {selectedProvider?.zones.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    No zones found. Click sync to fetch zones.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {selectedProvider?.zones.map((zone) => (
                      <button
                        key={zone.id}
                        onClick={() => handleSelectZone(zone)}
                        className={`w-full flex items-center justify-between rounded-lg px-3 py-2 text-sm text-left ${
                          selectedZone?.id === zone.id
                            ? 'bg-primary/10 text-primary'
                            : 'hover:bg-muted'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Globe className="h-4 w-4" />
                          <span>{zone.domain}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {zone.records_count} records
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Records */}
          <div className="lg:col-span-3">
            {selectedZone ? (
              <div className="rounded-xl border border-border bg-card">
                <div className="border-b border-border p-4 flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold">{selectedZone.domain}</h3>
                    <p className="text-sm text-muted-foreground">
                      {records.length} DNS records
                    </p>
                  </div>
                  <button
                    onClick={handleCreateRecord}
                    className="flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    <Plus className="h-4 w-4" />
                    Add Record
                  </button>
                </div>

                {isLoadingRecords ? (
                  <div className="p-8 text-center text-muted-foreground">
                    Loading records...
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Type
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Name
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Content
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Proxy
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Linked
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {records.map((record) => (
                          <tr key={record.id} className="hover:bg-muted/50">
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${getRecordTypeColor(
                                  record.type
                                )}`}
                              >
                                {record.type}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm font-mono">
                              {record.name}
                            </td>
                            <td className="px-4 py-3 text-sm font-mono max-w-xs truncate">
                              {record.content}
                            </td>
                            <td className="px-4 py-3">
                              <span title={record.proxied ? "Proxied" : "DNS Only"}>
                                <Cloud className={`h-4 w-4 ${record.proxied ? 'text-orange-500' : 'text-gray-400'}`} />
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {record.linked_proxy_host_id ? (
                                <span title="Linked to proxy host">
                                  <CheckCircle className="h-4 w-4 text-green-500" />
                                </span>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <button
                                  onClick={() => handleEditRecord(record)}
                                  className="p-1 rounded hover:bg-muted"
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={() => handleDeleteRecord(record)}
                                  className="p-1 rounded hover:bg-muted text-red-500"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-card p-12 text-center">
                <Globe className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground">Select a zone to view DNS records</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Provider Dialog */}
      {showProviderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Add DNS Provider</h2>
            </div>

            <form onSubmit={handleSubmitProvider} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input
                  type="text"
                  value={providerName}
                  onChange={(e) => setProviderName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="My Cloudflare Account"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Provider</label>
                <select
                  value={providerType}
                  onChange={(e) => setProviderType(e.target.value as any)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="cloudflare">Cloudflare</option>
                  <option value="godaddy" disabled>GoDaddy (coming soon)</option>
                </select>
              </div>

              {providerType === 'cloudflare' && (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-2">API Token</label>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder="Your Cloudflare API Token"
                      required
                    />
                  </div>
                  <div className="rounded-lg bg-muted/50 p-3 text-sm">
                    <p className="font-medium mb-2">Required API Token Permissions:</p>
                    <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                      <li><strong>Zone:Zone:Read</strong> - to list your domains</li>
                      <li><strong>Zone:DNS:Read</strong> - to view DNS records</li>
                      <li><strong>Zone:DNS:Edit</strong> - to create/modify DNS records</li>
                    </ul>
                    <p className="mt-2 text-xs">
                      Create a token at: Cloudflare Dashboard → My Profile → API Tokens → Create Token
                    </p>
                  </div>
                </>
              )}

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowProviderDialog(false)}
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
                  Add Provider
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add/Edit Record Dialog */}
      {showRecordDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingRecord ? 'Edit DNS Record' : 'Add DNS Record'}
              </h2>
            </div>

            <form onSubmit={handleSubmitRecord} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Type</label>
                <select
                  value={recordType}
                  onChange={(e) => setRecordType(e.target.value as any)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="A">A</option>
                  <option value="AAAA">AAAA</option>
                  <option value="CNAME">CNAME</option>
                  <option value="TXT">TXT</option>
                  <option value="MX">MX</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={recordName}
                    onChange={(e) => setRecordName(e.target.value)}
                    className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="subdomain"
                    required
                  />
                  <span className="text-muted-foreground">.{selectedZone?.domain}</span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Use @ for the root domain
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  {recordType === 'A' || recordType === 'AAAA'
                    ? 'IP Address'
                    : recordType === 'CNAME'
                    ? 'Target'
                    : 'Content'}
                </label>
                <input
                  type="text"
                  value={recordContent}
                  onChange={(e) => setRecordContent(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder={
                    recordType === 'A'
                      ? '192.168.1.1'
                      : recordType === 'CNAME'
                      ? 'target.example.com'
                      : 'Record content'
                  }
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">TTL (seconds)</label>
                <select
                  value={recordTtl}
                  onChange={(e) => setRecordTtl(parseInt(e.target.value))}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value={1}>Auto</option>
                  <option value={60}>1 minute</option>
                  <option value={300}>5 minutes</option>
                  <option value={3600}>1 hour</option>
                  <option value={86400}>1 day</option>
                </select>
              </div>

              {(recordType === 'A' || recordType === 'AAAA' || recordType === 'CNAME') && (
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Proxy through Cloudflare</p>
                    <p className="text-sm text-muted-foreground">
                      Enable Cloudflare's CDN and protection
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={recordProxied}
                      onChange={(e) => setRecordProxied(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-orange-500 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
                  </label>
                </div>
              )}

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowRecordDialog(false)}
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
                  {editingRecord ? 'Save Changes' : 'Add Record'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
