"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { SidebarProvider } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppHeader } from "./app-header"
import { AppSidebar } from "./app-sidebar"
import { MobileTabBar } from "./mobile-tab-bar"
import { SIDEBAR_COOKIE, type AppShellProduct, type NavItem, type NavSource } from "./types"

export { SIDEBAR_COOKIE }

export interface AppShellProps {
  product: AppShellProduct
  /** The sidebar's groups, or a function of the current path (see NavSource). */
  nav: NavSource
  /** Phone bottom bar: up to four destinations; a fifth "More" tab opens the sidebar. Omit for no bar. */
  mobileTabs?: NavItem[]
  /** Shown in the sidebar footer. No footer while it's empty (e.g. still loading). */
  version?: string | null
  /** Where the version in the footer links to. */
  aboutHref?: string
  /** Header, left (after the phone menu button): search, breadcrumb, page title. */
  headerStart?: React.ReactNode
  /** Header, right, before the theme toggle: notifications and other app buttons. */
  headerActions?: React.ReactNode
  /** Header, far right, after the theme toggle: the user menu. */
  userMenu?: React.ReactNode
  /** Under the header, above the page: app-wide notices such as an update banner. */
  banner?: React.ReactNode
  /** Under the logo bar in the sidebar, e.g. a team switcher. Use useSidebar() for its state. */
  sidebarTop?: React.ReactNode
  /**
   * Whether the sidebar starts expanded. A server layout passes the cookie
   * (`cookies().get(SIDEBAR_COOKIE)?.value !== "false"`); when omitted the shell reads the cookie
   * in the browser, which is right for shells only rendered on the client.
   */
  defaultOpen?: boolean
  /** Extra classes/style for the scrolling page area (e.g. a margin for a docked panel). */
  mainClassName?: string
  mainStyle?: React.CSSProperties
  children: React.ReactNode
}

function readSidebarCookie() {
  if (typeof document === "undefined") return true
  return !document.cookie.split("; ").includes(`${SIDEBAR_COOKIE}=false`)
}

/** The frame of every Ghostwire app: sidebar, top header, phone navigation and the page area. */
export function AppShell({
  product,
  nav,
  mobileTabs,
  version,
  aboutHref,
  headerStart,
  headerActions,
  userMenu,
  banner,
  sidebarTop,
  defaultOpen,
  mainClassName,
  mainStyle,
  children,
}: AppShellProps) {
  const [initialOpen] = React.useState(() => defaultOpen ?? readSidebarCookie())
  const tabs = mobileTabs?.length ? mobileTabs : null

  return (
    <TooltipProvider delayDuration={0}>
      <SidebarProvider
        defaultOpen={initialOpen}
        style={{ "--sidebar-width": "16rem", "--sidebar-width-icon": "4rem" } as React.CSSProperties}
        className={cn(
          // 100vh on a phone is the height with the browser chrome hidden, taller than what you
          // can see; with overflow-hidden that put the bottom of the shell under the URL bar. dvh
          // tracks the visible height, with vh as the fallback.
          "h-screen overflow-hidden bg-background supports-[height:100dvh]:h-dvh",
          // Collapse at the same pace as the sidebar always has.
          "[&_[data-slot=sidebar-container]]:duration-300 [&_[data-slot=sidebar-container]]:ease-in-out",
          "[&_[data-slot=sidebar-gap]]:duration-300 [&_[data-slot=sidebar-gap]]:ease-in-out"
        )}
      >
        <AppSidebar product={product} nav={nav} version={version} aboutHref={aboutHref} top={sidebarTop} />

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <AppHeader start={headerStart} actions={headerActions} userMenu={userMenu} />
          {banner}
          <main className={cn("flex-1 overflow-y-auto bg-muted/30 p-3 sm:p-4 md:p-6", mainClassName)} style={mainStyle}>
            {children}
            {/* Clears the fixed bottom tab bar (and the home indicator below it) so the last
                element on a page is never unreachable. */}
            {tabs && <div aria-hidden className="h-[calc(64px+env(safe-area-inset-bottom))] md:hidden" />}
          </main>
        </div>

        {tabs && <MobileTabBar tabs={tabs} />}
      </SidebarProvider>
    </TooltipProvider>
  )
}
