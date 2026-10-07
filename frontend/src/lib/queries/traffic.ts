'use client'

import { useQuery, keepPreviousData } from '@tanstack/react-query'
import api from '@/lib/api'
import type { TrafficLog } from '@/types'
import { trafficKeys } from './keys'

// ─── Filters (mirror the API's query parameters; also the page's URL) ──────

export type RangePreset = '15m' | '1h' | '6h' | '24h' | '7d' | '30d' | 'custom'

export interface TrafficFilters {
  range: RangePreset
  start?: string // ISO, when range = custom
  end?: string
  host: string[] // proxy host ids
  backend: string[] // "10.0.0.5" (every port) or "10.0.0.5:8080"
  statusClass: string[] // "2".."5"
  status: string[] // exact codes
  method: string[]
  path?: string
  pathMode: 'contains' | 'prefix'
  clientIp?: string // address or CIDR
  country: string[]
  ua?: string
  bot?: 'bot' | 'human'
  minRt?: string // ms
}

export const EMPTY_FILTERS: TrafficFilters = {
  range: '24h',
  host: [],
  backend: [],
  statusClass: [],
  status: [],
  method: [],
  pathMode: 'contains',
  country: [],
}

const LIST_KEYS = ['host', 'backend', 'statusClass', 'status', 'method', 'country'] as const
const URL_NAMES: Record<string, string> = { statusClass: 'status_class' }

/** Filters → API/URL query parameters (only the ones set). */
export function filtersToParams(f: TrafficFilters): URLSearchParams {
  const p = new URLSearchParams()
  if (f.range === 'custom') {
    if (f.start) p.set('start', f.start)
    if (f.end) p.set('end', f.end)
    if (!f.start && !f.end) p.set('range', '24h')
  } else {
    p.set('range', f.range)
  }
  for (const k of LIST_KEYS) {
    for (const v of f[k]) p.append(URL_NAMES[k] ?? k, v)
  }
  if (f.path) {
    p.set('path', f.path)
    if (f.pathMode !== 'contains') p.set('path_mode', f.pathMode)
  }
  if (f.clientIp) p.set('client_ip', f.clientIp)
  if (f.ua) p.set('ua', f.ua)
  if (f.bot) p.set('bot', f.bot === 'bot' ? 'true' : 'false')
  if (f.minRt) p.set('min_rt', f.minRt)
  return p
}

/** URL query → filters (unknown values are dropped, not trusted). */
export function parseFilters(sp: URLSearchParams): TrafficFilters {
  const presets: RangePreset[] = ['15m', '1h', '6h', '24h', '7d', '30d']
  const range = sp.get('range') as RangePreset | null
  const start = sp.get('start') ?? undefined
  const end = sp.get('end') ?? undefined
  const bot = sp.get('bot')
  const minRt = sp.get('min_rt')
  return {
    range: start || end ? 'custom' : range && presets.includes(range) ? range : '24h',
    start,
    end,
    host: sp.getAll('host'),
    backend: sp.getAll('backend'),
    statusClass: sp.getAll('status_class').filter((v) => /^[1-5]$/.test(v)),
    status: sp.getAll('status').filter((v) => /^\d{3}$/.test(v)),
    method: sp.getAll('method'),
    path: sp.get('path') ?? undefined,
    pathMode: sp.get('path_mode') === 'prefix' ? 'prefix' : 'contains',
    clientIp: sp.get('client_ip') ?? undefined,
    country: sp.getAll('country'),
    ua: sp.get('ua') ?? undefined,
    bot: bot === 'true' ? 'bot' : bot === 'false' ? 'human' : undefined,
    minRt: minRt && /^\d+$/.test(minRt) ? minRt : undefined,
  }
}

export function activeFilterCount(f: TrafficFilters): number {
  return (
    LIST_KEYS.reduce((n, k) => n + (f[k].length ? 1 : 0), 0) +
    [f.path, f.clientIp, f.ua, f.bot, f.minRt].filter(Boolean).length
  )
}

/** Stable cache key for a filter set. */
function key(f: TrafficFilters): string {
  return filtersToParams(f).toString()
}

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Latency {
  avg: number | null
  p50: number | null
  p95: number | null
  p99?: number | null
}

