'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Copy,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  Rows3,
  Server,
  Trash2,
  Wrench,
} from 'lucide-react'
import api from '@/lib/api'
import { useDebounced } from '@/lib/use-debounced'
import { toastError, toastSuccess } from '@/lib/toast'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Modal, ModalBody, ModalDescription, ModalFooter, ModalHeader, ModalTitle } from '@/components/ui/modal'
import type {
  HealthStatus,
  LbMethod,
  ProxyHost,
  UpstreamCheckResult,
  UpstreamPreview,
} from '@/types'

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

/** A server row as edited in the dialog (`id` only once it is saved). */
export interface ServerDraft {
  key: string
  id?: string
  host: string
  port: number
  weight: number
  max_fails: number
  fail_timeout: number
  backup: boolean
  down: boolean
  max_conns: number | null
  enabled: boolean
  last_status?: HealthStatus
  last_latency_ms?: number | null
  last_error?: string | null
  last_check_at?: string | null
  auto_down?: boolean
}

export interface BackendsValue {
  mode: 'single' | 'balanced'
  lb_method: LbMethod
  upstream_keepalive: number
  health_check_type: 'http' | 'tcp'
  health_check_path: string
  health_check_timeout: number
  lb_auto_down: boolean
  servers: ServerDraft[]
}

export const LB_METHODS: { value: LbMethod; label: string; hint: string; backup: boolean }[] = [
  {
    value: 'round_robin',
    label: 'Round robin',
    hint: 'Takes turns, in proportion to each server’s weight. Good when every request costs about the same.',
    backup: true,
  },
  {
    value: 'least_conn',
    label: 'Least connections',
    hint: 'Sends each request to the server with the fewest open requests. Recommended when some pages are much slower than others.',
    backup: true,
  },
  {
    value: 'ip_hash',
    label: 'IP hash (sticky sessions)',
    hint: 'A visitor’s IP always lands on the same server, so in-memory sessions keep working. No backup servers.',
    backup: false,
  },
  {
    value: 'hash_uri',
    label: 'URI hash',
    hint: 'The same URL always goes to the same server (consistent hashing); good for per-server caches. No backup servers.',
    backup: false,
  },
  {
    value: 'random_two',
    label: 'Random, two choices',
    hint: 'Picks two servers at random and uses the less busy one. Spreads load well with many servers. No backup servers.',
    backup: false,
  },
]

const methodLabel = (m: LbMethod) => LB_METHODS.find((x) => x.value === m)?.label ?? m

let draftCounter = 0
const newKey = () => `draft-${Date.now().toString(36)}-${++draftCounter}`

export function newServer(host: string, port: number, extra: Partial<ServerDraft> = {}): ServerDraft {
  return {
    key: newKey(),
    host,
    port,
    weight: 1,
    max_fails: 3,
    fail_timeout: 30,
    backup: false,
    down: false,
    max_conns: null,
    enabled: true,
    last_status: 'unknown',
    ...extra,
  }
}

export function backendsFromHost(host: ProxyHost | null): BackendsValue {
  const servers = (host?.upstream_servers ?? []).map((s) => ({
    key: s.id,
    id: s.id,
    host: s.host,
    port: s.port,
    weight: s.weight,
    max_fails: s.max_fails,
    fail_timeout: s.fail_timeout,
    backup: s.backup ?? false,
    down: s.down ?? false,
    max_conns: s.max_conns ?? null,
    enabled: s.enabled,
    last_status: s.last_status ?? 'unknown',
    last_latency_ms: s.last_latency_ms ?? null,
    last_error: s.last_error ?? null,
    last_check_at: s.last_check_at ?? null,
    auto_down: s.auto_down ?? false,
  }))
  return {
    mode: servers.length > 0 ? 'balanced' : 'single',
    lb_method: host?.lb_method ?? 'round_robin',
    upstream_keepalive: host?.upstream_keepalive ?? 32,
    health_check_type: host?.health_check_type ?? 'http',
    health_check_path: host?.health_check_path ?? '/',
    health_check_timeout: host?.health_check_timeout ?? 5,
    lb_auto_down: host?.lb_auto_down ?? false,
    servers,
  }
}

