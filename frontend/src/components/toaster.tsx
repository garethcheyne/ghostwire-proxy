'use client'

import { useState, useEffect } from 'react'
import { registerToastSetter, type ToastItem } from '@/lib/toast'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

const icons = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
}

// A plain popover-coloured card; the icon carries the status colour.
const iconStyles = {
  success: 'text-green-600 dark:text-green-400',
  error: 'text-red-600 dark:text-red-400',
  info: 'text-sky-600 dark:text-sky-400',
}

export function Toaster() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    registerToastSetter(setToasts)
  }, [])

  const dismiss = (id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  if (toasts.length === 0) return null

  return (
    <div className={
        // On phones the bottom tab bar owns the bottom of the screen, so toasts
        // sit above it and span the width instead of being pinned to a corner
        // that a 360px screen cannot fit.
        'fixed z-100 flex flex-col gap-2 ' +
        'left-4 right-4 bottom-[calc(64px+env(safe-area-inset-bottom)+1rem)] ' +
        'md:left-auto md:right-4 md:bottom-4 md:max-w-sm'
      }>
      {toasts.map(t => {
        const Icon = icons[t.type]
        return (
          <div
            key={t.id}
            role={t.type === 'error' ? 'alert' : 'status'}
            className="flex items-start gap-3 rounded-lg border bg-popover px-4 py-3 text-popover-foreground shadow-lg animate-in slide-in-from-bottom-2 fade-in duration-200"
          >
            <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${iconStyles[t.type]}`} />
            <p className="text-sm flex-1">{t.message}</p>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="-mr-1 shrink-0 text-muted-foreground"
            >
              <X />
            </Button>
          </div>
        )
      })}
    </div>
  )
}