export interface TrafficPoint extends Latency {
  t: string
  requests: number
  bytes_sent: number
  bytes_received: number
  s1xx: number
  s2xx: number
  s3xx: number
  s4xx: number
  s5xx: number
}

export interface TrafficOverview {
  range: { start: string | null; end: string | null; stride_seconds: number }
  rolled_until: string | null
  totals: {
    requests: number
    bot_requests: number
    bytes_sent: number
    bytes_received: number
    errors_4xx: number
    errors_5xx: number
    error_rate: number
    server_error_rate: number
    latency: Latency
    last_seen: string | null
  }
  status_codes: { status: number; requests: number }[]
  timeseries: TrafficPoint[]
}

export interface TopItem {
  value: string
  label?: string | null
  known_label?: string | null
  requests: number
  errors_4xx?: number
  errors_5xx?: number
  avg_response_time?: number | null
  bytes_sent?: number
  last_seen?: string | null
}

export type TopDimension =
  | 'path'
  | 'client_ip'
  | 'country'
  | 'user_agent'
  | 'referer'
  | 'method'
  | 'status'
  | 'proxy_host'
  | 'backend'
  | 'backend_host'

export interface BackendHealth {
  port: number
  status: string | null
  checked_at: string | null
  latency_ms: number | null
  error: string | null
  enabled: boolean
  down: boolean
  backup: boolean
  host_name: string | null
}

export interface BackendMeta {
  label: string | null
  configured_for: { id: string; name: string; port: number; via: 'forward_host' | 'upstream' }[]
  health: BackendHealth[]
}

export interface BackendRow extends BackendMeta {
  backend: string
  requests: number
  errors_4xx: number
  errors_5xx: number
  error_rate: number
  server_error_rate: number
  p50: number | null
  p95: number | null
  avg: number | null
  bytes_sent: number
  bytes_received: number
  last_seen: string | null
  hosts: { id: string; name: string; requests: number }[]
}

export interface NodeRow {
  node: string
  label: string | null
  requests: number
  share: number
  errors_4xx: number
  errors_5xx: number
  error_rate: number
  server_error_rate: number
  p50: number | null
  p95: number | null
  avg: number | null
  bytes_sent: number
  bytes_received: number
  failovers_in: number
  failovers_out: number
  last_seen: string | null
  health: BackendHealth[]
}

export interface NodesSummary {
  total_requests: number
  nodes: NodeRow[]
  series_nodes: string[]
  stride_seconds: number
  timeseries: { t: string; values: Record<string, number> }[]
  failovers: { total: number; pairs: { from: string; to: string; requests: number }[] }
}

export interface Attempt {
  node: string
  status: number | null
  time_ms: number | null
  final: boolean
}

export interface TrafficLogDetail extends TrafficLog {
  is_bot: boolean | null
  is_streaming: boolean | null
  request_headers: Record<string, string> | null
  client: {
    known_label: string | null
    isp: string | null
    org: string | null
    asn: string | null
    reverse_dns: string | null
    region: string | null
  }
  backend: ({ host: string } & BackendMeta) | null
  attempts: Attempt[]
  security_events: {
    id: string
    timestamp: string
    category: string | null
    rule_name: string | null
    rule_id: string | null
    severity: string | null
    action_taken: string | null
    request_uri: string | null
    matched_payload: string | null
  }[]
}

export interface ClientInfo {
  ip: string
  known: { label: string; category: string | null; trusted: boolean } | null
  enrichment: Record<string, string | number | boolean | null> | null
  threat: { status: string; score: number; events: number; last_seen: string | null } | null
}

// ─── Hooks ──────────────────────────────────────────────────────────────────

// Summaries are cached ~20s by the API; matching it here means flipping between
// tabs and panels doesn't refetch.
const STALE = 20_000

export interface TrafficLogsResult {
  items: TrafficLog[]
  total: number
  /** The API stopped counting (a filter it can't count from its summaries). */
  capped: boolean
}

async function fetchRequests(params: URLSearchParams): Promise<TrafficLogsResult> {
  const response = await api.get<TrafficLog[]>('/api/traffic', { params })
  const total = Number(response.headers['x-total-count'] ?? response.data.length)
  return { items: response.data, total, capped: response.headers['x-total-count-capped'] === 'true' }
}

