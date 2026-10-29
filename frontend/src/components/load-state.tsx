'use client'

import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/**
 * What a page shows under its PageHeader when its data could not be loaded, so a failed load
 * never looks like "nothing here yet".
 */
export function LoadError({
  what,
  onRetry,
  className,
}: {
  /** What failed to load, e.g. "proxy hosts". */
  what: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <Empty className={cn('border border-solid bg-card', className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-red-500/10 text-red-600 dark:text-red-400">
          <AlertTriangle />
        </EmptyMedia>
        <EmptyTitle>Couldn&apos;t load {what}</EmptyTitle>
        <EmptyDescription>The API didn&apos;t answer. Check that the proxy API is running, then try again.</EmptyDescription>
      </EmptyHeader>
      {onRetry && (
        <EmptyContent>
          <Button variant="outline" onClick={onRetry}>
            <RefreshCw /> Try again
          </Button>
        </EmptyContent>
      )}
    </Empty>
  )
}

/** The placeholder a page shows under its PageHeader while its data loads. */
export function ContentSkeleton({
  stats = 0,
  rows = 4,
  className,
}: {
  /** Number of StatCard-sized tiles across the top. */
  stats?: number
  /** Number of list rows / cards underneath. */
  rows?: number
  className?: string
}) {
  return (
    <div className={cn('space-y-4 sm:space-y-6', className)} aria-busy="true" aria-label="Loading">
      {stats > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          {Array.from({ length: stats }, (_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl sm:h-32" />
          ))}
        </div>
      )}
      <div className="space-y-3">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-16 rounded-xl" />
        ))}
      </div>
    </div>
  )
}
