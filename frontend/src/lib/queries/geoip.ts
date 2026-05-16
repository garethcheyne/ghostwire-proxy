'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { geoipKeys } from './keys'

export function useGeoipRules(proxyHostId?: string | null) {
  return useQuery({
    queryKey: geoipKeys.rules(proxyHostId),
    queryFn: async () => {
      const params = proxyHostId ? { proxy_host_id: proxyHostId } : undefined
      const response = await api.get('/api/geoip/rules', { params })
      return response.data
    },
    staleTime: 30_000,
  })
}

export function useGeoipSettings() {
  return useQuery({
    queryKey: geoipKeys.settings(),
    queryFn: async () => {
      const response = await api.get('/api/geoip/settings')
      return response.data
    },
    staleTime: 60_000,
  })
}
