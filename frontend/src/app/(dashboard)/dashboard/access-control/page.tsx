'use client'

import { useState } from 'react'
import { Key, Lock, Shield } from 'lucide-react'
import dynamic from 'next/dynamic'

// Dynamic imports to avoid code duplication - load the existing pages as components
const AuthWallsContent = dynamic(() => import('../auth-walls/page'), { ssr: false })
const AccessListsContent = dynamic(() => import('../access-lists/page'), { ssr: false })

type TabType = 'auth-walls' | 'ip-lists'

export default function AccessControlPage() {
  const [activeTab, setActiveTab] = useState<TabType>('auth-walls')

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2">
          <Shield className="h-6 w-6 text-cyan-400" />
          Access Control
        </h1>
        <p className="text-sm sm:text-base text-muted-foreground">
          Manage authentication walls and IP access lists
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        <button
          data-value="auth-walls"
          onClick={() => setActiveTab('auth-walls')}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'auth-walls'
              ? 'bg-background shadow-sm'
              : 'hover:bg-background/50 text-muted-foreground'
          }`}
        >
          <Key className="h-4 w-4" />
          <span className="hidden sm:inline">Auth Walls</span>
          <span className="sm:hidden">Auth</span>
        </button>
        <button
          data-value="ip-lists"
          onClick={() => setActiveTab('ip-lists')}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'ip-lists'
              ? 'bg-background shadow-sm'
              : 'hover:bg-background/50 text-muted-foreground'
          }`}
        >
          <Lock className="h-4 w-4" />
          <span className="hidden sm:inline">IP Access Lists</span>
          <span className="sm:hidden">IP Lists</span>
        </button>
      </div>

      {/* Tab Content */}
      <div className="[&>div>div:first-child]:hidden">
        {activeTab === 'auth-walls' && <AuthWallsContent />}
        {activeTab === 'ip-lists' && <AccessListsContent />}
      </div>
    </div>
  )
}
