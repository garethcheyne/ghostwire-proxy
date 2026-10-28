'use client'

import { useState } from 'react'
import { Key, Lock } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Key as HeaderIcon } from 'lucide-react'
import { AuthWallsPanel } from '@/components/access/auth-walls-panel'
import { AccessListsPanel } from '@/components/access/access-lists-panel'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

type TabType = 'auth-walls' | 'ip-lists'

export default function AccessControlPage() {
  const [activeTab, setActiveTab] = useState<TabType>('auth-walls')

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <PageHeader
        icon={HeaderIcon}
        title="Access Control"
        description="Manage authentication walls and IP access lists"
      />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="auth-walls">
            <Key className="h-4 w-4" />
            <span className="hidden sm:inline">Auth Walls</span>
            <span className="sm:hidden">Auth</span>
          </TabsTrigger>
          <TabsTrigger value="ip-lists">
            <Lock className="h-4 w-4" />
            <span className="hidden sm:inline">IP Access Lists</span>
            <span className="sm:hidden">IP Lists</span>
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Tab Content */}
      {activeTab === 'auth-walls' && <AuthWallsPanel embedded />}
      {activeTab === 'ip-lists' && <AccessListsPanel embedded />}
    </div>
  )
}
