'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, AlertCircle } from 'lucide-react'
import api from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [isSetupMode, setIsSetupMode] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

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
        router.push('/dashboard')
      } else {
        // Normal login
        const response = await api.post('/api/auth/login', {
          email,
          password,
        })

        localStorage.setItem('access_token', response.data.access_token)
        localStorage.setItem('refresh_token', response.data.refresh_token)
        router.push('/dashboard')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred')
    } finally {
      setIsSubmitting(false)
    }
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
          <img
            src="/logo.png"
            alt="Ghostwire Logo"
            className="h-20 w-20 object-contain [filter:brightness(0)_saturate(100%)_invert(42%)_sepia(93%)_saturate(1352%)_hue-rotate(162deg)_brightness(95%)_contrast(106%)] dark:[filter:brightness(0)_saturate(100%)_invert(71%)_sepia(53%)_saturate(425%)_hue-rotate(162deg)_brightness(95%)_contrast(92%)]"
          />
        </div>
        <div className="text-center">
          <span className="text-2xl font-bold">Ghostwire</span>
          <p className="text-xs text-muted-foreground uppercase tracking-widest mt-1">Reverse Proxy Manager</p>
        </div>
      </div>

      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-bold tracking-tight">
          {isSetupMode ? 'Initial Setup' : 'Welcome back'}
        </h1>
        <p className="text-muted-foreground">
          {isSetupMode
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
              className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
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
            className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
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
            className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
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
              className="w-full h-10 px-4 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
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
    </div>
  )
}
