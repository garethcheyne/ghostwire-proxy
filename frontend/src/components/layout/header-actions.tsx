'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  Bell,
  Power,
  AlertTriangle,
  ExternalLink,
  Ban,
  Wrench,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import api from '@/lib/api'
import { usePageData } from '@/lib/use-page-data'
import { cn } from '@/lib/utils'

/** The proxy's own header buttons: the kill switch (with its dialog and banner) and traffic logs. */
export function HeaderActions() {
  const [killSwitchActive, setKillSwitchActive] = useState(false)
  const [killSwitchMode, setKillSwitchMode] = useState<string>('maintenance')
  const [killSwitchRedirectUrl, setKillSwitchRedirectUrl] = useState('')
  const [showKillSwitchDialog, setShowKillSwitchDialog] = useState(false)
  const [isToggling, setIsToggling] = useState(false)

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

  usePageData(fetchKillSwitchStatus)

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

  return (
    <>
      {/* Kill Switch Button - Always visible with strong indicator */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={killSwitchActive ? 'destructive' : 'ghost'}
            size="icon"
            onClick={() => setShowKillSwitchDialog(true)}
            className="relative h-9 w-9"
          >
            <Power className="h-5 w-5" />
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

      {/* Kill Switch Confirmation Dialog */}
      <Dialog open={showKillSwitchDialog} onOpenChange={setShowKillSwitchDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {killSwitchActive ? (
                <>
                  <Power className="h-5 w-5 text-green-600 dark:text-green-400" />
                  Deactivate Kill Switch
                </>
              ) : (
                <>
                  <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  Activate Kill Switch
                </>
              )}
            </DialogTitle>
            <DialogDescription className="pt-2">
              {killSwitchActive ? (
                <span>
                  The kill switch is currently <strong className="text-red-600 dark:text-red-400">ACTIVE</strong> in <strong>{killSwitchMode}</strong> mode.
                  Deactivating will restore normal traffic flow.
                </span>
              ) : (
                <span>
                  Activating the kill switch will <strong className="text-red-600 dark:text-red-400">immediately affect ALL proxy traffic</strong>.
                  Choose how traffic should be handled.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {/* Mode selection - only show when activating */}
          {!killSwitchActive && (
            <div className="space-y-3 pt-2">
              <Label className="text-sm font-medium">Mode</Label>
              <Tabs value={killSwitchMode} onValueChange={setKillSwitchMode}>
                <TabsList aria-label="Kill switch mode" className="grid w-full grid-cols-3 sm:w-full">
                  {([
                    { value: 'maintenance', label: 'Maintenance', hint: '503 page', icon: Wrench },
                    { value: 'redirect', label: 'Redirect', hint: '301 to URL', icon: ExternalLink },
                    { value: 'drop', label: 'Drop', hint: 'No response', icon: Ban },
                  ] as const).map(({ value, label, hint, icon: Icon }) => (
                    <TabsTrigger key={value} value={value} className="h-auto flex-col gap-1 py-2.5">
                      <Icon className="size-5" />
                      <span>{label}</span>
                      <span className="text-[10px] font-normal text-muted-foreground">{hint}</span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>

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
              className="min-w-[140px]"
            >
              {isToggling ? (
                <>
                  <Loader2 className="animate-spin" />
                  Processing...
                </>
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
    </>
  )
}
