import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

type Status = 'loading' | 'success' | 'error'

export default function Callback() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')

  const wallId = searchParams.get('wall') || ''
  const redirectUrl = searchParams.get('redirect') || '/'
  const errorParam = searchParams.get('error')
  const errorDescription = searchParams.get('error_description')

  useEffect(() => {
    // Check for error in URL params (OAuth error)
    if (errorParam) {
      setStatus('error')
      setError(errorDescription || errorParam || 'Authentication failed')
      return
    }

    // If we reach this page without error, OAuth was successful
    // The backend should have set the session cookie and redirected
    // This page is a fallback
    setStatus('success')

    // Auto-redirect after short delay
    const timer = setTimeout(() => {
      window.location.href = redirectUrl
    }, 1500)

    return () => clearTimeout(timer)
  }, [errorParam, errorDescription, redirectUrl])

  const loginUrl = `/__auth/login?wall=${wallId}&redirect=${encodeURIComponent(redirectUrl)}`

  return (
    <div className="auth-layout items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            {status === 'loading' && (
              <>
                <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
                  <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
                </div>
                <CardTitle>Authenticating...</CardTitle>
                <CardDescription>Please wait while we complete your sign in</CardDescription>
              </>
            )}

            {status === 'success' && (
              <>
                <div className="mx-auto w-16 h-16 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center mb-4">
                  <CheckCircle className="w-8 h-8 text-green-400" />
                </div>
                <CardTitle>Success!</CardTitle>
                <CardDescription>Redirecting you now...</CardDescription>
              </>
            )}

            {status === 'error' && (
              <>
                <div className="mx-auto w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
                  <XCircle className="w-8 h-8 text-red-400" />
                </div>
                <CardTitle>Authentication Failed</CardTitle>
                <CardDescription>Unable to complete sign in</CardDescription>
              </>
            )}
          </CardHeader>

          {status === 'error' && (
            <CardContent className="space-y-4">
              <div className="alert-error flex items-start gap-3">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <p className="text-sm">{error}</p>
              </div>

              <a
                href={loginUrl}
                className="inline-flex items-center justify-center w-full h-11 rounded-md bg-cyan-600 text-white font-medium hover:bg-cyan-700 transition-colors"
              >
                Try Again
              </a>

              <p className="text-center text-xs text-white/30">
                Protected by Ghostwire Proxy
              </p>
            </CardContent>
          )}
        </Card>
      </div>
    </div>
  )
}
