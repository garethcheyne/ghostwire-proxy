'use client'

import { useState, useEffect } from 'react'
import {
  Flame,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  ToggleLeft,
  ToggleRight,
  RefreshCw,
  Zap,
  CheckCircle,
  XCircle,
  ShieldBan,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'

interface FirewallConnector {
  id: string
  name: string
  connector_type: string
  host: string
  port: number | null
  username: string | null
  site_id: string | null
  address_list_name: string | null
  enabled: boolean
  last_sync_at: string | null
  created_at: string
}

interface BlocklistEntry {
  id: string
  threat_actor_id: string | null
  ip_address: string
  connector_id: string | null
  pushed_at: string | null
  expires_at: string | null
  status: string
  error_message: string | null
}

const typeLabels: Record<string, string> = {
  routeros: 'MikroTik RouterOS',
  unifi: 'Ubiquiti UniFi',
  pfsense: 'pfSense',
  opnsense: 'OPNsense',
}

const typeColors: Record<string, string> = {
  routeros: 'bg-blue-500/10 text-blue-500',
  unifi: 'bg-cyan-500/10 text-cyan-500',
  pfsense: 'bg-orange-500/10 text-orange-500',
  opnsense: 'bg-purple-500/10 text-purple-500',
}

export default function FirewallsPage() {
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<'connectors' | 'blocklist'>('connectors')
  const [connectors, setConnectors] = useState<FirewallConnector[]>([])
  const [blocklist, setBlocklist] = useState<BlocklistEntry[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingConnector, setEditingConnector] = useState<FirewallConnector | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({})
  const [blockTestResults, setBlockTestResults] = useState<Record<string, { success: boolean; message: string }>>({})
  const [syncingId, setSyncingId] = useState<string | null>(null)

  // Form state
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('routeros')
  const [formHost, setFormHost] = useState('')
  const [formPort, setFormPort] = useState('')
  const [formUsername, setFormUsername] = useState('')
  const [formPassword, setFormPassword] = useState('')
  const [formApiKey, setFormApiKey] = useState('')
  const [formSiteId, setFormSiteId] = useState('')
  const [formAddressList, setFormAddressList] = useState('ghostwire-blocked')
  const [formEnabled, setFormEnabled] = useState(true)

  useEffect(() => {
    fetchData()
  }, [activeTab])

  const fetchData = async () => {
    setIsLoading(true)
    try {
      if (activeTab === 'connectors') {
        const res = await api.get('/api/firewalls')
        setConnectors(res.data)
      } else {
        const res = await api.get('/api/firewalls/blocklist/all')
        setBlocklist(res.data)
      }
    } catch (error) {
      console.error('Failed to fetch firewall data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormType('routeros')
    setFormHost('')
    setFormPort('')
    setFormUsername('')
    setFormPassword('')
    setFormApiKey('')
    setFormSiteId('')
    setFormAddressList('ghostwire-blocked')
    setFormEnabled(true)
    setError('')
  }

  const handleCreate = () => {
    resetForm()
    setEditingConnector(null)
    setShowCreateDialog(true)
  }

  const handleEdit = (connector: FirewallConnector) => {
    setFormName(connector.name)
    setFormType(connector.connector_type)
    setFormHost(connector.host)
    setFormPort(connector.port?.toString() || '')
    setFormUsername(connector.username || '')
    setFormPassword('')
    setFormApiKey('')
    setFormSiteId(connector.site_id || '')
    setFormAddressList(connector.address_list_name || 'ghostwire-blocked')
    setFormEnabled(connector.enabled)
    setEditingConnector(connector)
    setShowCreateDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const data: Record<string, unknown> = {
        name: formName,
        connector_type: formType,
        host: formHost,
        port: formPort ? parseInt(formPort) : null,
        username: formUsername || null,
        site_id: formSiteId || null,
        address_list_name: formAddressList || null,
        enabled: formEnabled,
      }
      if (formPassword) data.password = formPassword
      if (formApiKey) data.api_key = formApiKey

      if (editingConnector) {
        await api.put(`/api/firewalls/${editingConnector.id}`, data)
      } else {
        await api.post('/api/firewalls', data)
      }

      setShowCreateDialog(false)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save connector')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (connector: FirewallConnector) => {
    if (!(await confirm({ description: `Delete connector "${connector.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/firewalls/${connector.id}`)
      fetchData()
    } catch (error) {
      console.error('Failed to delete connector:', error)
    }
    setActiveDropdown(null)
  }

  const handleTest = async (connector: FirewallConnector) => {
    try {
      const res = await api.post(`/api/firewalls/${connector.id}/test`)
      setTestResults({ ...testResults, [connector.id]: res.data })
    } catch (err: any) {
      setTestResults({
        ...testResults,
        [connector.id]: { success: false, message: err.response?.data?.detail || 'Connection failed' },
      })
    }
  }

  const handleTestBlock = async (connector: FirewallConnector) => {
    setBlockTestResults({ ...blockTestResults, [connector.id]: { success: false, message: 'Testing...' } })
    try {
      const res = await api.post(`/api/firewalls/${connector.id}/test-block`)
      setBlockTestResults({ ...blockTestResults, [connector.id]: res.data })
    } catch (err: any) {
      setBlockTestResults({
        ...blockTestResults,
        [connector.id]: { success: false, message: err.response?.data?.detail || 'Block test failed' },
      })
    }
  }

  const handleSync = async (connector: FirewallConnector) => {
    setSyncingId(connector.id)
    try {
      await api.post(`/api/firewalls/${connector.id}/sync`)
      fetchData()
    } catch (error) {
      console.error('Failed to sync:', error)
    } finally {
      setSyncingId(null)
    }
  }

  const formatDate = (d: string | null) => {
    if (!d) return 'Never'
    try { return new Date(d).toLocaleString() } catch { return d }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Firewall Integration</h1>
          <p className="text-muted-foreground">
            Push blocked IPs to your network firewalls
          </p>
        </div>
        {activeTab === 'connectors' && (
          <button
            onClick={handleCreate}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Add Connector
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(['connectors', 'blocklist'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'bg-background shadow-sm'
                : 'hover:bg-background/50 text-muted-foreground'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex h-96 items-center justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      ) : activeTab === 'connectors' ? (
        <div className="space-y-3">
          {connectors.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <Flame className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">No firewall connectors configured</p>
              <p className="text-sm text-muted-foreground mt-1">
                Add your RouterOS, UniFi, pfSense, or OPNsense firewall
              </p>
            </div>
          ) : (
            connectors.map((connector) => (
              <div key={connector.id} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className={`shrink-0 h-3 w-3 rounded-full ${connector.enabled ? 'bg-green-500' : 'bg-slate-500'}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold">{connector.name}</h3>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${typeColors[connector.connector_type] || 'bg-muted'}`}>
                          {typeLabels[connector.connector_type] || connector.connector_type}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5">
                        {connector.host}{connector.port ? `:${connector.port}` : ''}
                        {connector.address_list_name && ` • List: ${connector.address_list_name}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Last sync: {formatDate(connector.last_sync_at)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {/* Connection test result */}
                    {testResults[connector.id] && (
                      <span className={`text-xs flex items-center gap-1 ${testResults[connector.id].success ? 'text-green-500' : 'text-red-500'}`}>
                        {testResults[connector.id].success ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                        {testResults[connector.id].success ? 'Connected' : 'Failed'}
                      </span>
                    )}
                    {/* Block test result */}
                    {blockTestResults[connector.id] && (
                      <span className={`text-xs flex items-center gap-1 ${blockTestResults[connector.id].success ? 'text-green-500' : 'text-red-500'}`}>
                        {blockTestResults[connector.id].success ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                        {blockTestResults[connector.id].success ? 'Block OK' : blockTestResults[connector.id].message}
                      </span>
                    )}
                    <button
                      onClick={() => handleTest(connector)}
                      title="Test Connection"
                      className="rounded-lg px-3 py-1.5 text-xs border border-input hover:bg-muted"
                    >
                      <Zap className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleTestBlock(connector)}
                      title="Test Block (adds and removes test IP)"
                      className="rounded-lg px-3 py-1.5 text-xs border border-input hover:bg-muted"
                    >
                      <ShieldBan className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleSync(connector)}
                      disabled={syncingId === connector.id}
                      title="Sync Blocklist"
                      className="rounded-lg px-3 py-1.5 text-xs border border-input hover:bg-muted disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${syncingId === connector.id ? 'animate-spin' : ''}`} />
                    </button>

                    <div className="relative" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setActiveDropdown(activeDropdown === connector.id ? null : connector.id)}
                        className="rounded-lg p-2 hover:bg-muted"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {activeDropdown === connector.id && (
                        <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-lg border border-border bg-card shadow-lg">
                          <div className="p-1">
                            <button
                              onClick={() => handleEdit(connector)}
                              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                            >
                              <Pencil className="h-4 w-4" />
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(connector)}
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
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {blocklist.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <Flame className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">No IPs in the firewall blocklist</p>
            </div>
          ) : (
            blocklist.map((entry) => (
              <div key={entry.id} className="rounded-xl border border-border bg-card p-4 flex items-center justify-between">
                <div>
                  <code className="text-sm font-mono font-semibold">{entry.ip_address}</code>
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                    entry.status === 'pushed' ? 'bg-green-500/10 text-green-500' :
                    entry.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500' :
                    'bg-slate-500/10 text-slate-400'
                  }`}>
                    {entry.status}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {entry.pushed_at ? `Pushed: ${formatDate(entry.pushed_at)}` : 'Pending'}
                  {entry.error_message && <span className="text-red-500 ml-2">{entry.error_message}</span>}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Create/Edit Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingConnector ? 'Edit Connector' : 'Add Firewall Connector'}
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
                  placeholder="Main Router"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Type</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="routeros">MikroTik RouterOS</option>
                  <option value="unifi">Ubiquiti UniFi</option>
                  <option value="pfsense">pfSense</option>
                  <option value="opnsense">OPNsense</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Host</label>
                  <input
                    type="text"
                    value={formHost}
                    onChange={(e) => setFormHost(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder="192.168.1.1"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Port</label>
                  <input
                    type="number"
                    value={formPort}
                    onChange={(e) => setFormPort(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder={
                      formType === 'routeros' ? '8728' :
                      formType === 'unifi' ? '443' :
                      formType === 'pfsense' ? '443' :
                      formType === 'opnsense' ? '443' : '443'
                    }
                  />
                </div>
              </div>

              {/* RouterOS uses username/password */}
              {formType === 'routeros' && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Username</label>
                    <input
                      type="text"
                      value={formUsername}
                      onChange={(e) => setFormUsername(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder="admin"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Password</label>
                    <input
                      type="password"
                      value={formPassword}
                      onChange={(e) => setFormPassword(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder={editingConnector ? '(unchanged)' : ''}
                    />
                  </div>
                </div>
              )}

              {/* UniFi uses API Key */}
              {formType === 'unifi' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">API Key</label>
                    <input
                      type="password"
                      value={formApiKey}
                      onChange={(e) => setFormApiKey(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder={editingConnector ? '(unchanged)' : ''}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Create at Settings → Admins & Users → API Keys
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Site ID (optional)</label>
                    <input
                      type="text"
                      value={formSiteId}
                      onChange={(e) => setFormSiteId(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder="Leave empty to use default site"
                    />
                  </div>
                </div>
              )}

              {/* pfSense uses API Key */}
              {formType === 'pfsense' && (
                <div>
                  <label className="block text-sm font-medium mb-2">API Key</label>
                  <input
                    type="password"
                    value={formApiKey}
                    onChange={(e) => setFormApiKey(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                    placeholder={editingConnector ? '(unchanged)' : ''}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Requires pfSense-API package installed
                  </p>
                </div>
              )}

              {/* OPNsense uses API Key + Secret */}
              {formType === 'opnsense' && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">API Key</label>
                    <input
                      type="password"
                      value={formApiKey}
                      onChange={(e) => setFormApiKey(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder={editingConnector ? '(unchanged)' : ''}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">API Secret</label>
                    <input
                      type="password"
                      value={formPassword}
                      onChange={(e) => setFormPassword(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder={editingConnector ? '(unchanged)' : ''}
                    />
                  </div>
                </div>
              )}

              {/* Address list / Firewall group */}
              <div>
                <label className="block text-sm font-medium mb-2">
                  {formType === 'routeros' ? 'Address List Name' :
                   formType === 'unifi' ? 'Firewall Group Name' : 'Alias Name'}
                </label>
                <input
                  type="text"
                  value={formAddressList}
                  onChange={(e) => setFormAddressList(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder={formType === 'unifi' ? 'Ghostwire Blocked' : 'ghostwire-blocked'}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {formType === 'routeros' && 'Address list in IP → Firewall → Address Lists'}
                  {formType === 'unifi' && 'Address group in Settings → Security → Firewall Groups (will be created if missing)'}
                  {formType === 'pfsense' && 'Firewall alias name for blocked IPs'}
                  {formType === 'opnsense' && 'Firewall alias name for blocked IPs'}
                </p>
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
                  {editingConnector ? 'Save Changes' : 'Add Connector'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
