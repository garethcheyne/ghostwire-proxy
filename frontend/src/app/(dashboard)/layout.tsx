'use client'

import { useState, useEffect, createContext, useContext } from 'react'
import { useRouter } from 'next/navigation'
import { Sidebar } from '@/components/layout/sidebar'
import { MobileSidebar } from '@/components/layout/mobile-sidebar'
import { Header } from '@/components/layout/header'
import { cn } from '@/lib/utils'
import { clearSession, setSessionActive } from '@/lib/session'

interface SidebarContextType {
  isCollapsed: boolean
  setIsCollapsed: (value: boolean) => void
  isMobileOpen: boolean
  setIsMobileOpen: (value: boolean) => void
}

export const SidebarContext = createContext<SidebarContextType>({
  isCollapsed: false,
  setIsCollapsed: () => {},
  isMobileOpen: false,
  setIsMobileOpen: () => {},
})

export const useSidebar = () => useContext(SidebarContext)

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [isMobileOpen, setIsMobileOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Check authentication
    const token = localStorage.getItem('access_token')
    if (!token) {
      clearSession()
      router.push('/auth/login')
    } else {
      // Ensure session cookie is set if we have a token
      setSessionActive()
      setIsLoading(false)
    }
  }, [router])

  // Close mobile sidebar on route change
  useEffect(() => {
    setIsMobileOpen(false)
  }, [])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="relative h-12 w-12">
            <div className="absolute inset-0 animate-ping rounded-full bg-cyan-500/30" />
            <div className="absolute inset-2 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
            <div className="absolute inset-4 rounded-full bg-cyan-500/50" />
          </div>
          <p className="text-sm text-muted-foreground animate-pulse">Initializing...</p>
        </div>
      </div>
    )
  }

  return (
    <SidebarContext.Provider value={{ isCollapsed, setIsCollapsed, isMobileOpen, setIsMobileOpen }}>
      <div className="flex h-screen overflow-hidden bg-background">
        {/* Desktop Sidebar - hidden on mobile */}
        <div className="hidden md:block">
          <Sidebar isCollapsed={isCollapsed} onToggle={() => setIsCollapsed(!isCollapsed)} />
        </div>

        {/* Mobile Sidebar - sheet overlay */}
        <MobileSidebar open={isMobileOpen} onOpenChange={setIsMobileOpen} />

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header onMobileMenuClick={() => setIsMobileOpen(true)} />
          <main className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6 bg-muted/30">
            {children}
          </main>
        </div>
      </div>
    </SidebarContext.Provider>
  )
}