/** One page of matching requests, newest first. */
export function useTrafficRequests(f: TrafficFilters, page: number, limit = 50) {
  return useQuery({
    queryKey: trafficKeys.logs({ q: key(f), page, limit }),
    queryFn: () => {
      const params = filtersToParams(f)
      params.set('skip', String((page - 1) * limit))
      params.set('limit', String(limit))
      return fetchRequests(params)
    },
    staleTime: STALE,
    placeholderData: keepPreviousData,
  })
}

export function useTrafficOverview(f: TrafficFilters) {
  return useQuery({
    queryKey: trafficKeys.overview(key(f)),
    queryFn: async () =>
      (await api.get<TrafficOverview>('/api/traffic/overview', { params: filtersToParams(f) })).data,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  })
}

export function useTrafficTop(f: TrafficFilters, dimension: TopDimension, limit = 10, enabled = true) {
  return useQuery({
    queryKey: trafficKeys.top(key(f), dimension, limit),
    queryFn: async () => {
      const params = filtersToParams(f)
      params.set('dimension', dimension)
      params.set('limit', String(limit))
      return (await api.get<TopItem[]>('/api/traffic/top', { params })).data
    },
    staleTime: STALE,
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useTrafficBackends(f: TrafficFilters, group: 'host' | 'hostport', enabled = true) {
  return useQuery({
    queryKey: trafficKeys.backends(key(f), group),
    queryFn: async () => {
      const params = filtersToParams(f)
      params.set('group', group)
      return (await api.get<BackendRow[]>('/api/traffic/backends', { params })).data
    },
    staleTime: STALE,
    placeholderData: keepPreviousData,
    enabled,
  })
}

/** Traffic split across upstream nodes (load-balanced host or one machine). */
export function useTrafficNodes(f: TrafficFilters, enabled = true) {
  return useQuery({
    queryKey: trafficKeys.nodes(key(f)),
    queryFn: async () => (await api.get<NodesSummary>('/api/traffic/nodes', { params: filtersToParams(f) })).data,
    staleTime: STALE,
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useBackendInfo(backend: string | undefined) {
  return useQuery({
    queryKey: trafficKeys.backendInfo(backend ?? ''),
    queryFn: async () =>
      (await api.get<{ backend: string } & BackendMeta>('/api/traffic/backend-info', { params: { backend } }))
        .data,
    enabled: Boolean(backend),
    staleTime: 30_000,
  })
}

export function useClientInfo(ip: string | undefined) {
  return useQuery({
    queryKey: trafficKeys.clientInfo(ip ?? ''),
    queryFn: async () => (await api.get<ClientInfo>('/api/traffic/client-info', { params: { ip } })).data,
    enabled: Boolean(ip),
    staleTime: 60_000,
  })
}

export function useTrafficLogDetail(id: string | undefined) {
  return useQuery({
    queryKey: trafficKeys.detail(id ?? ''),
    queryFn: async () => (await api.get<TrafficLogDetail>(`/api/traffic/${id}`)).data,
    enabled: Boolean(id),
    staleTime: 5 * 60_000,
  })
}

// ─── Older list hook (Analytics › Logs tab) ─────────────────────────────────

export interface TrafficLogParams {
  page: number
  limit: number
  proxyHostId?: string
  /** Status class base: 200, 300, 400 or 500. Expanded to a min/max range. */
  statusClass?: string
  /** Free text over request URI, client IP and user agent. */
  search?: string
}

export function useTrafficLogs(params: TrafficLogParams) {
  return useQuery({
    queryKey: trafficKeys.logs({ ...params }),
    queryFn: () => {
      const query = new URLSearchParams({
        skip: String((params.page - 1) * params.limit),
        limit: String(params.limit),
      })
      if (params.proxyHostId) query.set('proxy_host_id', params.proxyHostId)
      if (params.search) query.set('search', params.search)
      // The filter offers whole status classes ("4xx"); the API takes a range.
      if (params.statusClass) {
        const base = Number(params.statusClass)
        if (!Number.isNaN(base)) {
          query.set('status_min', String(base))
          query.set('status_max', String(base + 99))
        }
      }
      return fetchRequests(query)
    },
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  })
}
