'use client'

import { useState, useEffect } from 'react'
import {
  Bell,
  BellOff,
  Loader2,
  Send,
  Mail,
  Globe,
  MessageSquare,
  Smartphone,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import PushSubscriptionManager from '@/components/notifications/push-subscription'

interface AlertPreference {
  id: string
  user_id: string
  alert_type: string
  min_severity: string
  channels: string | null
  enabled: boolean
}

interface AlertChannel {
  id: string
  user_id: string | null
  channel_type: string
  name: string
  config: string | null
  enabled: boolean
  created_at: string
}

const notificationTypes = [
  {
    key: 'threat_detected',
    label: 'Threat Detected',
    description: 'WAF blocks, honeypot hits, and suspicious activity',
    icon: '🛡️',
  },
  {
    key: 'ip_blocked',
    label: 'IP Blocked',
    description: 'When an IP is automatically blocked by the firewall',
    icon: '🚫',
  },
  {
    key: 'firewall_pushed',
    label: 'Firewall Rule Pushed',
    description: 'When firewall rules are synced to Cloudflare or other providers',
    icon: '🔥',
  },
  {
    key: 'cert_expiring',
    label: 'Certificate Expiring',
    description: 'SSL/TLS certificates approaching expiration',
    icon: '📜',
  },
  {
    key: 'host_down',
    label: 'Host Down',
    description: 'When a proxy host backend becomes unreachable',
    icon: '🔴',
  },
]

const severityLevels = [
  { value: 'low', label: 'All', color: 'text-slate-400' },
  { value: 'medium', label: 'Medium+', color: 'text-yellow-500' },
  { value: 'high', label: 'High+', color: 'text-orange-500' },
  { value: 'critical', label: 'Critical', color: 'text-red-500' },
]

const channelIcons: Record<string, typeof Mail> = {
  email: Mail,
  webhook: Globe,
  slack: MessageSquare,
  telegram: MessageSquare,
  push: Smartphone,
}

const channelColors: Record<string, string> = {
  email: 'bg-blue-500/10 text-blue-500',
  webhook: 'bg-cyan-500/10 text-cyan-500',
  slack: 'bg-purple-500/10 text-purple-500',
  telegram: 'bg-sky-500/10 text-sky-500',
  push: 'bg-green-500/10 text-green-500',
}

export default function NotificationsPage() {
  const [activeTab, setActiveTab] = useState<'subscriptions' | 'channels' | 'devices'>('subscriptions')
  const [preferences, setPreferences] = useState<AlertPreference[]>([])
  const [channels, setChannels] = useState<AlertChannel[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState<string | null>(null)
  const [isTesting, setIsTesting] = useState(false)
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // Channel form
  const [showChannelDialog, setShowChannelDialog] = useState(false)
  const [editingChannel, setEditingChannel] = useState<AlertChannel | null>(null)
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('webhook')
  const [formConfig, setFormConfig] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const confirm = useConfirm()

  useEffect(() => {
    if (!notification) return
    const timer = setTimeout(() => setNotification(null), 5000)
    return () => clearTimeout(timer)
  }, [notification])

  useEffect(() => {
    fetchAll()
  }, [])

  const fetchAll = async () => {
    setIsLoading(true)
    try {
      const [prefRes, chanRes] = await Promise.all([
        api.get('/api/alerts/preferences'),
        api.get('/api/alerts/channels'),
      ])
      setPreferences(prefRes.data)
      setChannels(chanRes.data)
    } catch {
      setNotification({ type: 'error', message: 'Failed to load notification settings' })
    } finally {
      setIsLoading(false)
    }
  }

  // --- Subscription toggles ---

  const getPref = (alertType: string) => preferences.find((p) => p.alert_type === alertType)

  const toggleSubscription = async (alertType: string) => {
    const existing = getPref(alertType)
    setIsSaving(alertType)
    try {
      if (existing) {
        await api.put(`/api/alerts/preferences/${existing.id}`, { enabled: !existing.enabled })
      } else {
        await api.post('/api/alerts/preferences', { alert_type: alertType, min_severity: 'medium', enabled: true })
      }
      const res = await api.get('/api/alerts/preferences')
      setPreferences(res.data)
    } catch {
      setNotification({ type: 'error', message: 'Failed to update subscription' })
    } finally {
      setIsSaving(null)
    }
  }

  const updateSeverity = async (alertType: string, severity: string) => {
    const existing = getPref(alertType)
    setIsSaving(alertType)
    try {
      if (existing) {
        await api.put(`/api/alerts/preferences/${existing.id}`, { min_severity: severity })
      } else {
        await api.post('/api/alerts/preferences', { alert_type: alertType, min_severity: severity, enabled: true })
      }
      const res = await api.get('/api/alerts/preferences')
      setPreferences(res.data)
    } catch {
      setNotification({ type: 'error', message: 'Failed to update severity' })
    } finally {
      setIsSaving(null)
    }
  }

  // --- Channel CRUD ---

  const resetChannelForm = () => {
    setFormName('')
    setFormType('webhook')
    setFormConfig('')
    setFormEnabled(true)
    setFormError('')
  }

  const handleCreateChannel = () => {
    resetChannelForm()
    setEditingChannel(null)
    setShowChannelDialog(true)
  }

  const handleEditChannel = (channel: AlertChannel) => {
    setFormName(channel.name)
    setFormType(channel.channel_type)
    setFormConfig(channel.config || '')
    setFormEnabled(channel.enabled)
    setEditingChannel(channel)
    setShowChannelDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitChannel = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError('')
    setIsSubmitting(true)
    try {
      const data = { name: formName, channel_type: formType, config: formConfig || null, enabled: formEnabled }
      if (editingChannel) {
        await api.put(`/api/alerts/channels/${editingChannel.id}`, data)
      } else {
        await api.post('/api/alerts/channels', data)
      }
      setShowChannelDialog(false)
      const res = await api.get('/api/alerts/channels')
      setChannels(res.data)
      setNotification({ type: 'success', message: editingChannel ? 'Channel updated' : 'Channel created' })
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to save channel')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteChannel = async (channel: AlertChannel) => {
    if (!(await confirm({ description: `Delete channel "${channel.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/alerts/channels/${channel.id}`)
      const res = await api.get('/api/alerts/channels')
      setChannels(res.data)
      setNotification({ type: 'success', message: 'Channel deleted' })
    } catch {
      setNotification({ type: 'error', message: 'Failed to delete channel' })
    }
    setActiveDropdown(null)
  }

  const handleTestAlert = async () => {
    setIsTesting(true)
    try {
      await api.post('/api/alerts/test')
      setNotification({ type: 'success', message: 'Test notification sent to all channels!' })
    } catch {
      setNotification({ type: 'error', message: 'Failed to send test alert' })
    } finally {
      setIsTesting(false)
    }
  }

  const getConfigPlaceholder = () => {
    switch (formType) {
      case 'webhook': return '{"url": "https://hooks.example.com/..."}'
      case 'email': return '{"to": "admin@example.com", "smtp_host": "smtp.gmail.com"}'
      case 'slack': return '{"webhook_url": "https://hooks.slack.com/..."}'
      case 'telegram': return '{"bot_token": "...", "chat_id": "..."}'
      case 'push': return '(configured via Push Devices tab)'
      default: return '{}'
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading notifications...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Bell className="h-6 w-6 text-primary" />
            Notifications
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Choose what you get notified about and how
          </p>
        </div>
        {activeTab === 'channels' && (
          <div className="flex gap-2">
            <button
              onClick={handleTestAlert}
              disabled={isTesting}
              className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm hover:bg-muted disabled:opacity-50"
            >
              {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Test
            </button>
            <button
              onClick={handleCreateChannel}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" />
              Add Channel
            </button>
          </div>
        )}
      </div>

      {/* Notification banner */}
      {notification && (
        <div className={`rounded-md px-4 py-3 text-sm flex items-center justify-between ${
          notification.type === 'success' ? 'bg-green-500/15 text-green-600 dark:text-green-400' : 'bg-destructive/15 text-destructive'
        }`}>
          <span className="flex items-center gap-2">
            {notification.type === 'success' ? <CheckCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
            {notification.message}
          </span>
          <button onClick={() => setNotification(null)} className="ml-4 hover:opacity-70">&times;</button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {([
          { key: 'subscriptions', label: 'Subscriptions' },
          { key: 'channels', label: 'Channels' },
          { key: 'devices', label: 'Push Devices' },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-background shadow-sm'
                : 'hover:bg-background/50 text-muted-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* === SUBSCRIPTIONS TAB === */}
      {activeTab === 'subscriptions' && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Toggle which event types you want to be notified about. Alerts are sent to all your enabled channels.
          </p>

          <div className="rounded-xl border border-border bg-card divide-y divide-border">
            {notificationTypes.map((nt) => {
              const pref = getPref(nt.key)
              const isEnabled = pref?.enabled ?? false
              const severity = pref?.min_severity ?? 'medium'
              const saving = isSaving === nt.key

              return (
                <div key={nt.key} className="flex items-center justify-between p-4 gap-4">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <span className="text-xl shrink-0">{nt.icon}</span>
                    <div className="min-w-0">
                      <h3 className="font-medium text-sm">{nt.label}</h3>
                      <p className="text-xs text-muted-foreground">{nt.description}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    {/* Severity selector */}
                    <select
                      value={severity}
                      onChange={(e) => updateSeverity(nt.key, e.target.value)}
                      disabled={saving}
                      className="px-2 py-1 rounded-md border border-input bg-background text-xs focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                    >
                      {severityLevels.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>

                    {/* Toggle */}
                    <button
                      onClick={() => toggleSubscription(nt.key)}
                      disabled={saving}
                      className="relative shrink-0"
                    >
                      {saving ? (
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      ) : isEnabled ? (
                        <div className="w-11 h-6 bg-primary rounded-full relative transition-colors">
                          <div className="absolute top-0.5 right-[2px] bg-white rounded-full h-5 w-5 transition-all" />
                        </div>
                      ) : (
                        <div className="w-11 h-6 bg-muted rounded-full relative transition-colors">
                          <div className="absolute top-0.5 left-[2px] bg-white rounded-full h-5 w-5 transition-all" />
                        </div>
                      )}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          {channels.length === 0 && (
            <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-4 text-sm text-yellow-600 dark:text-yellow-400">
              <strong>No channels configured.</strong> Go to the Channels tab to add a delivery method (webhook, Slack, push, etc.)
            </div>
          )}
        </div>
      )}

      {/* === CHANNELS TAB === */}
      {activeTab === 'channels' && (
        <div className="space-y-3">
          {channels.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <BellOff className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">No delivery channels configured</p>
              <p className="text-sm text-muted-foreground mt-1">
                Add a channel to start receiving notifications
              </p>
            </div>
          ) : (
            channels.map((channel) => {
              const Icon = channelIcons[channel.channel_type] || Bell
              return (
                <div key={channel.id} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`shrink-0 p-2 rounded-lg ${channelColors[channel.channel_type] || 'bg-muted'}`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-sm">{channel.name}</h3>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${channelColors[channel.channel_type] || 'bg-muted'}`}>
                            {channel.channel_type}
                          </span>
                          {!channel.enabled && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-400">disabled</span>
                          )}
                        </div>
                        {channel.config && (
                          <p className="text-xs text-muted-foreground mt-0.5 truncate">{channel.config}</p>
                        )}
                      </div>
                    </div>

                    <div className="relative shrink-0 ml-4" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setActiveDropdown(activeDropdown === channel.id ? null : channel.id)}
                        className="rounded-lg p-2 hover:bg-muted"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {activeDropdown === channel.id && (
                        <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-lg border border-border bg-card shadow-lg">
                          <div className="p-1">
                            <button
                              onClick={() => handleEditChannel(channel)}
                              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                            >
                              <Pencil className="h-4 w-4" />
                              Edit
                            </button>
                            <button
                              onClick={() => handleDeleteChannel(channel)}
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
      )}

      {/* === PUSH DEVICES TAB === */}
      {activeTab === 'devices' && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Manage browser push notification subscriptions for this device.
          </p>
          <div className="rounded-xl border border-border bg-card p-6">
            <PushSubscriptionManager />
          </div>
        </div>
      )}

      {/* Channel Dialog */}
      {showChannelDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingChannel ? 'Edit Channel' : 'Add Delivery Channel'}
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                Configure where your notifications get delivered
              </p>
            </div>

            <form onSubmit={handleSubmitChannel} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="e.g. Security Alerts Slack"
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
                  <option value="webhook">Webhook</option>
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                  <option value="telegram">Telegram</option>
                  <option value="push">Web Push</option>
                </select>
              </div>

              {formType !== 'push' && (
                <div>
                  <label className="block text-sm font-medium mb-2">Configuration (JSON)</label>
                  <textarea
                    value={formConfig}
                    onChange={(e) => setFormConfig(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    rows={4}
                    placeholder={getConfigPlaceholder()}
                  />
                </div>
              )}

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="channel-enabled"
                  checked={formEnabled}
                  onChange={(e) => setFormEnabled(e.target.checked)}
                  className="h-4 w-4"
                />
                <label htmlFor="channel-enabled" className="text-sm">Enabled</label>
              </div>

              {formError && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {formError}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowChannelDialog(false)}
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
                  {editingChannel ? 'Save Changes' : 'Add Channel'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
