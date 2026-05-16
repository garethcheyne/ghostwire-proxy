'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { honeypotKeys } from './keys'

export function useHoneypotTraps(params: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: honeypotKeys.traps(params),
    queryFn: async () => {
      const response = await api.get('/api/honeypot/traps', { params })
      return response.data
    },
    staleTime: 30_000,
  })
}

export function useHoneypotHits(params: { skip?: number; limit?: number } = {}) {
  return useQuery({
    queryKey: honeypotKeys.hits(params),
    queryFn: async () => {
      const response = await api.get('/api/honeypot/hits', { params })
      return response.data
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}

export function useHoneypotStats() {
  return useQuery({
    queryKey: honeypotKeys.stats(),
    queryFn: async () => {
      const response = await api.get('/api/honeypot/stats')
      return response.data
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}
