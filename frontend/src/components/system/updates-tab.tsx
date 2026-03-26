'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  ArrowUpCircle,
  Shield,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Download,
  RotateCcw,
  Settings2,
  Box,
  Activity,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import api from '@/lib/api'

interface AppRelease {
  version: string
  name?: string
  published_at?: string
  changelog?: string
  html_url?: string
  prerelease: boolean
}

interface AppUpdateCheck {
  current_version: string
  latest_version: string | null
  update_available: boolean
  releases: AppRelease[]
  error: string | null
}

interface BaseImageCheck {
  container: string
  image: string
  update_available: boolean
  current_digest: string | null
  latest_digest: string | null
  error: string | null
}

interface UpdateHistoryItem {
  id: string
  update_type: string
  from_version: string | null
  to_version: string | null
  container_name: string | null
  status: string
  progress_percent: number
  progress_message: string | null
  error_message: string | null
  can_rollback: boolean
  rollback_performed: boolean
  started_at: string
  completed_at: string | null
}

interface UpdateSettings {
  auto_check_enabled: boolean
  check_interval_hours: number
  notify_app_updates: boolean
  notify_security_updates: boolean
  notify_base_image_updates: boolean
  auto_update_security: boolean
  update_channel: string
  github_repo: string
}

export function UpdatesTab() {
  const [appCheck, setAppCheck] = useState<AppUpdateCheck | null>(null)
  const [baseCheck, setBaseCheck] = useState<BaseImageCheck[]>([])
  const [history, setHistory] = useState<UpdateHistoryItem[]>([])
  const [settings, setSettings] = useState<UpdateSettings | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const [isUpdating, setIsUpdating] = useState<string | null>(null)
  const [activeUpdate, setActiveUpdate] = useState<UpdateHistoryItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll active update progress
  useEffect(() => {
    if (!activeUpdate || ['completed', 'failed'].includes(activeUpdate.status)) return
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/updates/status/${activeUpdate.id}`)
        setActiveUpdate(res.data)
        if (['completed', 'failed'].includes(res.data.status)) {
          loadHistory()
        }
      } catch {}
    }, 3000)
    return () => clearInterval(interval)
  }, [activeUpdate])

  const loadAll = async () => {
    await Promise.all([loadSettings(), loadHistory()])
  }

  const loadSettings = async () => {
    try {
      const res = await api.get('/api/updates/settings')
      setSettings(res.data)
    } catch {}
  }

  const loadHistory = async () => {
    try {
      const res = await api.get('/api/updates/history?limit=10')
      setHistory(res.data)
      // Check for in-progress updates
      const inProgress = res.data.find(
        (u: UpdateHistoryItem) => u.status === 'in_progress' || u.status === 'pending'
      )
      if (inProgress) setActiveUpdate(inProgress)
    } catch {}
  }

  const checkNow = async () => {
    setIsChecking(true)
    setError(null)
    try {
      const res = await api.post('/api/updates/check-now')
      setAppCheck(res.data.app)
      setBaseCheck(res.data.base_images)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to check for updates')
    } finally {
      setIsChecking(false)
    }
  }

  const startAppUpdate = async (version: string) => {
    setIsUpdating('app')
    try {
      const res = await api.post('/api/updates/app', { target_version: version })
      setActiveUpdate(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to start update')
    } finally {
      setIsUpdating(null)
    }
  }

  const startBaseImageUpdate = async (container: string) => {
    setIsUpdating(container)
    try {
      const res = await api.post('/api/updates/base-image', { container_name: container })
      setActiveUpdate(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to start update')
    } finally {
      setIsUpdating(null)
    }
  }

  const rollback = async (updateId: string) => {
    try {
      const res = await api.post(`/api/updates/rollback/${updateId}`)
      setActiveUpdate(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Rollback failed')
    }
  }

  const updateSetting = useCallback(async (key: string, value: any) => {
    try {
      const res = await api.put('/api/updates/settings', { [key]: value })
      setSettings(res.data)
    } catch {}
  }, [])

  const statusBadge = (status: string) => {
    const variants: Record<string, string> = {
      completed: 'bg-green-500/10 text-green-500 border-green-500/20',
      failed: 'bg-red-500/10 text-red-500 border-red-500/20',
      in_progress: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
      pending: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
      rolled_back: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    }
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${variants[status] || 'bg-muted text-muted-foreground'}`}>
        {status.replace('_', ' ')}
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Active Update Progress */}
      {activeUpdate && !['completed', 'failed'].includes(activeUpdate.status) && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-950/20 p-6">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="h-5 w-5 text-blue-400 animate-pulse" />
            <h3 className="font-semibold text-blue-400">Update In Progress</h3>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                {activeUpdate.update_type === 'app'
                  ? `Updating to v${activeUpdate.to_version}`
                  : `Updating ${activeUpdate.container_name} base image`}
              </span>
              <span className="font-mono">{activeUpdate.progress_percent}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-500"
                style={{ width: `${activeUpdate.progress_percent}%` }}
              />
            </div>
            {activeUpdate.progress_message && (
              <p className="text-xs text-muted-foreground">{activeUpdate.progress_message}</p>
            )}
          </div>
        </div>
      )}

      {/* Check for Updates */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ArrowUpCircle className="h-5 w-5 text-cyan-500" />
            <h3 className="font-semibold">Application Updates</h3>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={checkNow}
            disabled={isChecking}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isChecking ? 'animate-spin' : ''}`} />
            Check Now
          </Button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2 text-sm text-red-400">
            {error}
          </div>
        )}

        {appCheck ? (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="rounded-lg bg-muted/50 px-4 py-3">
                <p className="text-xs text-muted-foreground">Current</p>
                <p className="text-lg font-bold font-mono">v{appCheck.current_version}</p>
              </div>
              {appCheck.update_available && appCheck.latest_version && (
                <>
                  <span className="text-muted-foreground">→</span>
                  <div className="rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-4 py-3">
                    <p className="text-xs text-cyan-400">Latest</p>
                    <p className="text-lg font-bold font-mono text-cyan-400">v{appCheck.latest_version}</p>
                  </div>
                  <Button
                    onClick={() => startAppUpdate(appCheck.latest_version!)}
                    disabled={isUpdating !== null}
                    className="ml-auto"
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Update Now
                  </Button>
                </>
              )}
              {!appCheck.update_available && !appCheck.error && (
                <div className="flex items-center gap-2 text-green-500">
                  <CheckCircle2 className="h-5 w-5" />
                  <span className="text-sm">You&apos;re on the latest version</span>
                </div>
              )}
            </div>

            {appCheck.error && (
              <p className="text-sm text-yellow-400 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                {appCheck.error}
              </p>
            )}

            {/* Available releases */}
            {appCheck.releases.length > 0 && appCheck.update_available && (
              <div className="mt-4">
                <p className="text-sm font-medium mb-2">Available Releases</p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {appCheck.releases
                    .filter(r => !r.prerelease || settings?.update_channel !== 'stable')
                    .slice(0, 5)
                    .map(release => (
                      <div key={release.version} className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-2">
                        <div className="flex items-center gap-3">
                          <span className="font-mono font-medium">v{release.version}</span>
                          {release.prerelease && (
                            <Badge variant="outline" className="text-yellow-500 border-yellow-500/30">
                              pre-release
                            </Badge>
                          )}
                          {release.published_at && (
                            <span className="text-xs text-muted-foreground">
                              {new Date(release.published_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {release.html_url && (
                            <a
                              href={release.html_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-cyan-400 hover:underline"
                            >
                              Release notes
                            </a>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => startAppUpdate(release.version)}
                            disabled={isUpdating !== null}
                          >
                            Install
                          </Button>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Click &quot;Check Now&quot; to check for available updates, or updates are checked
            automatically every {settings?.check_interval_hours || 24} hours.
          </p>
        )}
      </div>

      {/* Base Image Security Updates */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-amber-500" />
          <h3 className="font-semibold">Container Security (Base Images)</h3>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Keep container base images up to date with the latest security patches.
          These are the OS/runtime layers your containers run on.
        </p>

        {baseCheck.length > 0 ? (
          <div className="space-y-3">
            {baseCheck.map(img => (
              <div key={img.container} className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
                <div className="flex items-center gap-3">
                  <Box className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="font-medium capitalize">{img.container}</p>
                    <p className="text-xs text-muted-foreground font-mono">{img.image}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {img.error ? (
                    <span className="text-xs text-yellow-400">{img.error}</span>
                  ) : img.update_available ? (
                    <>
                      <Badge variant="outline" className="text-amber-400 border-amber-500/30">
                        Update available
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => startBaseImageUpdate(img.container)}
                        disabled={isUpdating !== null}
                      >
                        {isUpdating === img.container ? (
                          <RefreshCw className="h-3 w-3 animate-spin" />
                        ) : (
                          'Update'
                        )}
                      </Button>
                    </>
                  ) : (
                    <span className="text-xs text-green-500 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> Up to date
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Run a check to see base image status.
          </p>
        )}
      </div>

      {/* Update Settings */}
      {settings && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Settings2 className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Update Settings</h3>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Automatic update checks</p>
                <p className="text-xs text-muted-foreground">
                  Check for new versions every {settings.check_interval_hours}h
                </p>
              </div>
              <Switch
                checked={settings.auto_check_enabled}
                onCheckedChange={(v) => updateSetting('auto_check_enabled', v)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Auto-update security patches</p>
                <p className="text-xs text-muted-foreground">
                  Automatically apply base image updates when detected
                </p>
              </div>
              <Switch
                checked={settings.auto_update_security}
                onCheckedChange={(v) => updateSetting('auto_update_security', v)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Notify on app updates</p>
                <p className="text-xs text-muted-foreground">
                  Show banner when a new application version is available
                </p>
              </div>
              <Switch
                checked={settings.notify_app_updates}
                onCheckedChange={(v) => updateSetting('notify_app_updates', v)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Update channel</p>
                <p className="text-xs text-muted-foreground">
                  Stable: production releases only. Beta: include pre-releases.
                </p>
              </div>
              <div className="flex rounded-lg border border-input overflow-hidden">
                {['stable', 'beta', 'edge'].map(ch => (
                  <button
                    key={ch}
                    onClick={() => updateSetting('update_channel', ch)}
                    className={`px-3 py-1 text-xs font-medium transition-colors ${
                      settings.update_channel === ch
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    }`}
                  >
                    {ch}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Update History */}
      {history.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <h3 className="font-semibold">Update History</h3>
          </div>
          <div className="space-y-3">
            {history.map(item => (
              <div key={item.id} className="flex items-center justify-between rounded-lg bg-muted/30 px-4 py-3">
                <div className="flex items-center gap-3">
                  {item.status === 'completed' ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                  ) : item.status === 'failed' ? (
                    <XCircle className="h-4 w-4 text-red-500" />
                  ) : (
                    <Activity className="h-4 w-4 text-blue-500" />
                  )}
                  <div>
                    <p className="text-sm font-medium">
                      {item.update_type === 'app'
                        ? `App update: v${item.from_version} → v${item.to_version}`
                        : item.update_type === 'base_image'
                        ? `Base image: ${item.container_name}`
                        : `Rollback: v${item.from_version} → v${item.to_version}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(item.started_at).toLocaleString()}
                      {item.error_message && (
                        <span className="text-red-400 ml-2">{item.error_message}</span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {statusBadge(item.status)}
                  {item.status === 'completed' && item.can_rollback && !item.rollback_performed && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs"
                      onClick={() => rollback(item.id)}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Rollback
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
