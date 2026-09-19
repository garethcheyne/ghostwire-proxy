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
  Boxes,
  Tag,
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

interface MobileSidebarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function MobileSidebar({ open, onOpenChange }: MobileSidebarProps) {
  const pathname = usePathname()

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Flex column, not fixed heights. The scroll region below sizes itself
          from whatever the sheet actually is, which is the only thing that
          works on a phone: the sheet is `fixed`, so it gets the *small*
          viewport (visible area), while `100vh` resolves to the *large* one
          (as if the browser chrome were hidden). Sizing the scroll region in
          vh made it taller than its own parent, so the last ~100px of the menu
          was clipped with no scrollbar — the bottom entries were unreachable. */}
      <SheetContent
        side="left"
        className="flex w-[280px] max-w-[85vw] flex-col p-0 bg-card/98 border-border backdrop-blur-xl"
      >
        <SheetHeader className="flex h-16 shrink-0 items-center justify-between border-b border-border px-4">
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
              <span className="text-xl font-bold text-brand-gradient leading-tight">
                Ghostwire
              </span>
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-normal">
                Reverse Proxy Manager
              </span>
            </SheetTitle>
          </Link>
        </SheetHeader>

        {/* min-h-0 is load-bearing: without it a flex child refuses to shrink
            below its content height and the scroll region grows past the sheet
            again. */}
        <ScrollArea className="min-h-0 flex-1 py-4">
          {/* Bottom padding clears the home indicator so the last entry is
              both readable and tappable. */}
          <nav className="space-y-6 px-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
            {navigation.map((group, groupIdx) => (
              <div key={group.title}>
                <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.title}
                </h4>
                <div className="space-y-1">
                  {group.items.map((item) => {
                    // The Dashboard link is the parent of every page, so it's only active on itself.
                    const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href + '/'))
                    const Icon = item.icon

                    return (
                      <Link key={item.href} href={item.href} onClick={() => onOpenChange(false)}>
                        <Button
                          variant={isActive ? 'secondary' : 'ghost'}
                          className={cn(
                            'w-full justify-start transition-all duration-200 h-11',
                            isActive
                              ? 'nav-active'
                              : 'hover:bg-accent hover:text-brand text-muted-foreground'
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
                  <Separator className="my-4 bg-border" />
                )}
              </div>
            ))}
          </nav>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
