'use client'

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Globe,
  AlertTriangle,
  BarChart3,
  Menu,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { useSidebar } from '@/app/(dashboard)/layout'

/**
 * Native-style bottom tab bar for phones.
 *
 * On a phone the only way into the app was the hamburger sheet, which meant two
 * taps and a full-screen overlay for every navigation. These are the four
 * destinations worth reaching in one thumb tap; everything else stays behind
 * "More", which opens the same sheet the hamburger does.
 *
 * Hidden from md upwards, where the persistent sidebar already does this job.
 */

interface Tab {
  title: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  /** Match this route exactly. /dashboard is a prefix of every other route. */
  exact?: boolean
}

const TABS: Tab[] = [
  { title: 'Home', href: '/dashboard', icon: LayoutDashboard, exact: true },
  { title: 'Hosts', href: '/dashboard/proxy-hosts', icon: Globe },
  { title: 'Threats', href: '/dashboard/threats', icon: AlertTriangle },
  { title: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
]

export function MobileTabBar() {
  const pathname = usePathname()
  const { setIsMobileOpen } = useSidebar()

  const isTabActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(href + '/')

  // "More" lights up whenever you're somewhere that isn't one of the four tabs,
  // so the bar always shows where you are rather than nothing at all.
  const onNamedTab = TABS.some((t) => isTabActive(t.href, t.exact))

  return (
    <nav
      aria-label="Primary"
      className={cn(
        'md:hidden fixed inset-x-0 bottom-0 z-40',
        'border-t border-border bg-background/95 backdrop-blur',
        'supports-[backdrop-filter]:bg-background/80',
        // Clears the iPhone home indicator.
        'pb-[env(safe-area-inset-bottom)]',
      )}
    >
      <div className="flex items-stretch">
        {TABS.map(({ title, href, icon: Icon, exact }) => {
          const active = isTabActive(href, exact)
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={cn(
                // min-h keeps every tap target comfortably above 44px.
                'flex flex-1 flex-col items-center justify-center gap-1 min-h-[56px] px-1 py-2',
                'text-[11px] font-medium transition-colors',
                active
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground active:text-foreground',
              )}
            >
              <Icon className={cn('h-5 w-5', active && 'stroke-[2.5]')} />
              <span className="leading-none">{title}</span>
            </Link>
          )
        })}

        <button
          type="button"
          onClick={() => setIsMobileOpen(true)}
          aria-label="Open navigation menu"
          className={cn(
            'flex flex-1 flex-col items-center justify-center gap-1 min-h-[56px] px-1 py-2',
            'text-[11px] font-medium transition-colors',
            !onNamedTab
              ? 'text-primary'
              : 'text-muted-foreground hover:text-foreground active:text-foreground',
          )}
        >
          <Menu className={cn('h-5 w-5', !onNamedTab && 'stroke-[2.5]')} />
          <span className="leading-none">More</span>
        </button>
      </div>
    </nav>
  )
}

export default MobileTabBar
