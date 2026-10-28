"use client"

import * as React from "react"
import { Menu } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useSidebar } from "@/components/ui/sidebar"
import { ThemeToggle } from "./theme-toggle"

export interface AppHeaderProps {
  /** Left, after the phone menu button: search, breadcrumb, page title. */
  start?: React.ReactNode
  /** Right, before the theme toggle: the app's own buttons (notifications, kill switch). */
  actions?: React.ReactNode
  /** Far right, after the theme toggle: the user menu. */
  userMenu?: React.ReactNode
}

/** The top bar of every Ghostwire app. */
export function AppHeader({ start, actions, userMenu }: AppHeaderProps) {
  const { setOpenMobile } = useSidebar()

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-background/95 px-3 backdrop-blur-sm supports-backdrop-filter:bg-background/60 sm:h-16 sm:px-6">
      <div className="flex items-center gap-2 sm:gap-4">
        <Button variant="ghost" size="icon" className="h-9 w-9 md:hidden" onClick={() => setOpenMobile(true)}>
          <Menu className="h-5 w-5" />
          <span className="sr-only">Open menu</span>
        </Button>
        {start}
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        {actions}
        <ThemeToggle />
        {userMenu}
      </div>
    </header>
  )
}
