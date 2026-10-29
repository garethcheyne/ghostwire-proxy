'use client'

import { useEffect, useState } from 'react'
import { Mail, Loader2, Send, Eye, EyeOff } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { LoadError } from '@/components/load-state'
import { toastError, toastSuccess } from '@/lib/toast'

interface SmtpConfig {
  host: string
  port: number
  username: string
  from_address: string
  from_name: string
  security: string
  configured: boolean
  has_password: boolean
}

const EMPTY: SmtpConfig = {
  host: '',
  port: 587,
  username: '',
  from_address: '',
  from_name: 'Ghostwire Proxy',
  security: 'starttls',
  configured: false,
  has_password: false,
}

export function SmtpCard() {
  const [config, setConfig] = useState<SmtpConfig>(EMPTY)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testTo, setTestTo] = useState('')
  const [loadError, setLoadError] = useState(false)

  const load = () =>
    api
      .get('/api/reports/smtp')
      .then(({ data }) => {
        setConfig({ ...EMPTY, ...data })
        setLoadError(false)
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false))

  useEffect(() => {
    void load()
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const payload: Record<string, unknown> = { ...config }
      // An empty field means "leave the stored password alone".
      if (password) payload.password = password
      const { data } = await api.put('/api/reports/smtp', payload)
      setConfig({ ...EMPTY, ...data })
      setPassword('')
      toastSuccess('Mail settings saved.')
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not save mail settings')
    } finally {
      setSaving(false)
    }
  }

  const sendTest = async () => {
    setTesting(true)
    try {
      await api.post('/api/reports/smtp/test', { to: testTo })
      toastSuccess(`Test message sent to ${testTo}.`)
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not send the test message')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading mail settings…
        </div>
      </div>
    )
  }

  const field = 'w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary'

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Mail className="h-5 w-5" />
        Outgoing Mail (SMTP)
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        Used for scheduled traffic reports and email alerts. Until a server is
        configured here, both are silently undeliverable.
      </p>

      {loadError ? (
        <LoadError what="mail settings" onRetry={load} className="border-0 bg-transparent p-0" />
      ) : (
      <>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <label className="block text-sm font-medium">SMTP server</label>
          <input
            className={field}
            value={config.host}
            onChange={(e) => setConfig({ ...config, host: e.target.value })}
            placeholder="smtp.example.com"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">Port</label>
          <input
            type="number"
            className={field}
            value={config.port}
            onChange={(e) => setConfig({ ...config, port: parseInt(e.target.value) || 587 })}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">Security</label>
          <select
            className={field}
            value={config.security}
            onChange={(e) => setConfig({ ...config, security: e.target.value })}
          >
            <option value="starttls">STARTTLS (587)</option>
            <option value="ssl">Implicit TLS (465)</option>
            <option value="none">None</option>
          </select>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">Username</label>
          <input
            className={field}
            value={config.username}
            onChange={(e) => setConfig({ ...config, username: e.target.value })}
            autoComplete="off"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">
            Password{' '}
            {config.has_password && (
              <span className="text-xs text-muted-foreground font-normal">
                (stored — leave blank to keep)
              </span>
            )}
          </label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              className={field + ' pr-10'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={config.has_password ? '••••••••' : ''}
              autoComplete="new-password"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">From address</label>
          <input
            className={field}
            value={config.from_address}
            onChange={(e) => setConfig({ ...config, from_address: e.target.value })}
            placeholder="proxy@example.com"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">From name</label>
          <input
            className={field}
            value={config.from_name}
            onChange={(e) => setConfig({ ...config, from_name: e.target.value })}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 mt-5 pt-4 border-t border-border">
        <Button size="lg" onClick={save} disabled={saving}>
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save
        </Button>

        <div className="flex-1 min-w-[220px] space-y-2">
          <label className="block text-sm font-medium">Send a test message to</label>
          <div className="flex gap-2">
            <input
              type="email"
              className={field}
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="you@example.com"
            />
            <Button
              variant="outline"
              onClick={sendTest}
              disabled={testing || !testTo || !config.configured}
              title={!config.configured ? 'Save an SMTP server first' : undefined}
              className="h-10 flex-shrink-0"
            >
              {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              Test
            </Button>
          </div>
        </div>
      </div>
      </>
      )}
    </div>
  )
}
