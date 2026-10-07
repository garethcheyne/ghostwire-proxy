'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Bookmark, FilterX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useProxyHosts } from '@/lib/queries/proxy-hosts'
import {
  EMPTY_FILTERS,
  activeFilterCount,
  useTrafficBackends,
  useTrafficTop,
  type RangePreset,
  type TrafficFilters,
} from '@/lib/queries/traffic'
import { MultiSelect, type MultiOption } from './multi-select'

const RANGES: { value: RangePreset; label: string }[] = [
  { value: '15m', label: 'Last 15 minutes' },
  { value: '1h', label: 'Last hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'custom', label: 'Custom range' },
]

const STATUS_CLASSES: MultiOption[] = [
  { value: '2', label: '2xx Success' },
  { value: '3', label: '3xx Redirect' },
  { value: '4', label: '4xx Client error' },
  { value: '5', label: '5xx Server error' },
]

const COMMON_CODES = ['200', '201', '204', '301', '302', '304', '400', '401', '403', '404', '429', '444', '499', '500', '502', '503', '504']
const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']

/** Saved quick views: a filter set on top of a time range. */
export const QUICK_VIEWS: { label: string; filters: Partial<TrafficFilters> }[] = [
  { label: 'Errors in the last hour', filters: { range: '1h', statusClass: ['5'] } },
  { label: 'Client errors today', filters: { range: '24h', statusClass: ['4'] } },
  { label: 'Slow requests (> 1 s)', filters: { range: '24h', minRt: '1000' } },
  { label: 'Blocked / denied', filters: { range: '24h', status: ['401', '403', '429', '444'] } },
  { label: 'Bots', filters: { range: '24h', bot: 'bot' } },
]

interface TrafficFiltersBarProps {
  filters: TrafficFilters
  onChange: (next: TrafficFilters) => void
  /** Filters the drill-down fixes (hidden from the bar). */
  locked?: Partial<Record<'host' | 'backend' | 'clientIp', boolean>>
}

export function TrafficFiltersBar({ filters, onChange, locked = {} }: TrafficFiltersBarProps) {
  const set = (patch: Partial<TrafficFilters>) => onChange({ ...filters, ...patch })
  const { data: hostsData } = useProxyHosts({ limit: 100 })
  // Option lists come from the data in the current time window only, so they
  // stay short and cheap (rollup-backed).
  const rangeOnly = useMemo<TrafficFilters>(
    () => ({ ...EMPTY_FILTERS, range: filters.range, start: filters.start, end: filters.end }),
    [filters.range, filters.start, filters.end]
  )
  const { data: backends } = useTrafficBackends(rangeOnly, 'hostport', !locked.backend)
  const { data: countries } = useTrafficTop(rangeOnly, 'country', 50)

  const hostOptions: MultiOption[] = (hostsData?.items ?? []).map((h) => ({
    value: h.id,
    label: h.domain_names[0] ?? h.id,
  }))
  const backendOptions = useMemo<MultiOption[]>(() => {
    const out: MultiOption[] = []
    const machines = new Map<string, number>()
    for (const b of backends ?? []) {
      if (!b.backend) continue
      const host = b.backend.replace(/:\d+$/, '')
      machines.set(host, (machines.get(host) ?? 0) + b.requests)
    }
    // A machine entry (every port), then its individual ports.
    for (const [host, n] of [...machines.entries()].sort((a, b) => b[1] - a[1])) {
      const label = (backends ?? []).find((b) => b.backend.startsWith(host) && b.label)?.label
      out.push({ value: host, label: label ? `${host} · ${label}` : `${host} (all ports)`, hint: n.toLocaleString() })
      for (const b of backends ?? []) {
        if (b.backend.replace(/:\d+$/, '') === host && b.backend !== host) {
          out.push({ value: b.backend, label: `  ${b.backend}`, hint: b.requests.toLocaleString() })
        }
      }
    }
    return out
  }, [backends])
  const countryOptions: MultiOption[] = (countries ?? [])
    .filter((c) => c.value)
    .map((c) => ({ value: c.value, label: c.label ? `${c.value} · ${c.label}` : c.value, hint: c.requests.toLocaleString() }))

  const count = activeFilterCount(filters)

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={filters.range} onValueChange={(v) => set({ range: v as RangePreset })}>
          <SelectTrigger className="h-9 w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGES.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {filters.range === 'custom' && (
          <>
            <Input
              type="datetime-local"
              className="h-9 w-[200px]"
              aria-label="From"
              value={toLocalInput(filters.start)}
              onChange={(e) => set({ start: fromLocalInput(e.target.value) })}
            />
            <span className="text-sm text-muted-foreground">to</span>
            <Input
              type="datetime-local"
              className="h-9 w-[200px]"
              aria-label="To"
              value={toLocalInput(filters.end)}
              onChange={(e) => set({ end: fromLocalInput(e.target.value) })}
            />
          </>
        )}
        <div className="ml-auto flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-9">
                <Bookmark className="h-4 w-4" />
                Quick views
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Quick views</DropdownMenuLabel>
              {QUICK_VIEWS.map((v) => (
                <DropdownMenuItem
                  key={v.label}
                  onSelect={() =>
                    onChange({
                      ...EMPTY_FILTERS,
                      // Keep what the drill-down pins.
                      host: locked.host ? filters.host : [],
                      backend: locked.backend ? filters.backend : [],
                      clientIp: locked.clientIp ? filters.clientIp : undefined,
                      ...v.filters,
                    })
                  }
                >
                  {v.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="sm"
            className="h-9"
            disabled={count === 0}
            onClick={() =>
              onChange({
                ...EMPTY_FILTERS,
                range: filters.range,
                start: filters.start,
                end: filters.end,
                host: locked.host ? filters.host : [],
                backend: locked.backend ? filters.backend : [],
                clientIp: locked.clientIp ? filters.clientIp : undefined,
              })
            }
          >
            <FilterX className="h-4 w-4" />
            Clear{count ? ` (${count})` : ''}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {!locked.host && (
          <MultiSelect label="Host" options={hostOptions} selected={filters.host} onChange={(host) => set({ host })} />
        )}
        {!locked.backend && (
          <MultiSelect
            label="Backend / node"
            options={backendOptions}
            selected={filters.backend}
            onChange={(backend) => set({ backend })}
            placeholder="IP or IP:port…"
            allowCustom={(v) => /^[\w.:[\]-]+$/.test(v)}
          />
        )}
        <MultiSelect
          label="Status"
          options={STATUS_CLASSES}
          selected={filters.statusClass}
          onChange={(statusClass) => set({ statusClass })}
        />
        <MultiSelect
          label="Code"
          options={COMMON_CODES.map((c) => ({ value: c, label: c }))}
          selected={filters.status}
          onChange={(status) => set({ status })}
          placeholder="Status code…"
          allowCustom={(v) => /^[1-5]\d\d$/.test(v)}
        />
        <MultiSelect
          label="Method"
          options={METHODS.map((m) => ({ value: m, label: m }))}
          selected={filters.method}
          onChange={(method) => set({ method })}
        />
        <MultiSelect
          label="Country"
          options={countryOptions}
          selected={filters.country}
          onChange={(country) => set({ country })}
          allowCustom={(v) => /^[A-Za-z]{2}$/.test(v)}
        />
        <Select
          value={filters.bot ?? 'all'}
          onValueChange={(v) => set({ bot: v === 'all' ? undefined : (v as 'bot' | 'human') })}
        >
          <SelectTrigger className="h-9 w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Bots and humans</SelectItem>
            <SelectItem value="human">Humans only</SelectItem>
            <SelectItem value="bot">Bots only</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex gap-2">
          <Select value={filters.pathMode} onValueChange={(v) => set({ pathMode: v as 'contains' | 'prefix' })}>
            <SelectTrigger className="h-9 w-[120px] shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="contains">Path has</SelectItem>
              <SelectItem value="prefix">Path starts</SelectItem>
            </SelectContent>
          </Select>
          <DebouncedInput
            value={filters.path ?? ''}
            onCommit={(v) => set({ path: v || undefined })}
            placeholder="/api/…"
          />
        </div>
        {!locked.clientIp && (
          <DebouncedInput
            value={filters.clientIp ?? ''}
            onCommit={(v) => set({ clientIp: v || undefined })}
            placeholder="Client IP or CIDR (203.0.113.0/24)"
          />
        )}
        <DebouncedInput
          value={filters.ua ?? ''}
          onCommit={(v) => set({ ua: v || undefined })}
          placeholder="User agent contains…"
        />
        <DebouncedInput
          value={filters.minRt ?? ''}
          onCommit={(v) => set({ minRt: /^\d+$/.test(v) ? v : undefined })}
          placeholder="Slower than (ms)"
          inputMode="numeric"
        />
      </div>
    </div>
  )
}

function DebouncedInput({
  value,
  onCommit,
  placeholder,
  inputMode,
}: {
  value: string
  onCommit: (value: string) => void
  placeholder?: string
  inputMode?: 'numeric'
}) {
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)
  // Follow outside changes (Clear, quick views, back/forward).
  if (value !== lastValue) {
    setLastValue(value)
    setDraft(value)
  }
  const commit = useRef(onCommit)
  useEffect(() => {
    commit.current = onCommit
  })
  useEffect(() => {
    if (draft === value) return
    const t = setTimeout(() => commit.current(draft.trim()), 400)
    return () => clearTimeout(t)
  }, [draft, value])
  return (
    <Input
      className="h-9"
      value={draft}
      placeholder={placeholder}
      inputMode={inputMode}
      onChange={(e) => setDraft(e.target.value)}
    />
  )
}

function toLocalInput(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromLocalInput(v: string): string | undefined {
  if (!v) return undefined
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}
