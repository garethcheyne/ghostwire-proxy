'use client'

import Link from 'next/link'
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
} from 'lucide-react'

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
      { title: 'Proxy Hosts', href: '/dashboard/proxy-hosts', icon: Globe },
      { title: 'Certificates', href: '/dashboard/certificates', icon: Shield },
      { title: 'DNS', href: '/dashboard/dns', icon: Cloud },
    ],
  },
  {
    title: 'Security',
    items: [
      { title: 'WAF Rules', href: '/dashboard/waf', icon: ShieldAlert },
      { title: 'Threats', href: '/dashboard/threats', icon: AlertTriangle },
      { title: 'Firewalls', href: '/dashboard/firewalls', icon: Flame },
      { title: 'GeoIP Blocking', href: '/dashboard/geoip', icon: Map },
      { title: 'Rate Limiting', href: '/dashboard/rate-limits', icon: Gauge },
      { title: 'Access Lists', href: '/dashboard/access-lists', icon: Lock },
      { title: 'Auth Walls', href: '/dashboard/auth-walls', icon: Key },
    ],
  },
  {
    title: 'Monitoring',
    items: [
      { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
      { title: 'Traffic', href: '/dashboard/traffic', icon: Activity },
      { title: 'System', href: '/dashboard/system', icon: Monitor },
    ],
  },
  {
    title: 'Administration',
    items: [
      { title: 'Users', href: '/dashboard/users', icon: Users },
      { title: 'Settings', href: '/dashboard/settings', icon: Settings },
    ],
  },
]

interface SidebarProps {
  isCollapsed: boolean
  onToggle: () => void
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const pathname = usePathname()

  return (
    <TooltipProvider delayDuration={0} key={isCollapsed ? 'collapsed' : 'expanded'}>
      <div
        className={cn(
          'relative flex h-full flex-col border-r border-slate-700/50 bg-slate-900/95 backdrop-blur transition-all duration-300',
          isCollapsed ? 'w-16' : 'w-64'
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center justify-between border-b border-slate-700/50 px-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="relative h-8 w-8">
              <img
                src="/logo.png"
                alt="Ghostwire Logo"
                className="h-8 w-8 object-contain [filter:brightness(0)_saturate(100%)_invert(42%)_sepia(93%)_saturate(1352%)_hue-rotate(162deg)_brightness(95%)_contrast(106%)] dark:[filter:brightness(0)_saturate(100%)_invert(71%)_sepia(53%)_saturate(425%)_hue-rotate(162deg)_brightness(95%)_contrast(92%)]"
              />
            </div>
            {!isCollapsed && (
              <div className="flex flex-col">
                <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent leading-tight">
                  Ghostwire
                </span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">
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
                  <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    {group.title}
                  </h4>
                )}
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
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
                                    ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-cyan-400 border border-cyan-500/30'
                                    : 'hover:bg-slate-800 hover:text-cyan-400 text-slate-400'
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
                              ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-cyan-400 border border-cyan-500/30'
                              : 'hover:bg-slate-800 hover:text-cyan-400 text-slate-400'
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
                  <Separator className="my-4 bg-slate-700/50" />
                )}
              </div>
            ))}
          </nav>
        </ScrollArea>

        {/* Collapse Toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          className="absolute -right-3 top-20 z-10 h-6 w-6 rounded-full border border-slate-600 bg-slate-800 shadow-md hover:bg-slate-700 hover:border-cyan-500/50"
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
