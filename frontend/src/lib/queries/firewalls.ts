'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { firewallKeys } from './keys'

export function useFirewalls() {
  return useQuery({
    queryKey: firewallKeys.list(),
    queryFn: async () => {
      const response = await api.get('/api/firewalls/')
      return response.data
    },
    staleTime: 30_000,
  })
}

export function useFirewallStatus() {
  return useQuery({
    queryKey: firewallKeys.status(),
    queryFn: async () => {
      const response = await api.get('/api/firewalls/status')
      return response.data
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}
