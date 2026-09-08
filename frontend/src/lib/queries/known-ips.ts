'use client'

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'

import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import { knownIpKeys } from './keys'

export interface KnownIp {
  id: string
  ip_address: string
  label: string
  category: string | null
  group_name: string | null
  notes: string | null
  trusted: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface KnownIpListResult {
  items: KnownIp[]
  total: number
}

export function useKnownIps(params: { skip?: number; limit?: number; search?: string; category?: string; group_name?: string } = {}) {
  return useQuery({
    queryKey: knownIpKeys.list(params),
    queryFn: async (): Promise<KnownIpListResult> => {
      const response = await api.get<KnownIp[]>('/api/known-ips', { params })
      const total = Number(response.headers['x-total-count'] ?? response.data.length)
      return { items: response.data, total }
    },
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

export interface KnownIpLabel {
  id: string
  label: string
  category: string | null
  group_name: string | null
  trusted: boolean
}

/**
 * The whole label set, as a lookup map.
 *
 * These are operator-curated, so the list is small and changes rarely. Fetching
 * it once and matching client-side means every IP anywhere in the app can show
 * its label with no per-row request, which is what makes annotating grids
 * practical at all.
 */
export function useKnownIpMap() {
  const { data } = useQuery({
    queryKey: knownIpKeys.list({ all: true }),
    queryFn: async (): Promise<Record<string, KnownIpLabel>> => {
      const response = await api.get<KnownIp[]>('/api/known-ips', { params: { limit: 500 } })
      return Object.fromEntries(
        response.data.map((k) => [k.ip_address, {
          id: k.id, label: k.label, category: k.category,
          group_name: k.group_name, trusted: k.trusted,
        }]),
      )
    },
    staleTime: 5 * 60_000,
  })
  return data ?? {}
}

/**
 * Resolve a page of addresses to their labels in one request.
 *
 * Grids render dozens of rows; a request per row would be dozens of round
 * trips, so callers hand over every address currently on screen.
 */
export function useKnownIpLookup(ips: string[]) {
  const unique = [...new Set(ips.filter(Boolean))].sort()
  return useQuery({
    queryKey: knownIpKeys.lookup(unique),
    queryFn: async (): Promise<Record<string, KnownIpLabel>> => {
      if (unique.length === 0) return {}
      const response = await api.post('/api/known-ips/lookup', { ips: unique })
      return response.data
    },
    enabled: unique.length > 0,
    // Labels change rarely; re-asking on every render would be wasteful.
    staleTime: 5 * 60_000,
  })
}

export function useIpReport(ip: string | null, days = 30) {
  return useQuery({
    queryKey: ip ? knownIpKeys.report(ip, days) : ['known-ips', 'report', 'none'],
    queryFn: async () => {
      const response = await api.get(`/api/known-ips/report/${encodeURIComponent(ip!)}`, {
        params: { days },
      })
      return response.data
    },
    enabled: Boolean(ip),
    staleTime: 60_000,
  })
}

function useInvalidate() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: knownIpKeys.all })
}

export function useCreateKnownIp() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (payload: Partial<KnownIp>) => (await api.post('/api/known-ips', payload)).data,
    onSuccess: () => { invalidate(); toastSuccess('IP labelled') },
    onError: (e: Error & { response?: { data?: { detail?: string } } }) =>
      toastError(e.response?.data?.detail || 'Failed to label IP'),
  })
}

export function useUpdateKnownIp() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async ({ id, ...payload }: Partial<KnownIp> & { id: string }) =>
      (await api.put(`/api/known-ips/${id}`, payload)).data,
    onSuccess: () => { invalidate(); toastSuccess('Label updated') },
    onError: (e: Error & { response?: { data?: { detail?: string } } }) =>
      toastError(e.response?.data?.detail || 'Failed to update label'),
  })
}

export function useDeleteKnownIp() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/known-ips/${id}`) },
    onSuccess: () => { invalidate(); toastSuccess('Label removed') },
    onError: (e: Error & { response?: { data?: { detail?: string } } }) =>
      toastError(e.response?.data?.detail || 'Failed to remove label'),
  })
}

export interface KnownIpGroup {
  group_name: string
  count: number
}

export function useKnownIpGroups() {
  return useQuery({
    queryKey: [...knownIpKeys.all, 'groups'],
    queryFn: async (): Promise<KnownIpGroup[]> =>
      (await api.get('/api/known-ips/groups')).data,
    staleTime: 60_000,
  })
}
