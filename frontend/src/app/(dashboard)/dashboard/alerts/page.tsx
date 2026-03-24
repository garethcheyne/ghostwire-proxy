'use client'

import { useState, useEffect } from 'react'
import {
  Bell,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  Send,
  Mail,
  Globe,
  MessageSquare,
  Smartphone,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react'
import Link from 'next/link'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'

interface AlertChannel {
  id: string
  user_id: string | null
  channel_type: string
  name: string
  config: string | null
  enabled: boolean
  created_at: string
}

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

export default function AlertsPage() {
  const [channels, setChannels] = useState<AlertChannel[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingChannel, setEditingChannel] = useState<AlertChannel | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

  // Channel form
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('webhook')
  const [formConfig, setFormConfig] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const confirm = useConfirm()

  useEffect(() => {
    if (!notification) return
    const timer = setTimeout(() => setNotification(null), 5000)
    return () => clearTimeout(timer)
  }, [notification])

  useEffect(() => {
    fetchChannels()
  }, [])

  const fetchChannels = async () => {
    setIsLoading(true)
    try {
      const res = await api.get('/api/alerts/channels')
      setChannels(res.data)
    } catch {
      setNotification({ type: 'error', message: 'Failed to load channels' })
    } finally {
      setIsLoading(false)
    }
  }

  const resetChannelForm = () => {
    setFormName('')
    setFormType('webhook')
    setFormConfig('')
    setFormEnabled(true)
    setError('')
  }

  const handleCreateChannel = () => {
    resetChannelForm()
    setEditingChannel(null)
    setShowCreateDialog(true)
  }

  const handleEditChannel = (channel: AlertChannel) => {
    setFormName(channel.name)
    setFormType(channel.channel_type)
    setFormConfig(channel.config || '')
    setFormEnabled(channel.enabled)
    setEditingChannel(channel)
    setShowCreateDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitChannel = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      const data = { name: formName, channel_type: formType, config: formConfig || null, enabled: formEnabled }
      if (editingChannel) {
        await api.put(`/api/alerts/channels/${editingChannel.id}`, data)
      } else {
        await api.post('/api/alerts/channels', data)
      }
      setShowCreateDialog(false)
      fetchChannels()
      setNotification({ type: 'success', message: editingChannel ? 'Channel updated' : 'Channel created' })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save channel')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteChannel = async (channel: AlertChannel) => {
    if (!(await confirm({ description: `Delete alert channel "${channel.name}"?`, variant: 'destructive' }))) return
    try {
      await api.delete(`/api/alerts/channels/${channel.id}`)
      fetchChannels()
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
      case 'webhook': return '{"url": "https://hooks.slack.com/..."}'
      case 'email': return '{"to": "admin@example.com", "smtp_host": "smtp.gmail.com"}'
      case 'slack': return '{"webhook_url": "https://hooks.slack.com/..."}'
      case 'telegram': return '{"bot_token": "...", "chat_id": "..."}'
      case 'push': return '(configured via browser push subscription)'
      default: return '{}'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <AlertTriangle className="h-6 w-6 text-amber-500" />
            Alert Channels
          </h1>
          <p className="text-muted-foreground">
            Manage global alert delivery channels (admin)
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestAlert}
            disabled={isTesting}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm hover:bg-muted disabled:opacity-50"
          >
            {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Test Alert
          </button>
          <button
            onClick={handleCreateChannel}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Add Channel
          </button>
        </div>
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

      {/* User notification preferences link */}
      <Link href="/dashboard/notifications">
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 hover:bg-primary/10 transition-colors cursor-pointer">
          <div className="flex items-center gap-3">
            <Bell className="h-5 w-5 text-primary" />
            <div>
              <p className="text-sm font-medium">Looking for your personal notification preferences?</p>
              <p className="text-xs text-muted-foreground">Go to Notifications to choose which events you subscribe to</p>
            </div>
          </div>
        </div>
      </Link>

      {isLoading ? (
        <div className="flex h-96 items-center justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      ) : channels.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Bell className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
          <p className="text-muted-foreground">No alert channels configured</p>
          <p className="text-sm text-muted-foreground mt-1">
            Add webhook, email, Slack, or Telegram channels
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {channels.map((channel) => {
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
                        <h3 className="font-semibold">{channel.name}</h3>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${channelColors[channel.channel_type] || 'bg-muted'}`}>
                          {channel.channel_type}
                        </span>
                        {channel.user_id === null && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">global</span>
                        )}
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
          })}
        </div>
      )}

      {/* Channel Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingChannel ? 'Edit Channel' : 'Add Alert Channel'}
              </h2>
            </div>

            <form onSubmit={handleSubmitChannel} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="Security Alerts Webhook"
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
