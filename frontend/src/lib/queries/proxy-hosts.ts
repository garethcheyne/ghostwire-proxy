'use client'

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import type { ProxyHost } from '@/types'
import { proxyHostKeys, type ListParams } from './keys'

export interface ProxyHostListResult {
  items: ProxyHost[]
  total: number
}

async function fetchProxyHosts(params: ListParams): Promise<ProxyHostListResult> {
  const response = await api.get<ProxyHost[]>('/api/proxy-hosts', { params })
  const total = Number(response.headers['x-total-count'] ?? response.data.length)
  return { items: response.data, total }
}

export function useProxyHosts(params: ListParams = {}) {
  return useQuery({
    queryKey: proxyHostKeys.list(params),
    queryFn: () => fetchProxyHosts(params),
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  })
}

export function useProxyHost(id: string | undefined) {
  return useQuery({
    queryKey: id ? proxyHostKeys.detail(id) : ['proxy-hosts', 'detail', 'none'],
    queryFn: async () => {
      const response = await api.get<ProxyHost>(`/api/proxy-hosts/${id}`)
      return response.data
    },
    enabled: Boolean(id),
    staleTime: 15_000,
  })
}

export function useCreateProxyHost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<ProxyHost>) => {
      const response = await api.post<ProxyHost>('/api/proxy-hosts', payload)
      return response.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: proxyHostKeys.all })
      toastSuccess('Proxy host created')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toastError(error.response?.data?.detail || 'Failed to create proxy host')
    },
  })
}

export function useUpdateProxyHost(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<ProxyHost>) => {
      const response = await api.put<ProxyHost>(`/api/proxy-hosts/${id}`, payload)
      return response.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: proxyHostKeys.all })
      toastSuccess('Proxy host updated')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toastError(error.response?.data?.detail || 'Failed to update proxy host')
    },
  })
}

export function useDeleteProxyHost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/proxy-hosts/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: proxyHostKeys.all })
      toastSuccess('Proxy host deleted')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toastError(error.response?.data?.detail || 'Failed to delete proxy host')
    },
  })
}
