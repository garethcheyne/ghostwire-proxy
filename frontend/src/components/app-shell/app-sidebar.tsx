"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { Sidebar, useSidebar } from "@/components/ui/sidebar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import {
  isNavItemActive,
  resolveNav,
  type AppShellProduct,
  type NavGroup,
  type NavItem,
  type NavSource,
} from "./types"

type Mode = "expanded" | "collapsed" | "mobile"

export interface AppSidebarProps {
  product: AppShellProduct
  nav: NavSource
  /** Shown in the footer ("Version 2026.10.28"). No footer without it. */
  version?: string | null
  /** Where the version links to, e.g. the About page. */
  aboutHref?: string
  /** Extra content under the logo bar, e.g. a team switcher. */
  top?: React.ReactNode
}

/** The persistent sidebar on desktop, and the slide-in sheet on phones. */
export function AppSidebar(props: AppSidebarProps) {
  const { isMobile, state, toggleSidebar, openMobile, setOpenMobile } = useSidebar()

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile}>
        {/* A flex column, not fixed heights: the sheet is `fixed`, so it gets the small viewport
            (what is visible), while 100vh is the large one. A scroll region sized in vh ran past
            the bottom of the sheet and the last entries were unreachable. */}
        <SheetContent side="left" className="flex max-w-[85vw] flex-col border-border bg-card p-0">
          <SheetTitle className="sr-only">{props.product.name ?? "Ghostwire"}</SheetTitle>
          <SidebarBody {...props} mode="mobile" onNavigate={() => setOpenMobile(false)} />
        </SheetContent>
      </Sheet>
    )
  }

  const collapsed = state === "collapsed"

  return (
    <Sidebar collapsible="icon" className="bg-card/95 text-foreground backdrop-blur-sm [--sidebar:transparent]">
      <SidebarBody {...props} mode={collapsed ? "collapsed" : "expanded"} />
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleSidebar}
        className="absolute -right-3 top-20 z-10 h-6 w-6 rounded-full border border-border bg-muted shadow-md hover:border-brand/50 hover:bg-accent"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        <span className="sr-only">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
      </Button>
    </Sidebar>
  )
}

