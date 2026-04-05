'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  LayoutDashboard,
  Globe,
  Shield,
  Key,
  Settings,
  Cloud,
  Users,
  BarChart3,
  ShieldAlert,
  AlertTriangle,
  Flame,
  Monitor,
  Info,
  Bell,
  BookOpen,
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
      { title: 'Firewalls', href: '/dashboard/firewalls', icon: Flame },
    ],
  },
  {
    title: 'Monitoring',
    items: [
      { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
      { title: 'Alerts', href: '/dashboard/alerts', icon: Bell },
      { title: 'System', href: '/dashboard/system', icon: Monitor },
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

interface MobileSidebarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function MobileSidebar({ open, onOpenChange }: MobileSidebarProps) {
  const pathname = usePathname()

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="w-[280px] p-0 bg-slate-900/98 border-slate-700/50 backdrop-blur-xl"
      >
        <SheetHeader className="flex h-16 items-center justify-between border-b border-slate-700/50 px-4">
          <Link href="/dashboard" className="flex items-center gap-2" onClick={() => onOpenChange(false)}>
            <div className="relative h-8 w-8">
              <Image
                src="/logo.png"
                alt="Ghostwire Logo"
                width={32}
                height={32}
                className="h-8 w-8 object-contain"
              />
            </div>
            <SheetTitle className="flex flex-col">
              <span className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent leading-tight">
                Ghostwire
              </span>
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-normal">
                Reverse Proxy Manager
              </span>
            </SheetTitle>
          </Link>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-4rem)] py-4">
          <nav className="space-y-6 px-3">
            {navigation.map((group, groupIdx) => (
              <div key={group.title}>
                <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  {group.title}
                </h4>
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
                    const Icon = item.icon

                    return (
                      <Link key={item.href} href={item.href} onClick={() => onOpenChange(false)}>
                        <Button
                          variant={isActive ? 'secondary' : 'ghost'}
                          className={cn(
                            'w-full justify-start transition-all duration-200 h-11',
                            isActive
                              ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-cyan-400 border border-cyan-500/30'
                              : 'hover:bg-slate-800 hover:text-cyan-400 text-slate-400'
                          )}
                        >
                          <Icon className="mr-3 h-5 w-5" />
                          <span className="text-sm">{item.title}</span>
                        </Button>
                      </Link>
                    )
                  })}
                </div>
                {groupIdx < navigation.length - 1 && (
                  <Separator className="my-4 bg-slate-700/50" />
                )}
              </div>
            ))}
          </nav>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
