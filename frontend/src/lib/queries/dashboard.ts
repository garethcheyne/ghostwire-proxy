'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Certificate, TrafficStats } from '@/types'
import {
  certificateKeys,
  trafficKeys,
  wafKeys,
  analyticsKeys,
  type ListParams,
} from './keys'

export interface CertificateListResult {
  items: Certificate[]
  total: number
}

export function useCertificates(params: ListParams = {}) {
  return useQuery({
    queryKey: certificateKeys.list(params),
    queryFn: async (): Promise<CertificateListResult> => {
      const response = await api.get<Certificate[]>('/api/certificates', { params })
      const total = Number(response.headers['x-total-count'] ?? response.data.length)
      return { items: response.data, total }
    },
    staleTime: 30_000,
  })
}

export function useTrafficStats() {
  return useQuery({
    queryKey: trafficKeys.stats(),
    queryFn: async () => {
      const response = await api.get<TrafficStats>('/api/traffic/stats')
      return response.data
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

export interface ThreatStats {
  total_events: number
  events_today: number
  events_this_week: number
  total_actors: number
  blocked_actors: number
  top_categories: { category: string; count: number }[]
  top_actors: { ip: string; score: number; events: number; status: string }[]
  severity_breakdown: Record<string, number>
}

export function useWafStats() {
  return useQuery({
    queryKey: wafKeys.stats(),
    queryFn: async () => {
      const response = await api.get<ThreatStats>('/api/waf/stats')
      return response.data
    },
    staleTime: 30_000,
    // Best-effort enrichment — don't retry hard
    retry: 1,
  })
}

export interface AuthErrors {
  summary: {
    total_401: number
    total_403: number
    failed_logins: number
  }
  recent_events: Array<{
    timestamp: string
    ip: string
    status: number
    method: string
    uri: string
    host: string
    country: string | null
  }>
  top_offenders: Array<{ ip: string; count: number; last_seen: string }>
  top_hosts: Array<{ host: string; count: number }>
  failed_logins: Array<{
    timestamp: string
    email: string
    type: string
    ip: string
    details: string | null
  }>
}

export function useAuthErrors(period: string = '24h') {
  return useQuery({
    queryKey: analyticsKeys.authErrors(period),
    queryFn: async () => {
      const response = await api.get<AuthErrors>(
        `/api/analytics/auth-errors?period=${encodeURIComponent(period)}`
      )
      return response.data
    },
    staleTime: 60_000,
    retry: 1,
  })
}