function SidebarBody({
  product,
  nav,
  version,
  aboutHref,
  top,
  mode,
  onNavigate,
}: AppSidebarProps & { mode: Mode; onNavigate?: () => void }) {
  const pathname = usePathname()
  const { groups, back } = resolveNav(nav, pathname)
  const all: NavGroup[] = back
    ? [{ title: "", items: [{ ...back, icon: ArrowLeft, exact: true, badge: undefined }] }, ...groups]
    : groups
  const collapsed = mode === "collapsed"
  const mobile = mode === "mobile"

  return (
    <>
      <div className={cn("flex h-16 shrink-0 items-center justify-between border-b border-border px-4", !mobile && "overflow-hidden")}>
        <ProductLogo product={product} collapsed={collapsed} onNavigate={onNavigate} />
      </div>

      {top}

      {/* min-h-0 lets the scroll region shrink below its content, so the logo bar and footer keep
          their size and the menu scrolls. */}
      <ScrollArea className="min-h-0 flex-1 py-4">
        {/* On phones the bottom padding clears the home indicator so the last entry is tappable. */}
        <nav className={cn("space-y-6", mobile ? "px-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))]" : "px-2")}>
          {all.map((group, groupIdx) => (
            <div key={group.title || groupIdx}>
              {!collapsed && group.title && (
                <h4 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.title}
                </h4>
              )}
              <div className="flex flex-col">
                {group.items.map((item) => (
                  <NavLink
                    key={item.href}
                    item={item}
                    active={isNavItemActive(item, pathname)}
                    mode={mode}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
              {!collapsed && groupIdx < all.length - 1 && (
                <Separator className={cn("my-4", mobile ? "bg-border" : "bg-border/50")} />
              )}
            </div>
          ))}
        </nav>
      </ScrollArea>

      {version && !mobile && <VersionFooter product={product} version={version} aboutHref={aboutHref} collapsed={collapsed} />}
    </>
  )
}

function ProductLogo({
  product,
  collapsed,
  onNavigate,
}: {
  product: AppShellProduct
  collapsed: boolean
  onNavigate?: () => void
}) {
  const alt = `${product.name ?? "Ghostwire"} logo`
  const mark = "h-8 w-8 object-contain"

  return (
    <Link href={product.href} className="flex min-w-0 items-center gap-2" onClick={onNavigate}>
      <div className="relative h-8 w-8 shrink-0">
        {product.logoLight ? (
          <>
            <Image src={product.logoLight} alt={alt} width={32} height={32} className={cn(mark, "dark:hidden")} />
            <Image src={product.logo} alt={alt} width={32} height={32} className={cn(mark, "hidden dark:block")} />
          </>
        ) : (
          <Image src={product.logo} alt={alt} width={32} height={32} className={mark} />
        )}
      </div>
      {!collapsed && (
        <div className="flex min-w-0 flex-col">
          <span className="text-xl font-bold leading-tight text-brand-gradient">Ghostwire</span>
          {/* One line, always: a long product line is cut with an ellipsis rather than wrapping. */}
          <span className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
            {product.line}
          </span>
        </div>
      )}
    </Link>
  )
}

function NavLink({
  item,
  active,
  mode,
  onNavigate,
}: {
  item: NavItem
  active: boolean
  mode: Mode
  onNavigate?: () => void
}) {
  const Icon = item.icon
  const count = item.badge && item.badge > 0 ? item.badge : 0
  const colours = active ? "nav-active" : "text-muted-foreground hover:bg-accent hover:text-brand"

  if (mode === "collapsed") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            asChild
            variant={active ? "secondary" : "ghost"}
            size="icon"
            className={cn("relative w-full transition-all duration-200", colours)}
          >
            <Link href={item.href} aria-current={active ? "page" : undefined}>
              <Icon className="h-5 w-5" />
              {count > 0 && <span className="absolute right-2.5 top-1 size-2 rounded-full bg-red-500" />}
              <span className="sr-only">{item.title}</span>
            </Link>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={10}>
          {item.title}
          {count > 0 && ` (${count})`}
        </TooltipContent>
      </Tooltip>
    )
  }

  const mobile = mode === "mobile"

  return (
    <Button
      asChild
      variant={active ? "secondary" : "ghost"}
      className={cn("w-full justify-start transition-all duration-200", mobile && "h-11", colours)}
    >
      <Link href={item.href} aria-current={active ? "page" : undefined} onClick={onNavigate}>
        <Icon className={cn("h-5 w-5", mobile ? "mr-3" : "mr-2")} />
        <span className={cn("truncate", mobile && "text-sm")}>{item.title}</span>
        {count > 0 && (
          <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </Link>
    </Button>
  )
}

function VersionFooter({
  product,
  version,
  aboutHref,
  collapsed,
}: {
  product: AppShellProduct
  version: string
  aboutHref?: string
  collapsed: boolean
}) {
  // A link to the About page when there is one. Built inline (not as a component) so the tooltip
  // trigger can pass its handlers and ref straight to the element.
  const versionLink = (className: string, children: React.ReactNode) =>
    aboutHref ? (
      <Link href={aboutHref} className={className}>
        {children}
      </Link>
    ) : (
      <div className={className}>{children}</div>
    )

  return (
    <div className="shrink-0 border-t border-border px-4 py-3">
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>
            {versionLink(
              "block text-center",
              <span className="font-mono text-[10px] text-muted-foreground transition-colors hover:text-brand">
                v{version.split(".").pop()}
              </span>
            )}
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            {product.name ?? "Ghostwire"} v{version}
          </TooltipContent>
        </Tooltip>
      ) : (
        versionLink(
          "group block",
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Version</span>
            <span className="font-mono text-[10px] text-muted-foreground transition-colors group-hover:text-brand">
              {version}
            </span>
          </div>
        )
      )}
    </div>
  )
}
