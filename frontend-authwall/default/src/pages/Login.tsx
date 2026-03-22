import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { User, Lock, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getAuthWallConfig, loginLocal, getOAuthStartUrl } from '@/api/client'
import type { AuthWallConfig } from '@/api/types'
import { cn } from '@/lib/utils'

// OAuth provider icons
const providerIcons: Record<string, React.ReactNode> = {
  google: (
    <svg className="w-5 h-5" viewBox="0 0 24 24">
      <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  ),
  github: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
    </svg>
  ),
  azure_ad: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M11.4 24H0l9.7-16.4L11.4 24zm1.2 0h11.4L14.3 7.6 12.6 24zM12 0L1.5 17.3 12 5.8l10.5 11.5L12 0z"/>
    </svg>
  ),
  oidc: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
    </svg>
  ),
}

export default function Login() {
  const [searchParams] = useSearchParams()
  const wallId = searchParams.get('wall') || ''
  const redirectUrl = searchParams.get('redirect') || '/'

  const [config, setConfig] = useState<AuthWallConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (!wallId) {
      setError('Missing authentication configuration')
      setLoading(false)
      return
    }

    getAuthWallConfig(wallId)
      .then(setConfig)
      .catch(() => setError('Failed to load authentication configuration'))
      .finally(() => setLoading(false))
  }, [wallId])

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const result = await loginLocal(wallId, username, password)

      if (result.success) {
        if (result.requires_totp) {
          // Redirect to TOTP page
          const params = new URLSearchParams({
            wall: wallId,
            session: result.partial_session_id || '',
            redirect: redirectUrl,
          })
          window.location.href = `/__auth/totp?${params}`
        } else {
          // Login successful, redirect to original URL
          window.location.href = redirectUrl
        }
      } else {
        setError(result.message || 'Invalid username or password')
      }
    } catch {
      setError('An error occurred. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleOAuthLogin = (providerId: string) => {
    window.location.href = getOAuthStartUrl(wallId, providerId, redirectUrl)
  }

  if (loading) {
    return (
      <div className="auth-layout items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    )
  }

  const hasLocalAuth = config?.has_local_users
  const hasOAuth = config?.providers && config.providers.length > 0
  const hasLdap = config?.has_ldap
  const hasMultipleMethods = (hasLocalAuth || hasLdap) && hasOAuth

  return (
    <div className="auth-layout">
      {/* Left Panel - Branding */}
      <div className="auth-brand-panel hidden lg:flex lg:w-1/2 flex-col justify-between p-10 relative">
        {/* Background effects */}
        <div className="auth-dot-grid" />
        <div className="auth-scanline" />
        <div className="auth-glow-primary top-1/4 -left-20" />
        <div className="auth-glow-secondary bottom-1/4 right-10" />

        {/* Logo & Status */}
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="relative h-10 w-10">
              <img
                src="/__auth/logo.png"
                alt="Ghostwire Logo"
                className="h-10 w-10 object-contain [filter:brightness(0)_saturate(100%)_invert(71%)_sepia(53%)_saturate(425%)_hue-rotate(162deg)_brightness(95%)_contrast(92%)]"
              />
            </div>
            <div>
              <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
                Ghostwire
              </span>
              <div className="text-[10px] text-white/40 tracking-[0.2em] uppercase">
                Security Platform
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4">
            <span className="status-dot status-dot-amber" />
            <span className="text-xs text-amber-400/80 font-medium">
              Authentication Required
            </span>
          </div>
        </div>

        {/* Main Heading */}
        <div className="relative z-10">
          <h1 className="text-4xl font-bold leading-tight">
            <span className="text-white">Sign in to</span>
            <br />
            <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
              continue
            </span>
          </h1>
          <p className="text-white/40 mt-4 max-w-md">
            This resource is protected by Ghostwire Proxy. Please authenticate to proceed.
          </p>
        </div>

        {/* Security Info */}
        <div className="relative z-10 space-y-3">
          {[
            'Encrypted connection',
            'Session-based authentication',
            'Automatic timeout protection',
          ].map((text, i) => (
            <div
              key={text}
              className={cn(
                'flex items-center gap-2 text-sm text-white/50 opacity-0 animate-float-up',
                `animate-delay-${(i + 1) * 100}`
              )}
              style={{ animationFillMode: 'forwards' }}
            >
              <div className="w-1 h-1 rounded-full bg-cyan-500" />
              {text}
            </div>
          ))}
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="auth-form-panel flex-1 flex items-center justify-center p-6 lg:p-10">
        <div className="w-full max-w-md">
          {/* Mobile Logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8 justify-center">
            <div className="relative h-10 w-10">
              <img
                src="/__auth/logo.png"
                alt="Ghostwire Logo"
                className="h-10 w-10 object-contain [filter:brightness(0)_saturate(100%)_invert(71%)_sepia(53%)_saturate(425%)_hue-rotate(162deg)_brightness(95%)_contrast(92%)]"
              />
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
              Ghostwire
            </span>
          </div>

          <Card>
            <CardHeader className="text-center">
              <CardTitle>Welcome back</CardTitle>
              <CardDescription>
                {config?.name || 'Sign in to access this resource'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {error && (
                <div className="alert-error flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                  <p className="text-sm">{error}</p>
                </div>
              )}

              {/* OAuth Providers */}
              {hasOAuth && (
                <div className="space-y-3">
                  {config?.providers.map((provider) => (
                    <Button
                      key={provider.id}
                      variant="outline"
                      className="w-full h-11"
                      onClick={() => handleOAuthLogin(provider.id)}
                    >
                      {providerIcons[provider.provider_type] || providerIcons.oidc}
                      <span>Continue with {provider.name}</span>
                    </Button>
                  ))}
                </div>
              )}

              {/* Separator */}
              {hasMultipleMethods && (
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-white/10" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-slate-900 px-2 text-white/40">
                      Or continue with
                    </span>
                  </div>
                </div>
              )}

              {/* Local/LDAP Login Form */}
              {(hasLocalAuth || hasLdap) && (
                <form onSubmit={handleLocalLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                      <Input
                        id="username"
                        type="text"
                        placeholder="Enter your username"
                        className="pl-10"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        required
                        autoComplete="username"
                        autoFocus
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                      <Input
                        id="password"
                        type="password"
                        placeholder="Enter your password"
                        className="pl-10"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        autoComplete="current-password"
                      />
                    </div>
                  </div>

                  <Button
                    type="submit"
                    className="w-full h-11"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Signing in...
                      </>
                    ) : (
                      'Sign in'
                    )}
                  </Button>
                </form>
              )}

              {/* Footer */}
              <p className="text-center text-xs text-white/30">
                Protected by Ghostwire
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
