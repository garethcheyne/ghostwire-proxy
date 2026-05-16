'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { wafKeys } from './keys'

export interface WafRule {
  id: string
  name: string
  category: string
  enabled: boolean
  proxy_host_id?: string | null
  pattern?: string
  action?: string
  severity?: string
  description?: string | null
  created_at?: string
  updated_at?: string
}

export interface WafEvent {
  id: string
  timestamp: string
  client_ip: string
  category: string
  severity: string
  rule_id?: string | null
  proxy_host_id?: string | null
  host?: string
  uri?: string
  method?: string
  payload?: string | null
}

export function useWafRules(params: { category?: string; enabled?: boolean; proxy_host_id?: string } = {}) {
  return useQuery({
    queryKey: wafKeys.rules(),
    queryFn: async () => {
      const response = await api.get<WafRule[]>('/api/waf/rules', { params })
      return response.data
    },
    staleTime: 30_000,
  })
}

export function useWafEvents(params: { category?: string; severity?: string; client_ip?: string; skip?: number; limit?: number } = {}) {
  return useQuery({
    queryKey: wafKeys.events(params),
    queryFn: async () => {
      const response = await api.get<WafEvent[]>('/api/waf/events', { params })
      return response.data
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}
