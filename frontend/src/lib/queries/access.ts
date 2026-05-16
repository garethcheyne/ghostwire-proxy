'use client'

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import type { AccessList, AuthWall } from '@/types'
import { accessListKeys, type ListParams } from './keys'

export interface AccessListsResult {
  items: AccessList[]
  total: number
}

export function useAccessLists(params: ListParams = {}) {
  return useQuery({
    queryKey: accessListKeys.list(params),
    queryFn: async (): Promise<AccessListsResult> => {
      const response = await api.get<AccessList[]>('/api/access-lists', { params })
      const total = Number(response.headers['x-total-count'] ?? response.data.length)
      return { items: response.data, total }
    },
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}

export function useCreateAccessList() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Partial<AccessList>) => {
      const response = await api.post<AccessList>('/api/access-lists', payload)
      return response.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: accessListKeys.all })
      toastSuccess('Access list created')
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toastError(error.response?.data?.detail || 'Failed to create access list')
    },
  })
}

export function useAuthWalls() {
  return useQuery({
    queryKey: ['auth-walls', 'list'] as const,
    queryFn: async () => {
      const response = await api.get<AuthWall[]>('/api/auth-walls')
      return response.data
    },
    staleTime: 60_000,
  })
}
