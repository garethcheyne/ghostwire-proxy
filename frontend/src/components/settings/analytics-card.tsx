'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import api from '@/lib/api'
import { useSession } from '@/lib/auth-client'
import { LoadError } from '@/components/load-state'
import { AnalyticsSettings } from '@/components/analytics/analytics-settings'
import type {
  AnalyticsSettingsChange,
  AnalyticsSettingsValue,
  AnalyticsTestResult,
} from '@/components/analytics/types'

function detail(error: unknown, fallback: string): string {
  const message = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof message === 'string' ? message : fallback
}

/**
 * System monitoring with Ghostwire Analytics (the shared registry card), for admins only. The API
 * keeps the settings; the ingest key never comes back, only whether one is stored.
 */
export function AnalyticsCard() {
  const { data: session, isPending } = useSession()
  const isAdmin = session?.user?.role === 'admin'
  const [value, setValue] = useState<AnalyticsSettingsValue | null>(null)
  const [loadError, setLoadError] = useState(false)

  const load = () =>
    api
      .get<AnalyticsSettingsValue>('/api/settings/analytics')
      .then(({ data }) => {
        setValue(data)
        setLoadError(false)
      })
      .catch(() => setLoadError(true))

  useEffect(() => {
    if (isAdmin) void load()
  }, [isAdmin])

  if (isPending || !isAdmin) return null

  if (loadError) {
    return <LoadError what="Ghostwire Analytics settings" onRetry={load} />
  }

  if (!value) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading Ghostwire Analytics settings…
        </div>
      </div>
    )
  }

  const onSave = async (change: AnalyticsSettingsChange) => {
    try {
      const { data } = await api.put<AnalyticsSettingsValue>('/api/settings/analytics', change)
      setValue(data)
    } catch (error) {
      throw new Error(detail(error, 'Could not save the Ghostwire Analytics settings.'))
    }
  }

  const onTest = async (change: AnalyticsSettingsChange): Promise<AnalyticsTestResult> => {
    try {
      const { data } = await api.post<AnalyticsTestResult>('/api/settings/analytics/test', change)
      return data
    } catch (error) {
      return { ok: false, message: detail(error, 'Could not run the test.') }
    }
  }

  return <AnalyticsSettings value={value} onSave={onSave} onTest={onTest} />
}
