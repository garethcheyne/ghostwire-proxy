'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip'
import {
  LayoutDashboard,
  Globe,
  Shield,
  Lock,
  Key,
  Tag,
  Activity,
  Settings,
  ChevronLeft,
  ChevronRight,
  Cloud,
  Users,
  BarChart3,
  ShieldAlert,
  AlertTriangle,
  Flame,
  Map,
  Gauge,
  Monitor,
  Boxes,
  Sparkles,
  Download,
  Bug,
  Info,
  FileText,
  Bell,
  BookOpen,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '@/lib/api'

interface NavItem {
  title: string
  href: string
  icon: React.ComponentType<{ className?: string }>
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const navigation: NavGroup[] = [
  {
    title: 'Overview',
    items: [
      { title: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    title: 'Proxy',
    items: [
      { title: 'Hosts', href: '/dashboard/proxy-hosts', icon: Globe },
      { title: 'Certificates', href: '/dashboard/certificates', icon: Shield },
      { title: 'DNS Providers', href: '/dashboard/dns', icon: Cloud },
    ],
  },
  {
    title: 'Security',
    items: [
      { title: 'Threats', href: '/dashboard/threats', icon: AlertTriangle },
      { title: 'Rules', href: '/dashboard/rules', icon: ShieldAlert },
      { title: 'Access Control', href: '/dashboard/access-control', icon: Key },
      { title: 'Known IPs', href: '/dashboard/known-ips', icon: Tag },
      { title: 'Firewalls', href: '/dashboard/firewalls', icon: Flame },
    ],
  },
  {
    title: 'Monitoring',
    items: [
      { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
      { title: 'Alerts', href: '/dashboard/alerts', icon: Bell },
      { title: 'System', href: '/dashboard/system', icon: Monitor },
      { title: 'Containers', href: '/dashboard/containers', icon: Boxes },
    ],
  },
  {
    title: 'Administration',
    items: [
      { title: 'Users', href: '/dashboard/users', icon: Users },
      { title: 'Settings', href: '/dashboard/settings', icon: Settings },
      { title: 'About', href: '/dashboard/about', icon: Info },
    ],
  },
  {
    title: 'Help',
    items: [
      { title: 'Documentation', href: '/dashboard/docs', icon: BookOpen },
    ],
  },
]

interface SidebarProps {
  isCollapsed: boolean
  onToggle: () => void
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const pathname = usePathname()
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    api.get('/version').then(res => setVersion(res.data.version)).catch(() => {})
  }, [])

  return (
    <TooltipProvider delayDuration={0} key={isCollapsed ? 'collapsed' : 'expanded'}>
      <div
        className={cn(
          'relative flex h-full flex-col border-r border-border bg-card/95 backdrop-blur transition-all duration-300',
          isCollapsed ? 'w-16' : 'w-64'
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center justify-between border-b border-border px-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="relative h-8 w-8">
              <Image
                src="/logo.png"
                alt="Ghostwire Logo"
                width={32}
                height={32}
                className="h-8 w-8 object-contain"
              />
            </div>
            {!isCollapsed && (
              <div className="flex flex-col">
                <span className="text-xl font-bold text-brand-gradient leading-tight">
                  Ghostwire
                </span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  Reverse Proxy Manager
                </span>
              </div>
            )}
          </Link>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1 py-4">
          <nav className="space-y-6 px-2">
            {navigation.map((group, groupIdx) => (
              <div key={group.title}>
                {!isCollapsed && (
                  <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {group.title}
                  </h4>
                )}
                <div className="space-y-1">
                  {group.items.map((item) => {
                    // The Dashboard link is the parent of every page, so it's only active on itself.
                    const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href + '/'))
                    const Icon = item.icon

                    if (isCollapsed) {
                      return (
                        <Tooltip key={item.href}>
                          <TooltipTrigger asChild>
                            <Link href={item.href}>
                              <Button
                                variant={isActive ? 'secondary' : 'ghost'}
                                size="icon"
                                className={cn(
                                  'w-full relative transition-all duration-200',
                                  isActive
                                    ? 'nav-active'
                                    : 'hover:bg-accent hover:text-brand text-muted-foreground'
                                )}
                              >
                                <Icon className="h-5 w-5" />
                              </Button>
                            </Link>
                          </TooltipTrigger>
                          <TooltipContent side="right" sideOffset={10}>
                            {item.title}
                          </TooltipContent>
                        </Tooltip>
                      )
                    }

                    return (
                      <Link key={item.href} href={item.href}>
                        <Button
                          variant={isActive ? 'secondary' : 'ghost'}
                          className={cn(
                            'w-full justify-start transition-all duration-200',
                            isActive
                              ? 'nav-active'
                              : 'hover:bg-accent hover:text-brand text-muted-foreground'
                          )}
                        >
                          <Icon className="mr-2 h-5 w-5" />
                          {item.title}
                        </Button>
                      </Link>
                    )
                  })}
                </div>
                {!isCollapsed && groupIdx < navigation.length - 1 && (
                  <Separator className="my-4 bg-border/50" />
                )}
              </div>
            ))}
          </nav>
        </ScrollArea>

        {/* Version Footer */}
        {version && (
          <div className="border-t border-border px-4 py-3">
            {isCollapsed ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link href="/dashboard/about" className="block text-center">
                    <span className="text-[10px] font-mono text-muted-foreground hover:text-brand transition-colors">
                      v{version.split('.').pop()}
                    </span>
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={10}>
                  Ghostwire Proxy v{version}
                </TooltipContent>
              </Tooltip>
            ) : (
              <Link href="/dashboard/about" className="group block">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Version</span>
                  <span className="text-[10px] font-mono text-muted-foreground group-hover:text-brand transition-colors">
                    {version}
                  </span>
                </div>
              </Link>
            )}
          </div>
        )}

        {/* Collapse Toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className="absolute -right-3 top-20 z-10 h-6 w-6 rounded-full border border-border bg-muted shadow-md hover:bg-accent hover:border-cyan-500/50"
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>
    </TooltipProvider>
  )
}
