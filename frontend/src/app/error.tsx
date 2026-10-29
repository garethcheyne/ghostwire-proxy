'use client'

/**
 * Root error boundary — catches any uncaught render error anywhere in the app.
 * Next.js requires this to be a Client Component.
 */

import { useEffect } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('Unhandled application error:', error)
  }, [error])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-red-500" />
        <h1 className="mt-4 text-lg font-semibold">Something went wrong</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.message || 'An unexpected error occurred.'}
        </p>
        {error.digest && (
          <p className="mt-1 text-xs text-muted-foreground/70">
            Reference: <code>{error.digest}</code>
          </p>
        )}
        <Button
          size="lg"
          onClick={reset}
          className="mt-4"
        >
          Try again
        </Button>
      </div>
    </div>
  )
}
