'use client'

import { useState, useEffect } from 'react'
import {
  Settings,
  Save,
  RefreshCw,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Server,
  Archive,
  ChevronRight,
  Globe,
  Bell,
  ShieldCheck,
  Plus,
  X,
} from 'lucide-react'
import Link from 'next/link'
import api from '@/lib/api'
import PushSubscriptionManager from '@/components/notifications/push-subscription'

interface SystemSettings {
  nginx_config_path: string
  certificate_path: string
  auto_renew_certificates: boolean
  default_ssl_provider: string
  enable_traffic_logging: boolean
  traffic_log_retention_days: number
  enable_waf: boolean
  enable_rate_limiting: boolean
  rate_limit_requests_per_second: number
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings>({
    nginx_config_path: '/etc/nginx/conf.d',
    certificate_path: '/etc/nginx/certs',
    auto_renew_certificates: true,
    default_ssl_provider: 'letsencrypt',
    enable_traffic_logging: true,
    traffic_log_retention_days: 30,
    enable_waf: true,
    enable_rate_limiting: true,
    rate_limit_requests_per_second: 100,
  })
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isReloading, setIsReloading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [nginxStatus, setNginxStatus] = useState<'running' | 'stopped' | 'error'>('running')
  const [defaultSite, setDefaultSite] = useState({ behavior: 'congratulations', redirect_url: '' })
  const [isSavingDefault, setIsSavingDefault] = useState(false)
  const [trustedIps, setTrustedIps] = useState<string[]>([])
  const [newTrustedIp, setNewTrustedIp] = useState('')
  const [isSavingTrusted, setIsSavingTrusted] = useState(false)

  useEffect(() => {
    fetchSettings()
    fetchDefaultSite()
    fetchTrustedIps()
  }, [])

