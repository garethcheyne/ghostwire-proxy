'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  Bell,
  Search,
  LogOut,
  Moon,
  Sun,
  Settings,
  Activity,
  Menu,
  Power,
  AlertTriangle,
  ExternalLink,
  Ban,
  Wrench,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Link from 'next/link'
import api from '@/lib/api'
import { cn } from '@/lib/utils'
import { clearSession } from '@/lib/session'

interface HeaderProps {
  title?: string
  onMobileMenuClick?: () => void
}

export function Header({ title, onMobileMenuClick }: HeaderProps) {
  const router = useRouter()
  const { theme, setTheme } = useTheme()
  const [user, setUser] = useState<{ name: string; email: string } | null>(null)
  const [killSwitchActive, setKillSwitchActive] = useState(false)
  const [killSwitchMode, setKillSwitchMode] = useState<string>('maintenance')
  const [killSwitchRedirectUrl, setKillSwitchRedirectUrl] = useState('')
  const [showKillSwitchDialog, setShowKillSwitchDialog] = useState(false)
  const [isToggling, setIsToggling] = useState(false)

  useEffect(() => {
    fetchUser()
    fetchKillSwitchStatus()
  }, [])

  const fetchUser = async () => {
    try {
      const response = await api.get('/api/auth/me')
      setUser(response.data)
    } catch {
      // Ignore errors
    }
  }

  const fetchKillSwitchStatus = async () => {
    try {
      const response = await api.get('/api/system/kill-switch')
      setKillSwitchActive(response.data.active)
      if (response.data.mode) setKillSwitchMode(response.data.mode)
      if (response.data.redirect_url) setKillSwitchRedirectUrl(response.data.redirect_url)
    } catch {
      // Ignore errors - endpoint may not exist yet
    }
  }

  const toggleKillSwitch = async () => {
    if (!killSwitchActive && killSwitchMode === 'redirect' && !killSwitchRedirectUrl.trim()) return
    setIsToggling(true)
    try {
      const response = await api.post('/api/system/kill-switch', {
        active: !killSwitchActive,
        mode: killSwitchMode,
        redirect_url: killSwitchMode === 'redirect' ? killSwitchRedirectUrl : undefined,
      })
      setKillSwitchActive(response.data.active)
      setShowKillSwitchDialog(false)
    } catch (error) {
      console.error('Failed to toggle kill switch:', error)
    } finally {
      setIsToggling(false)
    }
  }

  const handleLogout = () => {
    clearSession()
    router.push('/auth/login')
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
    <TooltipProvider>
      <header className="sticky top-0 z-40 flex h-14 sm:h-16 items-center justify-between border-b bg-background/95 px-3 sm:px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        {/* Left side - Mobile menu + Page title or search */}
        <div className="flex items-center gap-2 sm:gap-4">
          {/* Mobile hamburger menu */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-9 w-9"
            onClick={onMobileMenuClick}
          >
            <Menu className="h-5 w-5" />
            <span className="sr-only">Open menu</span>
          </Button>

          {title && (
            <h1 className="text-lg sm:text-xl font-semibold truncate">{title}</h1>
          )}
          <div className="hidden lg:flex">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                placeholder="Search..."
                className="h-9 w-48 xl:w-64 rounded-md border bg-muted/50 pl-9 pr-4 text-sm outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center gap-1 sm:gap-2">
          {/* Kill Switch Button - Always visible with strong indicator */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={killSwitchActive ? 'destructive' : 'ghost'}
                size="icon"
                onClick={() => setShowKillSwitchDialog(true)}
                className={cn(
                  'relative h-9 w-9 transition-all duration-300',
                  killSwitchActive && 'animate-pulse bg-red-600 hover:bg-red-700 shadow-lg shadow-red-500/50'
                )}
              >
                <Power className={cn('h-5 w-5', killSwitchActive && 'text-white')} />
                {killSwitchActive && (
                  <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-red-400 animate-ping" />
                )}
                <span className="sr-only">Kill Switch</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {killSwitchActive ? 'Kill Switch ACTIVE - All traffic blocked' : 'Kill Switch - Block all traffic'}
            </TooltipContent>
          </Tooltip>

          {/* Theme toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              >
                <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                <span className="sr-only">Toggle theme</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Toggle theme</TooltipContent>
          </Tooltip>

          {/* Notifications */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Link href="/dashboard/traffic">
                <Button variant="ghost" size="icon" className="relative h-9 w-9">
                  <Bell className="h-5 w-5" />
                  <span className="sr-only">Notifications</span>
                </Button>
              </Link>
            </TooltipTrigger>
            <TooltipContent>Traffic logs</TooltipContent>
          </Tooltip>

          {/* User menu */}
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
        </div>
      </header>

      {/* Kill Switch Confirmation Dialog */}
      <Dialog open={showKillSwitchDialog} onOpenChange={setShowKillSwitchDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {killSwitchActive ? (
                <>
                  <Power className="h-5 w-5 text-green-500" />
                  Deactivate Kill Switch
                </>
              ) : (
                <>
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                  Activate Kill Switch
                </>
              )}
            </DialogTitle>
            <DialogDescription className="pt-2">
              {killSwitchActive ? (
                <span>
                  The kill switch is currently <strong className="text-red-500">ACTIVE</strong> in <strong>{killSwitchMode}</strong> mode.
                  Deactivating will restore normal traffic flow.
                </span>
              ) : (
                <span>
                  Activating the kill switch will <strong className="text-red-500">immediately affect ALL proxy traffic</strong>.
                  Choose how traffic should be handled.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {/* Mode selection - only show when activating */}
          {!killSwitchActive && (
            <div className="space-y-3 pt-2">
              <Label className="text-sm font-medium">Mode</Label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setKillSwitchMode('maintenance')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-lg border-2 p-3 text-sm transition-colors',
                    killSwitchMode === 'maintenance'
                      ? 'border-orange-500 bg-orange-500/10 text-orange-500'
                      : 'border-muted hover:border-muted-foreground/50'
                  )}
                >
                  <Wrench className="h-5 w-5" />
                  <span className="font-medium">Maintenance</span>
                  <span className="text-[10px] text-muted-foreground">503 page</span>
                </button>
                <button
                  type="button"
                  onClick={() => setKillSwitchMode('redirect')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-lg border-2 p-3 text-sm transition-colors',
                    killSwitchMode === 'redirect'
                      ? 'border-blue-500 bg-blue-500/10 text-blue-500'
                      : 'border-muted hover:border-muted-foreground/50'
                  )}
                >
                  <ExternalLink className="h-5 w-5" />
                  <span className="font-medium">Redirect</span>
                  <span className="text-[10px] text-muted-foreground">301 to URL</span>
                </button>
                <button
                  type="button"
                  onClick={() => setKillSwitchMode('drop')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-lg border-2 p-3 text-sm transition-colors',
                    killSwitchMode === 'drop'
                      ? 'border-red-500 bg-red-500/10 text-red-500'
                      : 'border-muted hover:border-muted-foreground/50'
                  )}
                >
                  <Ban className="h-5 w-5" />
                  <span className="font-medium">Drop</span>
                  <span className="text-[10px] text-muted-foreground">No response</span>
                </button>
              </div>

              {killSwitchMode === 'redirect' && (
                <div className="space-y-1.5">
                  <Label htmlFor="redirect-url" className="text-sm">Redirect URL</Label>
                  <Input
                    id="redirect-url"
                    placeholder="https://status.example.com"
                    value={killSwitchRedirectUrl}
                    onChange={(e) => setKillSwitchRedirectUrl(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}

          <DialogFooter className="flex-col sm:flex-row gap-2 pt-4">
            <Button
              variant="outline"
              onClick={() => setShowKillSwitchDialog(false)}
              disabled={isToggling}
            >
              Cancel
            </Button>
            <Button
              variant={killSwitchActive ? 'default' : 'destructive'}
              onClick={toggleKillSwitch}
              disabled={isToggling || (!killSwitchActive && killSwitchMode === 'redirect' && !killSwitchRedirectUrl.trim())}
              className={cn(
                'min-w-[140px]',
                !killSwitchActive && 'bg-red-600 hover:bg-red-700'
              )}
            >
              {isToggling ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Processing...
                </span>
              ) : killSwitchActive ? (
                'Restore Traffic'
              ) : (
                'Block All Traffic'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Kill Switch Active Banner */}
      {killSwitchActive && (
        <div className={cn(
          'fixed top-14 sm:top-16 left-0 right-0 z-50 text-white py-2 px-4 text-center text-sm font-medium animate-pulse',
          killSwitchMode === 'maintenance' && 'bg-orange-600',
          killSwitchMode === 'redirect' && 'bg-blue-600',
          killSwitchMode === 'drop' && 'bg-red-600',
          !killSwitchMode && 'bg-red-600',
        )}>
          <AlertTriangle className="inline-block h-4 w-4 mr-2 -mt-0.5" />
          KILL SWITCH ACTIVE — {killSwitchMode === 'maintenance' ? 'Showing maintenance page' : killSwitchMode === 'redirect' ? 'Redirecting all traffic' : 'Dropping all connections'}
          <Button
            variant="outline"
            size="sm"
            className="ml-4 h-6 text-xs bg-transparent border-white/50 hover:bg-white/20 text-white"
            onClick={() => setShowKillSwitchDialog(true)}
          >
            Restore
          </Button>
        </div>
      )}
    </TooltipProvider>
  )
}
