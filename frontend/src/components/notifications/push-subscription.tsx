'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Bell,
  BellOff,
  BellRing,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Smartphone,
  Send,
} from 'lucide-react'
import api from '@/lib/api'
import {
  isPushSupported,
  getNotificationPermission,
  requestNotificationPermission,
  registerServiceWorker,
  subscribeToPush,
  unsubscribeFromPush,
  subscriptionToJson,
} from '@/lib/push-notifications'

interface PushSubscriptionManagerProps {
  className?: string
  showTestButton?: boolean
}

export function PushSubscriptionManager({
  className = '',
  showTestButton = true,
}: PushSubscriptionManagerProps) {
  // State
  const [isSupported, setIsSupported] = useState(false)
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('default')
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [vapidKey, setVapidKey] = useState<string | null>(null)
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null)

  // Initialize
  const initialize = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      // Check browser support
      const supported = isPushSupported()
      setIsSupported(supported)

      if (!supported) {
        setIsLoading(false)
        return
      }

      // Get permission status
      setPermission(getNotificationPermission())

      // Get VAPID key from server
      try {
        const response = await api.get('/api/alerts/push/vapid-key')
        setVapidKey(response.data.public_key)
      } catch (err: any) {
        if (err.response?.status === 503) {
          setError('Push notifications not configured on server')
        }
        setIsLoading(false)
        return
      }

      // Register service worker
      const reg = await registerServiceWorker()
      if (reg) {
        setRegistration(reg)

        // Check if already subscribed
        const subscription = await reg.pushManager.getSubscription()
        setIsSubscribed(!!subscription)
      }
    } catch (err: any) {
      console.error('Push initialization error:', err)
      setError('Failed to initialize notifications')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    initialize()
  }, [initialize])

  // Subscribe to push
  const handleSubscribe = async () => {
    if (!registration || !vapidKey) return

    setIsProcessing(true)
    setError(null)
    setSuccess(null)

    try {
      // Request permission if needed
      if (permission !== 'granted') {
        const result = await requestNotificationPermission()
        setPermission(result)

        if (result !== 'granted') {
          setError('Notification permission denied')
          setIsProcessing(false)
          return
        }
      }

      // Subscribe to push
      const subscription = await subscribeToPush(registration, vapidKey)

      if (subscription) {
        // Send subscription to server
        const subData = subscriptionToJson(subscription)
        await api.post('/api/alerts/push/subscribe', {
          endpoint: subData.endpoint,
          p256dh_key: subData.keys.p256dh,
          auth_key: subData.keys.auth,
          user_agent: navigator.userAgent,
        })

        setIsSubscribed(true)
        setSuccess('Push notifications enabled')
        setTimeout(() => setSuccess(null), 3000)
      }
    } catch (err: any) {
      console.error('Subscribe error:', err)
      setError(err.response?.data?.detail || 'Failed to enable notifications')
    } finally {
      setIsProcessing(false)
    }
  }

  // Unsubscribe from push
  const handleUnsubscribe = async () => {
    if (!registration) return

    setIsProcessing(true)
    setError(null)

    try {
      const subscription = await registration.pushManager.getSubscription()

      if (subscription) {
        // Unsubscribe from browser
        await unsubscribeFromPush(registration)

        // Remove from server
        await api.delete('/api/alerts/push/unsubscribe', {
          params: { endpoint: subscription.endpoint },
        })
      }

      setIsSubscribed(false)
      setSuccess('Push notifications disabled')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      console.error('Unsubscribe error:', err)
      setError('Failed to disable notifications')
    } finally {
      setIsProcessing(false)
    }
  }

  // Send test notification
  const handleTestNotification = async () => {
    setIsProcessing(true)
    setError(null)

    try {
      await api.post('/api/alerts/push/test')
      setSuccess('Test notification sent')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send test notification')
    } finally {
      setIsProcessing(false)
    }
  }

  // Not supported
  if (!isSupported) {
    return (
      <div className={`rounded-lg border border-border bg-muted/50 p-4 ${className}`}>
        <div className="flex items-center gap-3">
          <BellOff className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-medium">Push Notifications Not Supported</p>
            <p className="text-sm text-muted-foreground">
              Your browser doesn't support push notifications.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Loading
  if (isLoading) {
    return (
      <div className={`rounded-lg border border-border p-4 ${className}`}>
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">Checking notification status...</p>
        </div>
      </div>
    )
  }

  // Permission denied
  if (permission === 'denied') {
    return (
      <div className={`rounded-lg border border-destructive/30 bg-destructive/5 p-4 ${className}`}>
        <div className="flex items-center gap-3">
          <XCircle className="h-5 w-5 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Notifications Blocked</p>
            <p className="text-sm text-muted-foreground">
              You've blocked notifications for this site. Enable them in your browser settings.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Main UI
  return (
    <div className={`space-y-4 ${className}`}>
      {/* Status Card */}
      <div className="rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {isSubscribed ? (
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10">
                <BellRing className="h-5 w-5 text-green-500" />
              </div>
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                <Bell className="h-5 w-5 text-muted-foreground" />
              </div>
            )}
            <div>
              <p className="font-medium">
                {isSubscribed ? 'Push Notifications Enabled' : 'Push Notifications'}
              </p>
              <p className="text-sm text-muted-foreground">
                {isSubscribed
                  ? 'You will receive alerts about threats, updates, and more.'
                  : 'Get real-time alerts for security threats and updates.'}
              </p>
            </div>
          </div>

          <button
            onClick={isSubscribed ? handleUnsubscribe : handleSubscribe}
            disabled={isProcessing || !vapidKey}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
              isSubscribed
                ? 'border border-input hover:bg-muted'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isSubscribed ? (
              <>
                <BellOff className="h-4 w-4" />
                <span className="hidden sm:inline">Disable</span>
              </>
            ) : (
              <>
                <Bell className="h-4 w-4" />
                <span className="hidden sm:inline">Enable</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {success && (
        <div className="flex items-center gap-2 rounded-lg bg-green-500/10 border border-green-500/20 p-3 text-sm text-green-500">
          <CheckCircle className="h-4 w-4 flex-shrink-0" />
          {success}
        </div>
      )}

      {/* Test Button */}
      {showTestButton && isSubscribed && (
        <button
          onClick={handleTestNotification}
          disabled={isProcessing}
          className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm hover:bg-muted disabled:opacity-50"
        >
          {isProcessing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Send Test Notification
        </button>
      )}

      {/* Device Info */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Smartphone className="h-3 w-3" />
        <span>
          {isSubscribed
            ? 'This device will receive notifications'
            : 'Subscribe on each device you want to receive notifications'}
        </span>
      </div>
    </div>
  )
}

export default PushSubscriptionManager
