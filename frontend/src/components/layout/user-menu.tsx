'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { LogOut, Settings, Activity } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import api from '@/lib/api'
import { signOutAndRedirect } from '@/lib/session'

/** The signed-in admin's avatar and account menu, at the far right of the header. */
export function UserMenu() {
  const [user, setUser] = useState<{ name: string; email: string } | null>(null)

  const fetchUser = async () => {
    try {
      const response = await api.get('/api/users/me')
      setUser(response.data)
    } catch {
      // Ignore errors
    }
  }

  useEffect(() => {
    fetchUser()
  }, [])

  const handleLogout = async () => {
    // Ends the Better Auth session (audit-logged by the auth server) and clears the client.
    await signOutAndRedirect()
  }

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <div className="flex items-center gap-2 sm:gap-3 border-l pl-2 sm:pl-4 cursor-pointer">
          <div className="hidden sm:text-right lg:block">
            <p className="text-sm font-medium truncate max-w-[120px]" data-private="name">{user?.name || 'Admin'}</p>
            <p className="text-xs text-muted-foreground truncate max-w-[120px]" data-private="email">{user?.email || 'admin@proxy.local'}</p>
          </div>
          <Avatar className="h-8 w-8 sm:h-9 sm:w-9">
            <AvatarImage src="" alt={user?.name || 'User'} />
            <AvatarFallback className="bg-primary text-primary-foreground text-xs sm:text-sm">
              {user?.name ? getInitials(user.name) : 'AD'}
            </AvatarFallback>
          </Avatar>
        </div>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>My Account</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/dashboard/settings" className="cursor-pointer">
            <Settings className="mr-2 h-4 w-4" />
            <span>Settings</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/dashboard/analytics" className="cursor-pointer">
            <Activity className="mr-2 h-4 w-4" />
            <span>Analytics</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive cursor-pointer"
          onClick={handleLogout}
        >
          <LogOut className="mr-2 h-4 w-4" />
          <span>Sign out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
