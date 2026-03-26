'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import {
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Rocket,
  Globe,
  Shield,
  BarChart3,
  Settings,
  FileText,
} from 'lucide-react'
import { useState } from 'react'

interface NavChild {
  slug: string
  title: string
}

interface NavSection {
  slug: string
  title: string
  icon?: string
  children?: NavChild[]
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Rocket,
  Globe,
  Shield,
  BarChart3,
  Settings,
  BookOpen,
}

function getIcon(name?: string) {
  if (!name) return FileText
  return ICON_MAP[name] || FileText
}

export function DocsSidebar({ navigation }: { navigation: NavSection[] }) {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const toggle = (slug: string) => {
    setCollapsed(prev => ({ ...prev, [slug]: !prev[slug] }))
  }

  return (
    <div className="w-64 border-r border-border bg-card/50 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 h-14 border-b border-border shrink-0">
        <BookOpen className="h-5 w-5 text-cyan-400" />
        <span className="font-semibold text-sm">Documentation</span>
      </div>

      <ScrollArea className="flex-1">
        <nav className="p-3 space-y-1">
          {/* Overview link */}
          <Link href="/dashboard/docs">
            <Button
              variant={pathname === '/dashboard/docs' ? 'secondary' : 'ghost'}
              size="sm"
              className={cn(
                'w-full justify-start text-sm',
                pathname === '/dashboard/docs'
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <BookOpen className="mr-2 h-4 w-4" />
              Overview
            </Button>
          </Link>

          {/* Sections */}
          {navigation.map((section) => {
            const Icon = getIcon(section.icon)
            const sectionPath = `/dashboard/docs/${section.slug}`
            const isInSection = pathname.startsWith(sectionPath)
            const isExpanded = !collapsed[section.slug] && (isInSection || collapsed[section.slug] === undefined)

            return (
              <div key={section.slug}>
                <button
                  onClick={() => toggle(section.slug)}
                  className={cn(
                    'flex items-center w-full px-3 py-2 text-sm rounded-md transition-colors',
                    isInSection
                      ? 'text-cyan-400 font-medium'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  )}
                >
                  <Icon className="mr-2 h-4 w-4 shrink-0" />
                  <span className="flex-1 text-left">{section.title}</span>
                  {section.children && section.children.length > 0 && (
                    <span className="ml-auto">
                      {isExpanded ? (
                        <ChevronRight className="h-3 w-3 rotate-90 transition-transform" />
                      ) : (
                        <ChevronRight className="h-3 w-3 transition-transform" />
                      )}
                    </span>
                  )}
                </button>

                {/* Children */}
                {isExpanded && section.children && (
                  <div className="ml-4 pl-3 border-l border-border/50 space-y-0.5 mt-0.5">
                    {section.children.map((child) => {
                      const childPath = `/dashboard/docs/${section.slug}/${child.slug}`
                      const isActive = pathname === childPath

                      return (
                        <Link key={child.slug} href={childPath}>
                          <Button
                            variant="ghost"
                            size="sm"
                            className={cn(
                              'w-full justify-start text-xs h-8 font-normal',
                              isActive
                                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                                : 'text-muted-foreground hover:text-foreground'
                            )}
                          >
                            {child.title}
                          </Button>
                        </Link>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </nav>
      </ScrollArea>

      {/* Back to dashboard */}
      <div className="border-t border-border p-3 shrink-0">
        <Link href="/dashboard">
          <Button variant="ghost" size="sm" className="w-full justify-start text-xs text-muted-foreground">
            <ChevronLeft className="mr-1 h-3 w-3" />
            Back to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  )
}
