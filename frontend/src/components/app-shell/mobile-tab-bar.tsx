"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Menu } from "lucide-react"

import { cn } from "@/lib/utils"
import { useSidebar } from "@/components/ui/sidebar"
import { isNavItemActive, type NavItem } from "./types"

/**
 * Native-style bottom tab bar for phones: the destinations worth one thumb tap, then "More", which
 * opens the same sheet as the header's menu button. Hidden from md upwards, where the sidebar
 * does this job.
 *
 * Sizing: 64px of bar plus the safe-area inset. The shell's spacer under the page and the app's
 * toast offset both assume that height; change one and change them all.
 */
export function MobileTabBar({ tabs }: { tabs: NavItem[] }) {
  const pathname = usePathname()
  const { setOpenMobile } = useSidebar()

  // "More" lights up whenever you're somewhere that isn't one of the tabs, so the bar always
  // shows where you are.
  const onNamedTab = tabs.some((tab) => isNavItemActive(tab, pathname))
  const tabClass = (active: boolean) =>
    cn(
      // min-h keeps every tap target comfortably above 44px.
      "flex min-h-[64px] min-w-0 flex-1 flex-col items-center justify-center gap-1.5 px-1 py-2.5",
      "text-xs font-medium transition-colors",
      active ? "text-primary" : "text-muted-foreground hover:text-foreground active:text-foreground"
    )

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "fixed inset-x-0 bottom-0 z-40 md:hidden",
        "border-t border-border bg-background/95 backdrop-blur-sm",
        "supports-backdrop-filter:bg-background/80",
        // Clears the iPhone home indicator.
        "pb-[env(safe-area-inset-bottom)]"
      )}
    >
      <div className="flex items-stretch">
        {tabs.map((tab) => {
          const active = isNavItemActive(tab, pathname)
          const Icon = tab.icon
          return (
            <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined} className={tabClass(active)}>
              <Icon className={cn("h-6 w-6 shrink-0", active && "stroke-[2.5]")} />
              <span className="max-w-full truncate leading-none">{tab.title}</span>
            </Link>
          )
        })}

        <button
          type="button"
          onClick={() => setOpenMobile(true)}
          aria-label="Open navigation menu"
          className={tabClass(!onNamedTab)}
        >
          <Menu className={cn("h-6 w-6 shrink-0", !onNamedTab && "stroke-[2.5]")} />
          <span className="max-w-full truncate leading-none">More</span>
        </button>
      </div>
    </nav>
  )
}
