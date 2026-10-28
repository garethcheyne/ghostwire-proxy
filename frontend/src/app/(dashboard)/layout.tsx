'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/app-shell'
import { HeaderSearch } from '@/components/layout/header-search'
import { HeaderActions } from '@/components/layout/header-actions'
import { UserMenu } from '@/components/layout/user-menu'
import { UpdateBanner } from '@/components/layout/update-banner'
import { navigation, mobileTabs } from '@/components/layout/nav-config'
import { ConfirmDialogProvider } from '@/components/confirm-dialog'
import { IpActionsProvider } from '@/components/ip-actions-provider'
import api from '@/lib/api'
import { authClient } from '@/lib/auth-client'
import { clearLegacySession } from '@/lib/session'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(true)
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    // Check authentication (Better Auth session cookie)
    let cancelled = false
    authClient
      .getSession()
      .then(({ data }) => {
        if (cancelled) return
        if (data) {
          setIsLoading(false)
        } else {
          clearLegacySession()
          const next = window.location.pathname + window.location.search
          router.push(`/auth/login?next=${encodeURIComponent(next)}`)
        }
      })
      .catch(() => {
        if (!cancelled) router.push('/auth/login')
      })
    return () => {
      cancelled = true
    }
  }, [router])

  // The version for the sidebar footer, once signed in (as the sidebar used to fetch it on mount).
  useEffect(() => {
    if (isLoading) return
    api.get('/version').then(res => setVersion(res.data.version)).catch(() => {})
  }, [isLoading])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="relative h-12 w-12">
            <div className="absolute inset-0 animate-ping rounded-full bg-brand/30" />
            <div className="absolute inset-2 animate-spin rounded-full border-2 border-brand border-t-transparent" />
            <div className="absolute inset-4 rounded-full bg-brand/50" />
          </div>
          <p className="text-sm text-muted-foreground animate-pulse">Initializing...</p>
        </div>
      </div>
    )
  }

  return (
    <ConfirmDialogProvider>
      <IpActionsProvider>
        <AppShell
          product={{
            name: 'Ghostwire Proxy',
            line: 'Reverse Proxy Manager',
            logo: '/logo.png',
            logoLight: '/logo-black.png',
            href: '/dashboard',
          }}
          nav={navigation}
          mobileTabs={mobileTabs}
          version={version}
          aboutHref="/dashboard/about"
          headerStart={<HeaderSearch />}
          headerActions={<HeaderActions />}
          userMenu={<UserMenu />}
          banner={<UpdateBanner />}
        >
          {children}
        </AppShell>
      </IpActionsProvider>
    </ConfirmDialogProvider>
  )
}