/** The API body for the servers (no UI-only keys or health fields). */
export function serversPayload(value: BackendsValue) {
  if (value.mode === 'single') return []
  return value.servers.map((s) => ({
    ...(s.id ? { id: s.id } : {}),
    host: s.host.trim(),
    port: s.port,
    weight: s.weight,
    max_fails: s.max_fails,
    fail_timeout: s.fail_timeout,
    backup: s.backup,
    down: s.down,
    max_conns: s.max_conns,
    enabled: s.enabled,
  }))
}

export function lbSettingsPayload(value: BackendsValue) {
  return {
    lb_method: value.lb_method,
    upstream_keepalive: value.upstream_keepalive,
    health_check_type: value.health_check_type,
    health_check_path: value.health_check_path.trim() || '/',
    health_check_timeout: value.health_check_timeout,
    lb_auto_down: value.lb_auto_down,
  }
}

const HOST_RE = /^(?=.{1,253}$)[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?(\.[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?)*\.?$/
const IPV6_RE = /^\[?[0-9A-Fa-f:.]+\]?$/

export function hostError(host: string): string | null {
  const v = host.trim()
  if (!v) return 'Host is required'
  if (v.includes(':') ? IPV6_RE.test(v) : HOST_RE.test(v)) return null
  return 'IP address or hostname only — no scheme, port or path'
}

/** Per-server field problems, keyed by the server's draft key. */
export function serverFieldErrors(s: ServerDraft): string[] {
  const out: string[] = []
  const h = hostError(s.host)
  if (h) out.push(h)
  if (!Number.isInteger(s.port) || s.port < 1 || s.port > 65535) out.push('Port must be 1–65535')
  if (!Number.isInteger(s.weight) || s.weight < 1 || s.weight > 100) out.push('Weight must be 1–100')
  if (s.max_conns !== null && (!Number.isInteger(s.max_conns) || s.max_conns < 1 || s.max_conns > 100000))
    out.push('Max connections must be 1–100000, or empty')
  if (!Number.isInteger(s.max_fails) || s.max_fails < 0 || s.max_fails > 100) out.push('Max fails must be 0–100')
  if (!Number.isInteger(s.fail_timeout) || s.fail_timeout < 1 || s.fail_timeout > 3600) out.push('Fail timeout must be 1–3600 s')
  return out
}

/** Group-level problems, mirroring the API's rules so Save can be blocked early. */
export function groupErrors(value: BackendsValue): string[] {
  if (value.mode === 'single') return []
  const out: string[] = []
  if (value.servers.length === 0) {
    out.push('Add at least one server, or switch back to a single backend')
    return out
  }
  const enabled = value.servers.filter((s) => s.enabled)
  if (!enabled.some((s) => !s.backup)) out.push('At least one enabled server that isn’t a backup is required')
  const method = LB_METHODS.find((m) => m.value === value.lb_method)
  if (method && !method.backup && enabled.some((s) => s.backup))
    out.push(`${method.label} can’t be combined with backup servers (an nginx restriction)`)
  const seen = new Set<string>()
  for (const s of value.servers) {
    const k = `${s.host.trim().toLowerCase()}:${s.port}`
    if (seen.has(k)) out.push(`${k} is listed more than once`)
    seen.add(k)
  }
  if (value.servers.some((s) => serverFieldErrors(s).length > 0)) out.push('Fix the highlighted servers')
  const p = value.health_check_path.trim()
  if (p && (!p.startsWith('/') || p.startsWith('//') || /[\s#]/.test(p)))
    out.push('Health check path must start with a single “/” and contain no spaces or “#”')
  return out
}

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function HealthDot({ server }: { server: ServerDraft }) {
  const status = server.id ? server.last_status ?? 'unknown' : 'unknown'
  const label = !server.id
    ? 'Not saved yet'
    : status === 'up'
      ? `Up${server.last_latency_ms != null ? ` · ${server.last_latency_ms} ms` : ''}`
      : status === 'down'
        ? `Down${server.last_error ? ` · ${server.last_error}` : ''}`
        : 'Not checked yet'
  return (
    <span className="flex items-center gap-2 whitespace-nowrap" title={label}>
      <span
        className={cn(
          'h-2.5 w-2.5 shrink-0 rounded-full',
          status === 'up' && 'bg-green-500',
          status === 'down' && 'bg-red-500',
          status === 'unknown' && 'bg-muted-foreground/40'
        )}
      />
      <span
        className={cn(
          'text-xs',
          status === 'up' && 'text-green-600 dark:text-green-400',
          status === 'down' && 'text-red-600 dark:text-red-400',
          status === 'unknown' && 'text-muted-foreground'
        )}
      >
        {status === 'up' ? (server.last_latency_ms != null ? `${server.last_latency_ms} ms` : 'up') : status === 'down' ? 'down' : '—'}
      </span>
    </span>
  )
}

function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  placeholder,
  allowEmpty,
  hint,
}: {
  id: string
  label: string
  value: number | null
  onChange: (v: number | null) => void
  min?: number
  max?: number
  placeholder?: string
  allowEmpty?: boolean
  hint?: string
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        placeholder={placeholder}
        value={value ?? ''}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') onChange(allowEmpty ? null : NaN)
          else onChange(parseInt(raw, 10))
        }}
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function SwitchRow({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Server editor dialog
// ---------------------------------------------------------------------------

function ServerDialog({
  open,
  onOpenChange,
  initial,
  backupAllowed,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  initial: ServerDraft | null
  backupAllowed: boolean
  onSave: (server: ServerDraft) => void
}) {
  // Remounted (via key) each time it opens, so this starts from `initial`
  const [draft, setDraft] = useState<ServerDraft>(() => initial ?? newServer('', 8080))

  const errors = serverFieldErrors(draft)
  const set = (patch: Partial<ServerDraft>) => setDraft((d) => ({ ...d, ...patch }))

  return (
    <Modal open={open} onOpenChange={onOpenChange} size="lg">
      <ModalHeader className="p-6 pb-2">
        <ModalTitle>{initial ? 'Edit server' : 'Add server'}</ModalTitle>
        <ModalDescription>One backend process that nginx can send requests to.</ModalDescription>
      </ModalHeader>
      <ModalBody className="space-y-4 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="srv-host">Host</Label>
            <Input
              id="srv-host"
              value={draft.host}
              onChange={(e) => set({ host: e.target.value })}
              placeholder="10.0.0.5"
              aria-invalid={!!hostError(draft.host)}
              autoFocus
            />
          </div>
          <NumberField id="srv-port" label="Port" value={draft.port} min={1} max={65535} onChange={(v) => set({ port: v as number })} />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <NumberField
            id="srv-weight"
            label="Weight"
            value={draft.weight}
            min={1}
            max={100}
            onChange={(v) => set({ weight: v as number })}
            hint="Relative share of traffic (1–100). A weight of 2 gets twice the requests of 1."
          />
          <NumberField
            id="srv-maxconns"
            label="Max connections"
            value={draft.max_conns}
            min={1}
            allowEmpty
            placeholder="Unlimited"
            onChange={(v) => set({ max_conns: v })}
            hint="Cap on simultaneous connections; empty for no limit."
          />
          <NumberField
            id="srv-maxfails"
            label="Max fails"
            value={draft.max_fails}
            min={0}
            max={100}
            onChange={(v) => set({ max_fails: v as number })}
            hint="Failures within the timeout before nginx skips this server (0 = never)."
          />
          <NumberField
            id="srv-failtimeout"
            label="Fail timeout (s)"
            value={draft.fail_timeout}
            min={1}
            max={3600}
            onChange={(v) => set({ fail_timeout: v as number })}
            hint="How long a failing server is skipped, and the window failures are counted in."
          />
        </div>
        <div className="space-y-2">
          <SwitchRow
            id="srv-backup"
            label="Backup"
            hint={
              backupAllowed
                ? 'Only receives traffic when every primary server is unavailable.'
                : 'Not available with the selected balancing method (an nginx restriction).'
            }
            checked={draft.backup}
            disabled={!backupAllowed && !draft.backup}
            onChange={(v) => set({ backup: v })}
          />
          <SwitchRow
            id="srv-down"
            label="Maintenance (down)"
            hint="Keeps the server in the group but sends it no traffic, e.g. while you deploy to it."
            checked={draft.down}
            onChange={(v) => set({ down: v })}
          />
          <SwitchRow
            id="srv-enabled"
            label="Enabled"
            hint="Disabled servers are left out of the config entirely."
            checked={draft.enabled}
            onChange={(v) => set({ enabled: v })}
          />
        </div>
        {errors.length > 0 && (
          <ul className="space-y-1 text-sm text-destructive">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </ModalBody>
      <ModalFooter className="p-6 pt-2">
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button
          disabled={errors.length > 0}
          onClick={() => {
            onSave({ ...draft, host: draft.host.trim() })
            onOpenChange(false)
          }}
        >
          {initial ? 'Update server' : 'Add server'}
        </Button>
      </ModalFooter>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Port range helper
// ---------------------------------------------------------------------------

function PortRangeDialog({
  open,
  onOpenChange,
  defaultHost,
  onAdd,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultHost: string
  onAdd: (host: string, ports: number[]) => void
}) {
  // Remounted (via key) each time it opens, so the host starts from defaultHost
  const [host, setHost] = useState(defaultHost)
  const [start, setStart] = useState<number>(8050)
  const [count, setCount] = useState<number>(4)

  const errors: string[] = []
  const he = hostError(host)
  if (he) errors.push(he)
  if (!Number.isInteger(start) || start < 1 || start > 65535) errors.push('Start port must be 1–65535')
  if (!Number.isInteger(count) || count < 1 || count > 64) errors.push('Count must be 1–64')
  else if (start + count - 1 > 65535) errors.push('The range runs past port 65535')
  const end = start + count - 1

  return (
    <Modal open={open} onOpenChange={onOpenChange} size="md">
      <ModalHeader className="p-6 pb-2">
        <ModalTitle>Add a port range</ModalTitle>
        <ModalDescription>
          For several processes on one machine, e.g. Node workers on ports 8050–8053.
        </ModalDescription>
      </ModalHeader>
      <ModalBody className="space-y-4 p-6">
        <div className="space-y-1.5">
          <Label htmlFor="range-host">Host</Label>
          <Input id="range-host" value={host} onChange={(e) => setHost(e.target.value)} placeholder="10.0.0.5" autoFocus />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <NumberField id="range-start" label="First port" value={start} min={1} max={65535} onChange={(v) => setStart(v as number)} />
          <NumberField id="range-count" label="How many" value={count} min={1} max={64} onChange={(v) => setCount(v as number)} />
        </div>
        {errors.length === 0 ? (
          <p className="rounded-lg bg-muted px-3 py-2 font-mono text-xs">
            {count === 1 ? `${host.trim()}:${start}` : `${host.trim()}:${start} … ${host.trim()}:${end}`}{' '}
            <span className="font-sans text-muted-foreground">
              ({count} server{count === 1 ? '' : 's'}; ports already listed are skipped)
            </span>
          </p>
        ) : (
          <ul className="space-y-1 text-sm text-destructive">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </ModalBody>
      <ModalFooter className="p-6 pt-2">
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button
          disabled={errors.length > 0}
          onClick={() => {
            onAdd(host.trim(), Array.from({ length: count }, (_, i) => start + i))
            onOpenChange(false)
          }}
        >
          Add {count} server{count === 1 ? '' : 's'}
        </Button>
      </ModalFooter>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Section
// ---------------------------------------------------------------------------

interface BackendsSectionProps {
  value: BackendsValue
  onChange: (value: BackendsValue) => void
  forwardScheme: 'http' | 'https'
  forwardHost: string
  forwardPort: number
  onForwardChange: (patch: { forward_scheme?: 'http' | 'https'; forward_host?: string; forward_port?: number }) => void
  websocketsSupport: boolean
  /** Saved host id: enables "Check now" and names the upstream in the preview. */
  hostId?: string
}

export function BackendsSection({
  value,
  onChange,
  forwardScheme,
  forwardHost,
  forwardPort,
  onForwardChange,
  websocketsSupport,
  hostId,
}: BackendsSectionProps) {
  const [serverDialog, setServerDialog] = useState<{ open: boolean; editing: ServerDraft | null; nonce: number }>({
    open: false,
    editing: null,
    nonce: 0,
  })
  const openServerDialog = (editing: ServerDraft | null) =>
    setServerDialog((d) => ({ open: true, editing, nonce: d.nonce + 1 }))
  const [range, setRange] = useState({ open: false, nonce: 0 })
  const [checking, setChecking] = useState(false)

  const set = (patch: Partial<BackendsValue>) => onChange({ ...value, ...patch })
  const method = LB_METHODS.find((m) => m.value === value.lb_method) ?? LB_METHODS[0]

  const addServers = (servers: ServerDraft[]) => {
    const existing = new Set(value.servers.map((s) => `${s.host.trim().toLowerCase()}:${s.port}`))
    const fresh = servers.filter((s) => !existing.has(`${s.host.trim().toLowerCase()}:${s.port}`))
    if (fresh.length < servers.length) {
      toastSuccess(fresh.length ? `Added ${fresh.length}; ${servers.length - fresh.length} already listed` : 'Those servers are already listed')
    }
    if (fresh.length) set({ servers: [...value.servers, ...fresh] })
  }

  const switchMode = (mode: 'single' | 'balanced') => {
    if (mode === value.mode) return
    if (mode === 'balanced' && value.servers.length === 0 && forwardHost.trim()) {
      // Start from the current backend so nothing changes until a server is added
      onChange({ ...value, mode, servers: [newServer(forwardHost.trim(), forwardPort)] })
      return
    }
    set({ mode })
  }

  const copyFromForward = () => {
    if (!forwardHost.trim()) {
      toastError('Set a forward host first')
      return
    }
    addServers([newServer(forwardHost.trim(), forwardPort)])
  }

  const checkNow = async () => {
    if (!hostId) return
    setChecking(true)
    try {
      const res = await api.post<UpstreamCheckResult[]>(`/api/proxy-hosts/${hostId}/upstreams/check`)
      const byId = new Map(res.data.map((r) => [r.id, r]))
      onChange({
        ...value,
        servers: value.servers.map((s) => {
          const r = s.id ? byId.get(s.id) : undefined
          return r
            ? { ...s, last_status: r.status, last_latency_ms: r.latency_ms, last_error: r.error, last_check_at: new Date().toISOString() }
            : s
        }),
      })
      const up = res.data.filter((r) => r.status === 'up').length
      toastSuccess(`${up} of ${res.data.length} server${res.data.length === 1 ? '' : 's'} answering`)
    } catch (err: any) {
      toastError(err.response?.data?.detail || 'Health check failed')
    } finally {
      setChecking(false)
    }
  }

  const errors = groupErrors(value)
  const saved = value.servers.filter((s) => s.id && s.enabled)
  const healthy = saved.filter((s) => s.last_status === 'up').length

  // Live preview from the API's own generator
  const previewBody = useMemo(
    () =>
      value.mode === 'balanced'
        ? JSON.stringify({
            host_id: hostId,
            forward_scheme: forwardScheme,
            websockets_support: websocketsSupport,
            ...lbSettingsPayload(value),
            servers: serversPayload(value),
          })
        : '',
    [value, hostId, forwardScheme, websocketsSupport]
  )
  const debouncedBody = useDebounced(previewBody, 350)
  const [preview, setPreview] = useState<UpstreamPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  // Field errors are shown inline; the API would only answer 422 for them.
  const previewable = value.servers.length > 0 && !value.servers.some((s) => serverFieldErrors(s).length > 0)
  useEffect(() => {
    if (!debouncedBody || !previewable) return
    let cancelled = false
    api
      .post<UpstreamPreview>('/api/proxy-hosts/upstream-preview', JSON.parse(debouncedBody))
      .then((res) => {
        if (!cancelled) {
          setPreview(res.data)
          setPreviewError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) setPreviewError(err.response?.data?.detail ? 'Preview unavailable: check the values above' : 'Preview unavailable')
      })
    return () => {
      cancelled = true
    }
  }, [debouncedBody, previewable])

  const previewText = preview && previewable ? [preview.upstream_block, preview.location_directives].filter(Boolean).join('\n\n') : ''

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium">Backends</p>
          <p className="text-xs text-muted-foreground">
            {value.mode === 'single'
              ? 'Every request goes to one upstream.'
              : 'Requests are spread across several upstream servers.'}
          </p>
        </div>
        <div className="flex w-full gap-1 overflow-x-auto rounded-lg bg-muted p-1 sm:w-fit" role="tablist">
          {(['single', 'balanced'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={value.mode === mode}
              onClick={() => switchMode(mode)}
              className={cn(
                'flex-1 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors sm:flex-none',
                value.mode === mode ? 'bg-background shadow-sm' : 'text-muted-foreground hover:bg-background/50'
              )}
            >
              {mode === 'single' ? 'Single backend' : 'Load balanced'}
            </button>
          ))}
        </div>
      </div>

      {value.mode === 'single' ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="fwd-scheme">Scheme</Label>
            <Select value={forwardScheme} onValueChange={(v) => onForwardChange({ forward_scheme: v as 'http' | 'https' })}>
              <SelectTrigger id="fwd-scheme">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="http">http</SelectItem>
                <SelectItem value="https">https</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fwd-host">Forward Host</Label>
            <Input
              id="fwd-host"
              value={forwardHost}
              onChange={(e) => onForwardChange({ forward_host: e.target.value })}
              placeholder="192.168.1.1"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fwd-port">Forward Port</Label>
            <Input
              id="fwd-port"
              type="number"
              min={1}
              max={65535}
              value={forwardPort}
              onChange={(e) => onForwardChange({ forward_port: parseInt(e.target.value) || 80 })}
              required
            />
          </div>
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-border p-4">
          {/* Method + scheme */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="lb-method">Balancing method</Label>
              <Select value={value.lb_method} onValueChange={(v) => set({ lb_method: v as LbMethod })}>
                <SelectTrigger id="lb-method">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LB_METHODS.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                      {m.value === 'least_conn' ? ' · recommended' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{method.hint}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lb-scheme">Scheme</Label>
              <Select value={forwardScheme} onValueChange={(v) => onForwardChange({ forward_scheme: v as 'http' | 'https' })}>
                <SelectTrigger id="lb-scheme">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="http">http</SelectItem>
                  <SelectItem value="https">https</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Used for every server.</p>
            </div>
          </div>

          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={() => openServerDialog(null)}>
              <Plus className="h-4 w-4" />
              Add server
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setRange((r) => ({ open: true, nonce: r.nonce + 1 }))}>
              <Rows3 className="h-4 w-4" />
              Add a port range
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={copyFromForward}>
              <Copy className="h-4 w-4" />
              Copy from forward host
            </Button>
            {hostId && saved.length > 0 && (
              <Button type="button" size="sm" variant="ghost" onClick={checkNow} disabled={checking} className="sm:ml-auto">
                {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
                Check now
              </Button>
            )}
          </div>

          {/* Servers */}
          {value.servers.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center">
              <Server className="mx-auto mb-2 h-8 w-8 text-muted-foreground opacity-60" />
              <p className="text-sm font-medium">No servers yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Add servers one by one, a whole port range at once, or start from the forward host.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Server</TableHead>
                    <TableHead className="text-right">Weight</TableHead>
                    <TableHead className="hidden text-right sm:table-cell">Max conns</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Health</TableHead>
                    <TableHead className="w-10">
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {value.servers.map((s) => {
                    const fieldErrors = serverFieldErrors(s)
                    return (
                      <TableRow key={s.key} className={cn(!s.enabled && 'opacity-60')}>
                        <TableCell className="font-mono text-xs sm:text-sm">
                          <button
                            type="button"
                            className="text-left hover:text-primary"
                            onClick={() => openServerDialog(s)}
                          >
                            {s.host.includes(':') ? `[${s.host}]` : s.host}:{s.port}
                          </button>
                          {fieldErrors.length > 0 && (
                            <p className="mt-1 font-sans text-xs text-destructive">{fieldErrors[0]}</p>
                          )}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{s.weight}</TableCell>
                        <TableCell className="hidden text-right tabular-nums text-muted-foreground sm:table-cell">
                          {s.max_conns ?? '∞'}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {!s.enabled ? (
                              <Badge variant="outline">Disabled</Badge>
                            ) : (
                              <>
                                {s.backup ? (
                                  <Badge variant="outline" className="border-brand-2/30 bg-brand-2/10 text-brand-2">
                                    Backup
                                  </Badge>
                                ) : (
                                  <Badge variant="outline">Primary</Badge>
                                )}
                                {s.down && (
                                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400">
                                    Maintenance
                                  </Badge>
                                )}
                                {s.auto_down && value.lb_auto_down && !s.down && (
                                  <Badge variant="outline" className="border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400">
                                    Auto-down
                                  </Badge>
                                )}
                              </>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <HealthDot server={s} />
                        </TableCell>
                        <TableCell>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button type="button" variant="ghost" size="icon" className="h-8 w-8" aria-label="Server actions">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48">
                              <DropdownMenuItem onClick={() => openServerDialog(s)}>
                                <Pencil className="h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => set({ servers: value.servers.map((x) => (x.key === s.key ? { ...x, down: !x.down } : x)) })}
                              >
                                <Wrench className="h-4 w-4" />
                                {s.down ? 'End maintenance' : 'Maintenance (down)'}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => set({ servers: value.servers.map((x) => (x.key === s.key ? { ...x, enabled: !x.enabled } : x)) })}
                              >
                                <Power className="h-4 w-4" />
                                {s.enabled ? 'Disable' : 'Enable'}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-red-500 focus:text-red-500"
                                onClick={() => set({ servers: value.servers.filter((x) => x.key !== s.key) })}
                              >
                                <Trash2 className="h-4 w-4" />
                                Remove
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {value.servers.length > 0 && hostId && saved.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {healthy} of {saved.length} saved server{saved.length === 1 ? '' : 's'} answering the last health check
              {value.health_check_type === 'http' ? ` (GET ${value.health_check_path || '/'})` : ' (TCP connect)'}.
            </p>
          )}

          {/* Problems */}
          {(errors.length > 0 || (previewable && (preview?.warnings.length ?? 0) > 0)) && (
            <div className="space-y-1.5">
              {errors.map((e) => (
                <p key={e} className="flex items-start gap-2 text-sm text-destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  {e}
                </p>
              ))}
              {errors.length === 0 &&
                preview?.warnings.map((w) => (
                  <p key={w} className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    {w}
                  </p>
                ))}
            </div>
          )}

          {/* Health checks and connection settings */}
          <div className="space-y-4 rounded-lg border border-border p-3">
            <p className="text-sm font-medium">Health checks &amp; connections</p>
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="hc-type">Check type</Label>
                  <Select value={value.health_check_type} onValueChange={(v) => set({ health_check_type: v as 'http' | 'tcp' })}>
                    <SelectTrigger id="hc-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="http">HTTP GET</SelectItem>
                      <SelectItem value="tcp">TCP connect</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="hc-path">Path</Label>
                  <Input
                    id="hc-path"
                    value={value.health_check_path}
                    disabled={value.health_check_type === 'tcp'}
                    onChange={(e) => set({ health_check_path: e.target.value })}
                    placeholder="/healthz"
                  />
                </div>
                <NumberField
                  id="hc-timeout"
                  label="Timeout (s)"
                  value={value.health_check_timeout}
                  min={1}
                  max={30}
                  onChange={(v) => set({ health_check_timeout: (v as number) || 5 })}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Every minute each enabled server is probed directly at its own host and port (redirects are not followed).
                HTTP counts any status below 500 as up.
              </p>
              <SwitchRow
                id="lb-autodown"
                label="Take failed servers out automatically"
                hint="Marks a server down in nginx after two failed checks and puts it back when it answers. Off by default: nginx already skips servers that fail real requests (max fails)."
                checked={value.lb_auto_down}
                onChange={(v) => set({ lb_auto_down: v })}
              />
              <NumberField
                id="lb-keepalive"
                label="Keepalive connections"
                value={value.upstream_keepalive}
                min={0}
                max={1024}
                onChange={(v) => set({ upstream_keepalive: Number.isNaN(v as number) ? 0 : (v as number) })}
                hint="Idle connections each nginx worker keeps open to the group, so requests skip the TCP handshake. 0 turns it off."
              />
            </div>
          </div>

          {/* Preview */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">Generated config</p>
              <span className="text-xs text-muted-foreground">
                {methodLabel(value.lb_method)} · {value.servers.filter((s) => s.enabled).length} enabled
              </span>
            </div>
            <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-muted p-3 font-mono text-xs leading-relaxed">
              {previewText || previewError || 'The upstream block appears here once the servers are valid.'}
            </pre>
            <p className="text-xs text-muted-foreground">
              Read-only: this is exactly what nginx gets. Saving runs <code>nginx -t</code> first and changes nothing if it fails.
            </p>
          </div>
        </div>
      )}

      <ServerDialog
        key={`server-${serverDialog.nonce}`}
        open={serverDialog.open}
        onOpenChange={(open) => setServerDialog((d) => ({ ...d, open }))}
        initial={serverDialog.editing}
        backupAllowed={method.backup}
        onSave={(server) => {
          if (serverDialog.editing) {
            const moved = server.host !== serverDialog.editing.host || server.port !== serverDialog.editing.port
            set({
              servers: value.servers.map((x) =>
                x.key === server.key ? (moved ? { ...server, last_status: 'unknown', last_latency_ms: null, last_error: null } : server) : x
              ),
            })
          } else {
            addServers([server])
          }
        }}
      />
      <PortRangeDialog
        key={`range-${range.nonce}`}
        open={range.open}
        onOpenChange={(open) => setRange((r) => ({ ...r, open }))}
        defaultHost={value.servers[0]?.host || forwardHost}
        onAdd={(host, ports) => addServers(ports.map((p) => newServer(host, p)))}
      />
    </div>
  )
}

/** "Load balanced · 4 backends · 3 healthy" for the host list. */
export function LoadBalancedBadge({ host }: { host: ProxyHost }) {
  const servers = (host.upstream_servers ?? []).filter((s) => s.enabled)
  if (servers.length === 0) return null
  const checked = servers.filter((s) => s.last_status && s.last_status !== 'unknown')
  const healthy = servers.filter((s) => s.last_status === 'up').length
  const tone =
    checked.length === 0
      ? 'border-border bg-muted text-muted-foreground'
      : healthy === servers.length
        ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400'
        : healthy === 0
          ? 'border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400'
          : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400'
  return (
    <Badge
      variant="outline"
      className={cn('gap-1 font-medium', tone)}
      title={`${methodLabel(host.lb_method ?? 'round_robin')}: ${servers
        .map((s) => `${s.host}:${s.port} ${s.last_status ?? 'unknown'}`)
        .join(', ')}`}
    >
      Load balanced · {servers.length} backend{servers.length === 1 ? '' : 's'} ·{' '}
      {checked.length === 0 ? 'not checked yet' : `${healthy} healthy`}
    </Badge>
  )
}
