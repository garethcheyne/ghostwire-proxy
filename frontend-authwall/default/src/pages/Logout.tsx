import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { logout } from '@/api/client'

export default function Logout() {
  const [searchParams] = useSearchParams()
  const [isLoggingOut, setIsLoggingOut] = useState(true)

  const wallId = searchParams.get('wall') || ''
  const redirectUrl = searchParams.get('redirect') || '/'

  useEffect(() => {
    const doLogout = async () => {
      try {
        if (wallId) {
          await logout(wallId)
        }
      } catch {
        // Ignore errors - we're logging out anyway
      } finally {
        setIsLoggingOut(false)

        // Redirect to login after short delay
        setTimeout(() => {
          const loginUrl = `/__auth/login?wall=${wallId}&redirect=${encodeURIComponent(redirectUrl)}`
          window.location.href = loginUrl
        }, 1500)
      }
    }

    doLogout()
  }, [wallId, redirectUrl])

  return (
    <div className="auth-layout items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            {isLoggingOut ? (
              <>
                <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
                  <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
                </div>
                <CardTitle>Signing out...</CardTitle>
                <CardDescription>Please wait</CardDescription>
              </>
            ) : (
              <>
                <div className="mx-auto w-16 h-16 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center mb-4">
                  <CheckCircle className="w-8 h-8 text-green-400" />
                </div>
                <CardTitle>Signed out</CardTitle>
                <CardDescription>Redirecting to login...</CardDescription>
              </>
            )}
          </CardHeader>

          <CardContent>
            <p className="text-center text-xs text-white/30">
              Protected by Ghostwire
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
