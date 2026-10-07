'use client'
/*
 * Creating an API key, and showing it the one time it can be shown.
 *
 * Its own module because two pages need it: Settings > API keys, where keys are managed, and
 * Settings > AI agents (MCP), where someone connecting Claude Code is most likely to go looking.
 * One implementation, so the scopes, expiry choices and warning cannot drift apart.
 */
import { useEffect, useState } from 'react'
import { Check, Copy, KeyRound, Loader2, Plus } from 'lucide-react'
import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export interface ApiKeyScope {
  name: string
  description: string
}

export interface ApiKeyRow {
  id: string
  name: string
  prefix: string
  display: string
  scopes: string[]
  created_by: string
  created_by_email: string | null
  created_at: string
  last_used_at: string | null
  last_used_ip: string | null
  expires_at: string | null
  revoked_at: string | null
  status: 'active' | 'expired' | 'revoked'
}

const EXPIRY = [
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '1 year' },
  { value: 'never', label: 'Never' },
]

/** Scope sets worth offering in one click. */
export const PRESETS: { label: string; scopes: string[] }[] = [
  { label: 'Read only', scopes: ['read'] },
  { label: 'Configure hosts', scopes: ['read', 'write:proxy-hosts', 'write:upstreams', 'write:certificates', 'write:access', 'write:nginx'] },
]

export function useScopes() {
  const [scopes, setScopes] = useState<ApiKeyScope[]>([])
  useEffect(() => {
    api.get('/api/api-keys/scopes').then(r => setScopes(r.data)).catch(() => {})
  }, [])
  return scopes
}

function errorDetail(e: unknown, fallback: string) {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          toastError('Could not copy — select the text and copy it instead')
        }
      }}
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      <span className="ml-1.5">{copied ? 'Copied' : label}</span>
    </Button>
  )
}

export function CreateKey({
  onCreated,
  defaultScopes = ['read'],
  defaultName = '',
}: {
  onCreated: (key: string) => void
  defaultScopes?: string[]
  defaultName?: string
}) {
  const scopes = useScopes()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(defaultName)
  const [chosen, setChosen] = useState<string[]>(defaultScopes)
  const [expiry, setExpiry] = useState('90')
  const [code, setCode] = useState('')
  const [saving, setSaving] = useState(false)

  const reset = () => {
    setName(defaultName)
    setChosen(defaultScopes)
    setExpiry('90')
    setCode('')
  }

  const toggle = (scope: string, on: boolean) =>
    setChosen(prev => (on ? [...new Set([...prev, scope])] : prev.filter(s => s !== scope)))

  const hasAdmin = chosen.includes('admin')

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    try {
      const { data } = await api.post('/api/api-keys/', {
        name: name.trim(),
        scopes: chosen,
        expires_in_days: expiry === 'never' ? null : Number(expiry),
        code: code.trim(),
      })
      onCreated(data.key)
      toastSuccess('API key created')
      setOpen(false)
      reset()
    } catch (e) {
      toastError(errorDetail(e, 'Could not create the key'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={o => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1.5 h-4 w-4" />
          New key
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={handleSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>New API key</DialogTitle>
            <DialogDescription>
              The key acts as you, limited to the scopes you tick. Give it a name you&apos;ll recognise
              in the audit log.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              required
              maxLength={100}
              placeholder="Claude Code on my laptop"
              value={name}
              onChange={e => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label>Scopes</Label>
              <div className="flex gap-1">
                {PRESETS.map(p => (
                  <Button key={p.label} type="button" variant="ghost" size="sm" onClick={() => setChosen(p.scopes)}>
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-2 rounded-lg border border-border p-3">
              {scopes.map(scope => {
                const always = scope.name === 'read'
                const checked = always || hasAdmin || chosen.includes(scope.name)
                return (
                  <label key={scope.name} className="flex cursor-pointer items-start gap-3">
                    <Checkbox
                      className="mt-0.5"
                      checked={checked}
                      disabled={always || (hasAdmin && scope.name !== 'admin')}
                      onCheckedChange={v => toggle(scope.name, v === true)}
                    />
                    <span className="min-w-0">
                      <code className="font-mono text-xs font-semibold">{scope.name}</code>
                      <span className="block text-xs text-muted-foreground">{scope.description}</span>
                    </span>
                  </label>
                )
              })}
              {!scopes.length && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            </div>
            <p className="text-xs text-muted-foreground">
              Every key can read. Users, API keys, two-factor, updates, backup restore and the kill
              switch are never available to keys, whatever the scopes.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Expires after</Label>
              <Select value={expiry} onValueChange={setExpiry}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXPIRY.map(option => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="key-code">Two-factor code</Label>
              <Input
                id="key-code"
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                maxLength={16}
                value={code}
                onChange={e => setCode(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={saving || !name.trim() || !code.trim()}>
              {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Create key
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * The key, once. Only a hash is stored, so a key that is not copied here is gone — worth saying
 * plainly rather than leaving someone to discover it after they navigate away.
 */
export function NewKeyAlert({ value }: { value: string }) {
  return (
    <Alert className="border-primary/30 bg-primary/5">
      <KeyRound className="h-4 w-4" />
      <AlertTitle>Copy your new key now</AlertTitle>
      <AlertDescription className="space-y-2">
        <p className="text-sm text-muted-foreground">It won&apos;t be shown again.</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={value} readOnly className="font-mono text-xs" onFocus={e => e.target.select()} />
          <CopyButton value={value} label="Copy key" />
        </div>
      </AlertDescription>
    </Alert>
  )
}
