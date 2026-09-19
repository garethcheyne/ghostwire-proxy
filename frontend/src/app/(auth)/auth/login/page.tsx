'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { Loader2, AlertCircle, ShieldCheck, KeyRound } from 'lucide-react'
import api from '@/lib/api'
import { setSessionActive } from '@/lib/session'

export default function LoginPage() {
  const router = useRouter()
  const [isSetupMode, setIsSetupMode] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Two-factor challenge. `stage` drives which form is shown: the password
  // form, the 6-digit code form, or forced enrolment when MFA is required
  // org-wide and this account has not set it up yet.
  const [stage, setStage] = useState<'password' | 'totp' | 'enrol'>('password')
  const [challengeToken, setChallengeToken] = useState('')
  const [enrolmentToken, setEnrolmentToken] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [enrolSecret, setEnrolSecret] = useState('')
  const [enrolQr, setEnrolQr] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [savedCodes, setSavedCodes] = useState(false)

  // Form fields
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  useEffect(() => {
    checkSetup()
  }, [])

  const checkSetup = async () => {
    try {
      const response = await api.get('/api/setup/check')
      setIsSetupMode(response.data.setup_required)
    } catch {
      // If check fails, assume login mode
      setIsSetupMode(false)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      if (isSetupMode) {
        // Initial setup
        if (password !== confirmPassword) {
          setError('Passwords do not match')
          setIsSubmitting(false)
          return
        }

        if (password.length < 8) {
          setError('Password must be at least 8 characters')
          setIsSubmitting(false)
          return
        }

        const response = await api.post('/api/setup/initialize', {
          email,
          password,
          name,
        })

        localStorage.setItem('access_token', response.data.access_token)
        localStorage.setItem('refresh_token', response.data.refresh_token)
        setSessionActive()
        router.push('/dashboard')
      } else {
        // Normal login. The password alone may not be enough: the API answers
        // with a challenge instead of a session when MFA is in play.
        const response = await api.post('/api/auth/login', {
          email,
          password,
        })

        if (response.data.challenge === 'totp') {
          setChallengeToken(response.data.challenge_token)
          setStage('totp')
          return
        }

        if (response.data.challenge === 'enrol') {
          setEnrolmentToken(response.data.enrolment_token)
          await beginEnrolment(response.data.enrolment_token)
          setStage('enrol')
          return
        }

        localStorage.setItem('access_token', response.data.access_token)
        localStorage.setItem('refresh_token', response.data.refresh_token)
        setSessionActive()
        router.push('/dashboard')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred')
    } finally {
      setIsSubmitting(false)
    }
  }

  // The enrolment token is not a session, so it has to be passed explicitly —
  // the axios interceptor only attaches a stored access_token.
  const beginEnrolment = async (token: string) => {
    const setup = await api.post(
      '/api/auth/mfa/setup',
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    )
    setEnrolSecret(setup.data.secret)
    setEnrolQr(setup.data.qr_code || '')
    setBackupCodes(setup.data.backup_codes || [])
  }

  const handleTotpSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      const response = await api.post('/api/auth/login/totp', {
        challenge_token: challengeToken,
        code: totpCode.trim(),
      })
      localStorage.setItem('access_token', response.data.access_token)
      localStorage.setItem('refresh_token', response.data.refresh_token)
      setSessionActive()
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid verification code')
      setTotpCode('')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Verifying during forced enrolment also completes the login, so the API
  // hands back the session here rather than making the user sign in twice.
  const handleEnrolSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)
    try {
      const response = await api.post(
        '/api/auth/mfa/verify',
        { code: totpCode.trim() },
        { headers: { Authorization: `Bearer ${enrolmentToken}` } }
      )
      localStorage.setItem('access_token', response.data.access_token)
      localStorage.setItem('refresh_token', response.data.refresh_token)
      setSessionActive()
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'That code did not match')
      setTotpCode('')
    } finally {
      setIsSubmitting(false)
    }
  }

  const restart = () => {
    setStage('password')
    setTotpCode('')
    setChallengeToken('')
    setEnrolmentToken('')
    setError('')
    setPassword('')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Mobile logo */}
      <div className="lg:hidden flex flex-col items-center justify-center gap-4 mb-8">
        <div className="relative h-20 w-20">
          <Image
            src="/logo.png"
            alt="Ghostwire Logo"
            width={80}
            height={80}
            className="h-20 w-20 object-contain"
          />
        </div>
        <div className="text-center">
          <span className="text-2xl font-bold">Ghostwire</span>
          <p className="text-xs text-muted-foreground uppercase tracking-widest mt-1">Reverse Proxy Manager</p>
        </div>
      </div>

      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-bold tracking-tight">
          {stage === 'totp'
            ? 'Two-factor authentication'
            : stage === 'enrol'
            ? 'Set up two-factor authentication'
            : isSetupMode
            ? 'Initial Setup'
            : 'Welcome back'}
        </h1>
        <p className="text-muted-foreground">
          {stage === 'totp'
            ? 'Enter the 6-digit code from your authenticator app'
            : stage === 'enrol'
            ? 'Your administrator requires two-factor authentication on every admin account'
            : isSetupMode
            ? 'Create your administrator account'
            : 'Sign in to your account to continue'}
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {stage === 'password' && (
      <form onSubmit={handleSubmit} className="space-y-4">
        {isSetupMode && (
          <div className="space-y-2">
            <label className="block text-sm font-medium">
              Full Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="John Doe"
              required
              disabled={isSubmitting}
            />
          </div>
        )}

        <div className="space-y-2">
          <label className="block text-sm font-medium">
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="admin@proxy.local"
            required
            disabled={isSubmitting}
            autoComplete="email"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="••••••••"
            required
            disabled={isSubmitting}
            autoComplete="current-password"
            minLength={isSetupMode ? 8 : 1}
          />
        </div>

        {isSetupMode && (
          <div className="space-y-2">
            <label className="block text-sm font-medium">
              Confirm Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="••••••••"
              required
              disabled={isSubmitting}
              minLength={8}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-10 bg-primary text-primary-foreground rounded-md font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
        >
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {isSetupMode ? 'Create Account' : 'Sign in'}
        </button>
      </form>
      )}

      {stage === 'totp' && (
        <form onSubmit={handleTotpSubmit} className="space-y-4">
          <div className="flex justify-center">
            <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
              <ShieldCheck className="h-6 w-6 text-primary" />
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium">Verification code</label>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="w-full h-12 px-4 rounded-md border border-input bg-background text-center text-2xl tracking-[0.4em] font-mono focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="000000"
              maxLength={8}
              autoFocus
              required
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground text-center">
              Lost your device? Enter one of your 8-character backup codes instead.
            </p>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || totpCode.trim().length < 6}
            className="w-full h-10 bg-primary text-primary-foreground rounded-md font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Verify
          </button>

          <button
            type="button"
            onClick={restart}
            className="w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Back to sign in
          </button>
        </form>
      )}

      {stage === 'enrol' && (
        <form onSubmit={handleEnrolSubmit} className="space-y-4">
          <ol className="space-y-4">
            <li className="space-y-2">
              <p className="text-sm font-medium">
                1. Scan this with your authenticator app
              </p>
              {enrolQr ? (
                <div className="flex justify-center">
                  {/* Rendered server-side so the secret never reaches a third
                      party QR service. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={enrolQr}
                    alt="Two-factor setup QR code"
                    className="h-44 w-44 rounded-lg border border-border bg-white p-2"
                  />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  QR code unavailable — enter the key below manually.
                </p>
              )}
              <div className="rounded-md border border-border bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground mb-1">
                  Or enter this key manually
                </p>
                <code className="text-sm font-mono break-all select-all">
                  {enrolSecret}
                </code>
              </div>
            </li>

            <li className="space-y-2">
              <p className="text-sm font-medium">2. Save your backup codes</p>
              <p className="text-xs text-muted-foreground">
                Each can be used once if you lose your device. They are shown only now.
              </p>
              <div className="grid grid-cols-2 gap-1.5 rounded-md border border-border bg-muted/50 p-3">
                {backupCodes.map((code) => (
                  <code key={code} className="text-sm font-mono select-all">
                    {code}
                  </code>
                ))}
              </div>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={savedCodes}
                  onChange={(e) => setSavedCodes(e.target.checked)}
                  className="mt-0.5"
                />
                <span>I have saved these backup codes somewhere safe</span>
              </label>
            </li>

            <li className="space-y-2">
              <p className="text-sm font-medium">
                3. Enter the code from your app to finish
              </p>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                className="w-full h-12 px-4 rounded-md border border-input bg-background text-center text-2xl tracking-[0.4em] font-mono focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="000000"
                maxLength={6}
                required
                disabled={isSubmitting}
              />
            </li>
          </ol>

          <button
            type="submit"
            disabled={isSubmitting || !savedCodes || totpCode.trim().length < 6}
            className="w-full h-10 bg-primary text-primary-foreground rounded-md font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <KeyRound className="h-4 w-4" />
            Enable and sign in
          </button>

          <button
            type="button"
            onClick={restart}
            className="w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
        </form>
      )}
    </div>
  )
}