  const fetchSettings = async () => {
    try {
      const response = await api.get('/api/settings')
      if (response.data) {
        setSettings((prev) => ({ ...prev, ...response.data }))
      }
    } catch (error) {
      console.error('Failed to fetch settings:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    setMessage(null)

    try {
      await api.put('/api/settings', settings)
      setMessage({ type: 'success', text: 'Settings saved successfully' })
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save settings' })
    } finally {
      setIsSaving(false)
    }
  }

  const fetchDefaultSite = async () => {
    try {
      const { data } = await api.get('/api/settings/default-site')
      setDefaultSite(data)
    } catch (error) {
      console.error('Failed to fetch default site:', error)
    }
  }

  const handleSaveDefaultSite = async () => {
    setIsSavingDefault(true)
    setMessage(null)
    try {
      await api.put('/api/settings/default-site', defaultSite)
      setMessage({ type: 'success', text: 'Default site updated and applied' })
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to update default site' })
    } finally {
      setIsSavingDefault(false)
    }
  }

  const handleReloadNginx = async () => {
    setIsReloading(true)
    setMessage(null)

    try {
      await api.post('/api/settings/reload-nginx')
      setMessage({ type: 'success', text: 'Nginx configuration reloaded successfully' })
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to reload Nginx configuration' })
    } finally {
      setIsReloading(false)
    }
  }

  const fetchTrustedIps = async () => {
    try {
      const { data } = await api.get('/api/settings/trusted_ips')
      const parsed = JSON.parse(data.value || '[]')
      setTrustedIps(Array.isArray(parsed) ? parsed : [])
    } catch {
      setTrustedIps([])
    }
  }

  const saveTrustedIps = async (ips: string[]) => {
    setIsSavingTrusted(true)
    setMessage(null)
    try {
      await api.put('/api/settings/trusted_ips', { value: JSON.stringify(ips) })
      setTrustedIps(ips)
      setMessage({ type: 'success', text: 'Trusted IPs saved. Changes will take effect within 5 minutes.' })
    } catch {
      setMessage({ type: 'error', text: 'Failed to save trusted IPs' })
    } finally {
      setIsSavingTrusted(false)
    }
  }

  const addTrustedIp = () => {
    const ip = newTrustedIp.trim()
    if (!ip) return
    // Basic validation: IPv4, IPv4/CIDR
    const ipv4 = /^(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?$/
    if (!ipv4.test(ip)) {
      setMessage({ type: 'error', text: 'Invalid IP address or CIDR format (e.g. 192.168.1.1 or 10.0.0.0/24)' })
      return
    }
    if (trustedIps.includes(ip)) {
      setMessage({ type: 'error', text: 'This IP is already in the trusted list' })
      return
    }
    const updated = [...trustedIps, ip]
    setNewTrustedIp('')
    saveTrustedIps(updated)
  }

  const removeTrustedIp = (ip: string) => {
    saveTrustedIps(trustedIps.filter(i => i !== ip))
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-muted-foreground">
            Configure system-wide settings for your proxy
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleReloadNginx}
            disabled={isReloading}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isReloading ? 'animate-spin' : ''}`} />
            Reload Nginx
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save Settings
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`flex items-center gap-2 p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-green-500/10 text-green-500 border border-green-500/20'
              : 'bg-red-500/10 text-red-500 border border-red-500/20'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircle className="h-5 w-5" />
          ) : (
            <AlertTriangle className="h-5 w-5" />
          )}
          {message.text}
        </div>
      )}

      {/* System Status */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Server className="h-5 w-5" />
          System Status
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground mb-1">Nginx Status</p>
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${
                  nginxStatus === 'running' ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <span className="font-medium capitalize">{nginxStatus}</span>
            </div>
          </div>
          <div className="rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground mb-1">Config Path</p>
            <code className="text-sm">{settings.nginx_config_path}</code>
          </div>
          <div className="rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground mb-1">Certificate Path</p>
            <code className="text-sm">{settings.certificate_path}</code>
          </div>
        </div>
      </div>

      {/* Default Site */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Default Site
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          What happens when someone visits your server by IP address or uses a hostname that isn&apos;t configured as a proxy host.
        </p>
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { value: 'congratulations', label: 'Welcome Page', desc: 'Show a Ghostwire Proxy landing page' },
              { value: 'redirect', label: 'Redirect', desc: 'Redirect to a custom URL' },
              { value: '404', label: '404 Not Found', desc: 'Return a 404 error page' },
              { value: '444', label: 'Drop Connection', desc: 'Silently close the connection' },
            ].map((opt) => (
              <label
                key={opt.value}
                className={`relative flex flex-col rounded-lg border p-4 cursor-pointer transition-colors ${
                  defaultSite.behavior === opt.value
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-muted-foreground/30'
                }`}
              >
                <input
                  type="radio"
                  name="defaultSite"
                  value={opt.value}
                  checked={defaultSite.behavior === opt.value}
                  onChange={(e) => setDefaultSite({ ...defaultSite, behavior: e.target.value })}
                  className="sr-only"
                />
                <span className="font-medium text-sm">{opt.label}</span>
                <span className="text-xs text-muted-foreground mt-1">{opt.desc}</span>
              </label>
            ))}
          </div>

          {defaultSite.behavior === 'redirect' && (
            <div>
              <label className="block text-sm font-medium mb-2">Redirect URL</label>
              <input
                type="url"
                value={defaultSite.redirect_url}
                onChange={(e) => setDefaultSite({ ...defaultSite, redirect_url: e.target.value })}
                placeholder="https://example.com"
                className="w-full max-w-md px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleSaveDefaultSite}
              disabled={isSavingDefault}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isSavingDefault ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save & Apply
            </button>
          </div>
        </div>
      </div>

      {/* SSL Settings */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">SSL/TLS Settings</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Auto-renew Certificates</p>
              <p className="text-sm text-muted-foreground">
                Automatically renew Let's Encrypt certificates before expiry
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings.auto_renew_certificates}
                onChange={(e) =>
                  setSettings({ ...settings, auto_renew_certificates: e.target.checked })
                }
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Default SSL Provider</label>
            <select
              value={settings.default_ssl_provider}
              onChange={(e) =>
                setSettings({ ...settings, default_ssl_provider: e.target.value })
              }
              className="w-full max-w-xs px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="letsencrypt">Let's Encrypt</option>
              <option value="custom">Custom Certificate</option>
            </select>
          </div>
        </div>
      </div>

      {/* Logging Settings */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Logging Settings</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Enable Traffic Logging</p>
              <p className="text-sm text-muted-foreground">
                Log all requests passing through the proxy
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enable_traffic_logging}
                onChange={(e) =>
                  setSettings({ ...settings, enable_traffic_logging: e.target.checked })
                }
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Log Retention (days)</label>
            <input
              type="number"
              value={settings.traffic_log_retention_days}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  traffic_log_retention_days: parseInt(e.target.value) || 30,
                })
              }
              className="w-full max-w-xs px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
              min={1}
              max={365}
            />
          </div>
        </div>
      </div>

      {/* Backup & Restore */}
      <Link href="/dashboard/settings/backups">
        <div className="rounded-xl border border-border bg-card p-6 hover:border-primary/50 hover:bg-muted/50 transition-colors cursor-pointer group">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <Archive className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Backup & Restore</h2>
                <p className="text-sm text-muted-foreground">
                  Create backups, restore from previous backups, and configure automatic backup schedules
                </p>
              </div>
            </div>
            <ChevronRight className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
        </div>
      </Link>

      {/* Security Settings */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-4">Security Settings</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Enable WAF (Web Application Firewall)</p>
              <p className="text-sm text-muted-foreground">
                Block common web attacks and exploits
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enable_waf}
                onChange={(e) => setSettings({ ...settings, enable_waf: e.target.checked })}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Enable Rate Limiting</p>
              <p className="text-sm text-muted-foreground">
                Limit requests per IP address
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings.enable_rate_limiting}
                onChange={(e) =>
                  setSettings({ ...settings, enable_rate_limiting: e.target.checked })
                }
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>
          {settings.enable_rate_limiting && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Rate Limit (requests/second per IP)
              </label>
              <input
                type="number"
                value={settings.rate_limit_requests_per_second}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    rate_limit_requests_per_second: parseInt(e.target.value) || 100,
                  })
                }
                className="w-full max-w-xs px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                min={1}
              />
            </div>
          )}
        </div>
      </div>

      {/* Push Notifications */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
          <Bell className="h-5 w-5" />
          Push Notifications
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Receive real-time alerts about security threats, system updates, and important events on your devices.
        </p>
        <PushSubscriptionManager />
      </div>

      {/* Trusted IPs */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          Trusted IPs
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          IPs in this list bypass WAF, rate limiting, and are excluded from traffic logging.
          Use this to whitelist your own IP so your traffic isn&apos;t blocked or recorded.
          Supports individual IPs and CIDR notation (e.g. 10.0.0.0/24).
        </p>
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={newTrustedIp}
              onChange={(e) => setNewTrustedIp(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addTrustedIp()}
              placeholder="e.g. 203.86.201.144 or 10.0.0.0/8"
              className="flex-1 max-w-sm px-4 py-2 rounded-lg border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              onClick={addTrustedIp}
              disabled={isSavingTrusted || !newTrustedIp.trim()}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isSavingTrusted ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Add
            </button>
          </div>
          {trustedIps.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">No trusted IPs configured</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {trustedIps.map((ip) => (
                <div
                  key={ip}
                  className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-sm font-mono"
                >
                  <span>{ip}</span>
                  <button
                    onClick={() => removeTrustedIp(ip)}
                    disabled={isSavingTrusted}
                    className="text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
