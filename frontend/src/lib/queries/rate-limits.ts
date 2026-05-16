'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { rateLimitKeys } from './keys'

export function useRateLimits(proxyHostId?: string | null) {
  return useQuery({
    queryKey: rateLimitKeys.list(proxyHostId),
    queryFn: async () => {
      const params = proxyHostId ? { proxy_host_id: proxyHostId } : undefined
      const response = await api.get('/api/rate-limits', { params })
      return response.data
    },
    staleTime: 30_000,
  })
}
