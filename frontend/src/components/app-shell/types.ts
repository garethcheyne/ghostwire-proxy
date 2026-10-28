import type * as React from "react"

/** Any icon component: lucide icons, or your own that take a className. */
export type NavIcon = React.ComponentType<{ className?: string }>

export interface NavItem {
  title: string
  href: string
  icon: NavIcon
  /**
   * Active only on this exact path. Set it on the dashboard/home link: it is the parent of every
   * page, so a prefix match would light it up everywhere.
   */
  exact?: boolean
  /** A count shown as a small red pill (a dot on the icon when the sidebar is collapsed). */
  badge?: number
}

export interface NavGroup {
  /** The small uppercase label above the group. Leave empty for a group with no label. */
  title: string
  items: NavItem[]
}

/** The sidebar for one page: its groups, and an optional "back" link shown above them. */
export interface NavConfig {
  groups: NavGroup[]
  back?: NavItem
}

/**
 * The sidebar's contents: a fixed list of groups, or a function of the current path for apps whose
 * sidebar changes by section (a website's own menu, settings, admin).
 */
export type NavSource = NavGroup[] | ((pathname: string) => NavGroup[] | NavConfig)

export interface AppShellProduct {
  /** The full product name, for the logo's alt text and the version tooltip. Default "Ghostwire". */
  name?: string
  /** The product line under the wordmark: "Reverse proxy manager", "Analytics". Shown uppercase. */
  line: string
  /** The badged mark for dark mode (sky ghost), e.g. "/logo.png". */
  logo: string
  /** The badged mark for light mode (black ghost), e.g. "/logo-black.png". Omit to use `logo` in both. */
  logoLight?: string
  /** Where the logo links to: the app's home. */
  href: string
}

/** Prefix match on whole path segments, or an exact match for items flagged `exact`. */
export function isNavItemActive(item: Pick<NavItem, "href" | "exact">, pathname: string) {
  if (item.exact) return pathname === item.href
  return pathname === item.href || pathname.startsWith(`${item.href}/`)
}

export function resolveNav(nav: NavSource, pathname: string): NavConfig {
  const resolved = typeof nav === "function" ? nav(pathname) : nav
  return Array.isArray(resolved) ? { groups: resolved } : resolved
}
