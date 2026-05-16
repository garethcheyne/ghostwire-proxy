/**
 * Centralised React Query key factories.
 *
 * Why: stable, hierarchical keys make targeted invalidation predictable
 * (e.g. `queryClient.invalidateQueries({ queryKey: proxyHostKeys.all })`
 * wipes every proxy-host query regardless of its filter params).
 */

export type ListParams = {
  skip?: number
  limit?: number
  enabled?: boolean | null
  search?: string | null
}

export const proxyHostKeys = {
  all: ['proxy-hosts'] as const,
  lists: () => [...proxyHostKeys.all, 'list'] as const,
  list: (params: ListParams = {}) => [...proxyHostKeys.lists(), params] as const,
  detail: (id: string) => [...proxyHostKeys.all, 'detail', id] as const,
}

export const certificateKeys = {
  all: ['certificates'] as const,
  lists: () => [...certificateKeys.all, 'list'] as const,
  list: (params: ListParams = {}) => [...certificateKeys.lists(), params] as const,
  detail: (id: string) => [...certificateKeys.all, 'detail', id] as const,
}

export const accessListKeys = {
  all: ['access-lists'] as const,
  lists: () => [...accessListKeys.all, 'list'] as const,
  list: (params: ListParams = {}) => [...accessListKeys.lists(), params] as const,
  detail: (id: string) => [...accessListKeys.all, 'detail', id] as const,
}

export const trafficKeys = {
  all: ['traffic'] as const,
  stats: () => [...trafficKeys.all, 'stats'] as const,
}

export const wafKeys = {
  all: ['waf'] as const,
  stats: () => [...wafKeys.all, 'stats'] as const,
  rules: () => [...wafKeys.all, 'rules'] as const,
  events: (params: Record<string, unknown> = {}) =>
    [...wafKeys.all, 'events', params] as const,
}

export const analyticsKeys = {
  all: ['analytics'] as const,
  authErrors: (period: string) => [...analyticsKeys.all, 'auth-errors', period] as const,
}

export const firewallKeys = {
  all: ['firewalls'] as const,
  list: () => [...firewallKeys.all, 'list'] as const,
  status: () => [...firewallKeys.all, 'status'] as const,
}

export const geoipKeys = {
  all: ['geoip'] as const,
  rules: (proxyHostId?: string | null) =>
    [...geoipKeys.all, 'rules', proxyHostId ?? null] as const,
  settings: () => [...geoipKeys.all, 'settings'] as const,
}

export const honeypotKeys = {
  all: ['honeypot'] as const,
  traps: (params: Record<string, unknown> = {}) => [...honeypotKeys.all, 'traps', params] as const,
  hits: (params: Record<string, unknown> = {}) => [...honeypotKeys.all, 'hits', params] as const,
  stats: () => [...honeypotKeys.all, 'stats'] as const,
}

export const rateLimitKeys = {
  all: ['rate-limits'] as const,
  list: (proxyHostId?: string | null) =>
    [...rateLimitKeys.all, 'list', proxyHostId ?? null] as const,
}

export const dnsKeys = {
  all: ['dns'] as const,
  providers: () => [...dnsKeys.all, 'providers'] as const,
}

export const authWallKeys = {
  all: ['auth-walls'] as const,
  list: (params: ListParams = {}) => [...authWallKeys.all, 'list', params] as const,
  detail: (id: string) => [...authWallKeys.all, 'detail', id] as const,
}
