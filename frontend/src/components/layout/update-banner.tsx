'use client'

import { useState, useEffect } from 'react'
import { ArrowUpCircle, Shield, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface UpdateInfo {
  checked: boolean
  app_update_available: boolean
  app_latest_version: string | null
  app_current_version: string | null
  base_image_updates: number
  base_image_details: { container: string; image: string }[]
  checked_at: string | null
}

export function UpdateBanner() {
  const [update, setUpdate] = useState<UpdateInfo | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const router = useRouter()

  useEffect(() => {
    checkForUpdates()
    // Poll every 5 minutes
    const interval = setInterval(checkForUpdates, 300000)
    return () => clearInterval(interval)
  }, [])

  const checkForUpdates = async () => {
    try {
      const response = await api.get('/api/updates/available')
      setUpdate(response.data)
    } catch {
      // Silently fail — this is a background check
    }
  }

  if (dismissed || !update?.checked) return null

  const hasAppUpdate = update.app_update_available
  const hasBaseUpdates = update.base_image_updates > 0

  if (!hasAppUpdate && !hasBaseUpdates) return null

  return (
    <div className="relative border-b bg-cyan-950/50 border-cyan-800/30 px-4 py-2">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 text-sm">
          {hasAppUpdate && (
            <div className="flex items-center gap-2 text-cyan-400">
              <ArrowUpCircle className="h-4 w-4" />
              <span>
                Version <strong>{update.app_latest_version}</strong> is available
                <span className="text-muted-foreground ml-1">
                  (current: {update.app_current_version})
                </span>
              </span>
            </div>
          )}
          {hasAppUpdate && hasBaseUpdates && (
            <span className="text-muted-foreground">·</span>
          )}
          {hasBaseUpdates && (
            <div className="flex items-center gap-2 text-amber-400">
              <Shield className="h-4 w-4" />
              <span>
                {update.base_image_updates} container{update.base_image_updates !== 1 ? 's have' : ' has'} security updates
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-cyan-400 hover:text-cyan-300"
            onClick={() => router.push('/dashboard/system?tab=updates')}
          >
            View Updates
          </Button>
          <button
            onClick={() => setDismissed(true)}
            className="text-muted-foreground hover:text-foreground"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
