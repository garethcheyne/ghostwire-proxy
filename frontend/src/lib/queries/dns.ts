'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { dnsKeys } from './keys'

export function useDnsProviders() {
  return useQuery({
    queryKey: dnsKeys.providers(),
    queryFn: async () => {
      const response = await api.get('/api/dns/providers')
      return response.data
    },
    staleTime: 60_000,
  })
}
