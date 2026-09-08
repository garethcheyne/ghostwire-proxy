'use client'

import { useQuery, keepPreviousData } from '@tanstack/react-query'
import api from '@/lib/api'
import type { TrafficLog } from '@/types'
import { trafficKeys } from './keys'

export interface TrafficLogParams {
  page: number
  limit: number
  proxyHostId?: string
  /** Status class base: 200, 300, 400 or 500. Expanded to a min/max range. */
  statusClass?: string
  /** Free text over request URI, client IP and user agent. */
  search?: string
}

export interface TrafficLogsResult {
  items: TrafficLog[]
  total: number
}

async function fetchTrafficLogs(params: TrafficLogParams): Promise<TrafficLogsResult> {
  const query: Record<string, string | number> = {
    skip: (params.page - 1) * params.limit,
    limit: params.limit,
  }
  if (params.proxyHostId) query.proxy_host_id = params.proxyHostId
  if (params.search) query.search = params.search

  // The filter offers whole status classes ("4xx"), but the API takes an
  // explicit range — 400 alone would only ever match a literal 400.
  if (params.statusClass) {
    const base = Number(params.statusClass)
    if (!Number.isNaN(base)) {
      query.status_min = base
      query.status_max = base + 99
    }
  }

  const response = await api.get<TrafficLog[]>('/api/traffic', { params: query })
  // Total lives in the header; falling back to the page length would peg the
  // pager at a single page, which is exactly the bug this replaced.
  const total = Number(response.headers['x-total-count'] ?? response.data.length)
  return { items: response.data, total }
}

export function useTrafficLogs(params: TrafficLogParams) {
  return useQuery({
    queryKey: trafficKeys.logs({ ...params }),
    queryFn: () => fetchTrafficLogs(params),
    staleTime: 15_000,
    // Keeps the previous page on screen while the next one loads, instead of
    // blanking the table back to a spinner on every page/filter change.
    placeholderData: keepPreviousData,
  })
}
