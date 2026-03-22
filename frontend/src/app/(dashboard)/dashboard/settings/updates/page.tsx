'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Download,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Package,
  Server,
  Shield,
  History,
  Settings,
  RotateCcw,
  Clock,
  ArrowRight,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import api from '@/lib/api'

interface AppVersion {
  version: string
  name: string | null
  published_at: string | null
  changelog: string | null
  html_url: string | null
  prerelease: boolean
}

interface AppUpdateInfo {
  current_version: string
  latest_version: string | null
  update_available: boolean
  releases: AppVersion[]
  error: string | null
}

interface BaseImageInfo {
  container: string
  image: string
  update_available: boolean
  current_digest: string | null
  latest_digest: string | null
  error: string | null
}

interface UpdateStatus {
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
  backup_id: string | null
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

export default function UpdatesPage() {
  // State
  const [appInfo, setAppInfo] = useState<AppUpdateInfo | null>(null)
  const [baseImages, setBaseImages] = useState<BaseImageInfo[]>([])
  const [updateHistory, setUpdateHistory] = useState<UpdateStatus[]>([])
  const [settings, setSettings] = useState<UpdateSettings | null>(null)
  const [activeUpdate, setActiveUpdate] = useState<UpdateStatus | null>(null)

  // UI State
  const [isLoading, setIsLoading] = useState(true)
  const [isChecking, setIsChecking] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [isSavingSettings, setIsSavingSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Expandable sections
  const [showAllReleases, setShowAllReleases] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [selectedRelease, setSelectedRelease] = useState<AppVersion | null>(null)

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [appResponse, imagesResponse, historyResponse, settingsResponse] =
        await Promise.all([
          api.get('/api/updates/check/app'),
          api.get('/api/updates/check/base-images'),
          api.get('/api/updates/history'),
          api.get('/api/updates/settings'),
        ])

      setAppInfo(appResponse.data)
      setBaseImages(imagesResponse.data)
      setUpdateHistory(historyResponse.data)
      setSettings(settingsResponse.data)

      // Check for active updates
      const active = historyResponse.data.find(
        (u: UpdateStatus) => u.status === 'in_progress' || u.status === 'pending'
      )
      if (active) {
        setActiveUpdate(active)
      }
    } catch (err: any) {
      setError('Failed to load update information')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Poll for active update status
  useEffect(() => {
    if (!activeUpdate || (activeUpdate.status !== 'in_progress' && activeUpdate.status !== 'pending')) {
      return
    }

    const interval = setInterval(async () => {
      try {
        const response = await api.get(`/api/updates/status/${activeUpdate.id}`)
        setActiveUpdate(response.data)

        if (response.data.status === 'completed' || response.data.status === 'failed') {
          fetchData()
        }
      } catch (err) {
        console.error('Failed to fetch update status:', err)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [activeUpdate, fetchData])

  // Check for updates
  const handleCheckUpdates = async () => {
    setIsChecking(true)
    setError(null)
    setSuccess(null)

    try {
      const [appResponse, imagesResponse] = await Promise.all([
        api.get('/api/updates/check/app'),
        api.get('/api/updates/check/base-images'),
      ])

      setAppInfo(appResponse.data)
      setBaseImages(imagesResponse.data)
      setSuccess('Update check completed')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError('Failed to check for updates')
    } finally {
      setIsChecking(false)
    }
  }

  // Start app update
  const handleStartAppUpdate = async (version: string) => {
    if (!confirm(`Update to version ${version}?\n\nA backup will be created automatically before the update.`)) {
      return
    }

    setIsUpdating(true)
    setError(null)

    try {
      const response = await api.post('/api/updates/app', {
        target_version: version,
      })
      setActiveUpdate(response.data)
      setSuccess('Update started')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start update')
    } finally {
      setIsUpdating(false)
    }
  }

  // Start base image update
  const handleStartBaseImageUpdate = async (containerName: string) => {
    if (!confirm(`Update base image for ${containerName}?\n\nThis will restart the container.`)) {
      return
    }

    setIsUpdating(true)
    setError(null)

    try {
      const response = await api.post('/api/updates/base-image', {
        container_name: containerName,
      })
      setActiveUpdate(response.data)
      setSuccess('Base image update started')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start update')
    } finally {
      setIsUpdating(false)
    }
  }

  // Rollback
  const handleRollback = async (updateId: string) => {
    if (!confirm('Rollback this update?\n\nThis will restore the previous version from backup.')) {
      return
    }

    setError(null)

    try {
      const response = await api.post(`/api/updates/rollback/${updateId}`)
      setActiveUpdate(response.data)
      setSuccess('Rollback started')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start rollback')
    }
  }

  // Save settings
  const handleSaveSettings = async () => {
    if (!settings) return

    setIsSavingSettings(true)
    setError(null)

    try {
      const response = await api.put('/api/updates/settings', settings)
      setSettings(response.data)
      setSuccess('Settings saved')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError('Failed to save settings')
    } finally {
      setIsSavingSettings(false)
    }
  }

  // Status icons
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />
      case 'in_progress':
      case 'pending':
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString()
  }

  const formatRelativeDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    if (days < 7) return `${days} days ago`
    if (days < 30) return `${Math.floor(days / 7)} weeks ago`
    return `${Math.floor(days / 30)} months ago`
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const isUpdateInProgress = activeUpdate?.status === 'in_progress' || activeUpdate?.status === 'pending'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">System Updates</h1>
          <p className="text-muted-foreground">
            Manage application and base image updates
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>
          <button
            onClick={handleCheckUpdates}
            disabled={isChecking || isUpdateInProgress}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isChecking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Check for Updates
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-destructive flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} className="text-xs underline">
            Dismiss
          </button>
        </div>
      )}

      {success && (
        <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-4 text-green-500 flex items-center gap-2">
          <CheckCircle className="h-5 w-5 flex-shrink-0" />
          <span className="flex-1">{success}</span>
          <button onClick={() => setSuccess(null)} className="text-xs underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Active Update Progress */}
      {isUpdateInProgress && activeUpdate && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-6">
          <div className="flex items-center gap-3 mb-4">
            <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            <div>
              <h2 className="font-semibold">
                {activeUpdate.update_type === 'app' ? 'Application Update' : 'Base Image Update'} in Progress
              </h2>
              <p className="text-sm text-muted-foreground">
                {activeUpdate.progress_message || 'Processing...'}
              </p>
            </div>
          </div>

          <div className="w-full bg-muted rounded-full h-3">
            <div
              className="bg-blue-500 h-3 rounded-full transition-all duration-500"
              style={{ width: `${activeUpdate.progress_percent}%` }}
            />
          </div>
          <p className="text-sm text-muted-foreground mt-2 text-center">
            {activeUpdate.progress_percent}% complete
          </p>
        </div>
      )}

      {/* Settings Panel */}
      {showSettings && settings && (
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
              <Settings className="h-5 w-5 text-muted-foreground" />
            </div>
            <h2 className="text-lg font-semibold">Update Settings</h2>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Auto-check for updates</p>
                <p className="text-sm text-muted-foreground">Periodically check for new versions</p>
              </div>
              <button
                onClick={() => setSettings({ ...settings, auto_check_enabled: !settings.auto_check_enabled })}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.auto_check_enabled ? 'bg-primary' : 'bg-muted'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.auto_check_enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Check interval (hours)</p>
                <p className="text-sm text-muted-foreground">How often to check for updates</p>
              </div>
              <input
                type="number"
                min="1"
                max="168"
                value={settings.check_interval_hours}
                onChange={(e) => setSettings({ ...settings, check_interval_hours: parseInt(e.target.value) || 24 })}
                className="w-20 rounded-lg border border-input bg-background px-3 py-1 text-sm"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Update channel</p>
                <p className="text-sm text-muted-foreground">Which releases to show</p>
              </div>
              <select
                value={settings.update_channel}
                onChange={(e) => setSettings({ ...settings, update_channel: e.target.value })}
                className="rounded-lg border border-input bg-background px-3 py-1 text-sm"
              >
                <option value="stable">Stable</option>
                <option value="beta">Beta</option>
                <option value="edge">Edge (All)</option>
              </select>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">GitHub repository</p>
                <p className="text-sm text-muted-foreground">Source for update checks</p>
              </div>
              <input
                type="text"
                value={settings.github_repo}
                onChange={(e) => setSettings({ ...settings, github_repo: e.target.value })}
                className="w-64 rounded-lg border border-input bg-background px-3 py-1 text-sm font-mono"
              />
            </div>

            <div className="flex justify-end pt-4 border-t border-border">
              <button
                onClick={handleSaveSettings}
                disabled={isSavingSettings}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isSavingSettings && <Loader2 className="h-4 w-4 animate-spin" />}
                Save Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Application Updates */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Package className="h-5 w-5 text-primary" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold">Application Updates</h2>
            <p className="text-sm text-muted-foreground">
              Current version: <span className="font-mono font-medium">{appInfo?.current_version}</span>
            </p>
          </div>

          {appInfo?.update_available && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 text-green-500 text-sm font-medium">
              <Download className="h-4 w-4" />
              Update Available
            </div>
          )}
        </div>

        {appInfo?.error && (
          <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
            {appInfo.error}
          </div>
        )}

        {appInfo?.update_available && appInfo.latest_version && (
          <div className="mb-4 p-4 rounded-lg bg-green-500/5 border border-green-500/20">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-green-600 dark:text-green-400">
                  Version {appInfo.latest_version} is available
                </p>
                {appInfo.releases[0]?.published_at && (
                  <p className="text-sm text-muted-foreground">
                    Released {formatRelativeDate(appInfo.releases[0].published_at)}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {appInfo.releases[0]?.html_url && (
                  <a
                    href={appInfo.releases[0].html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input text-sm hover:bg-muted"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Release Notes
                  </a>
                )}
                <button
                  onClick={() => handleStartAppUpdate(appInfo.latest_version!)}
                  disabled={isUpdating || isUpdateInProgress}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-green-500 text-white text-sm font-medium hover:bg-green-600 disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                  Update Now
                </button>
              </div>
            </div>

            {appInfo.releases[0]?.changelog && (
              <div className="mt-3 pt-3 border-t border-green-500/20">
                <button
                  onClick={() => setSelectedRelease(selectedRelease?.version === appInfo.releases[0].version ? null : appInfo.releases[0])}
                  className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                >
                  {selectedRelease?.version === appInfo.releases[0].version ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                  View Changelog
                </button>
                {selectedRelease?.version === appInfo.releases[0].version && (
                  <pre className="mt-2 p-3 rounded-lg bg-muted text-sm whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">
                    {appInfo.releases[0].changelog}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}

        {!appInfo?.update_available && !appInfo?.error && (
          <p className="text-muted-foreground flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-500" />
            You are running the latest version
          </p>
        )}

        {/* Previous releases */}
        {appInfo?.releases && appInfo.releases.length > 1 && (
          <div className="mt-4 pt-4 border-t border-border">
            <button
              onClick={() => setShowAllReleases(!showAllReleases)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              {showAllReleases ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {showAllReleases ? 'Hide' : 'Show'} previous releases ({appInfo.releases.length - 1})
            </button>

            {showAllReleases && (
              <div className="mt-3 space-y-2">
                {appInfo.releases.slice(1).map((release) => (
                  <div key={release.version} className="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm">{release.version}</span>
                      {release.prerelease && (
                        <span className="px-2 py-0.5 rounded text-xs bg-yellow-500/10 text-yellow-600 dark:text-yellow-400">
                          Pre-release
                        </span>
                      )}
                      {release.published_at && (
                        <span className="text-sm text-muted-foreground">
                          {formatRelativeDate(release.published_at)}
                        </span>
                      )}
                    </div>
                    {release.html_url && (
                      <a
                        href={release.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Base Image Updates */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-500/10">
            <Server className="h-5 w-5 text-orange-500" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Base Image Updates</h2>
            <p className="text-sm text-muted-foreground">
              Security patches for container base images (Alpine, Python, Node.js, etc.)
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {baseImages.map((image) => (
            <div
              key={image.container}
              className="flex items-center justify-between p-4 rounded-lg border border-border"
            >
              <div className="flex items-center gap-3">
                <Shield className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium capitalize">{image.container}</p>
                  <p className="text-sm text-muted-foreground font-mono">
                    {image.image}
                  </p>
                </div>
              </div>

              {image.error ? (
                <span className="text-sm text-muted-foreground">
                  Check failed
                </span>
              ) : image.update_available ? (
                <button
                  onClick={() => handleStartBaseImageUpdate(image.container)}
                  disabled={isUpdating || isUpdateInProgress}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                  Update
                </button>
              ) : (
                <span className="text-sm text-green-500 flex items-center gap-1">
                  <CheckCircle className="h-4 w-4" />
                  Up to date
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Update History */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10">
            <History className="h-5 w-5 text-purple-500" />
          </div>
          <h2 className="text-lg font-semibold">Update History</h2>
        </div>

        {updateHistory.length === 0 ? (
          <p className="text-muted-foreground text-center py-8">
            No update history yet
          </p>
        ) : (
          <div className="space-y-3">
            {updateHistory.slice(0, 10).map((update) => (
              <div
                key={update.id}
                className="flex items-center justify-between p-4 rounded-lg border border-border"
              >
                <div className="flex items-center gap-3">
                  {getStatusIcon(update.status)}
                  <div>
                    <p className="font-medium">
                      {update.update_type === 'app' ? (
                        'Application Update'
                      ) : update.update_type === 'base_image' ? (
                        <>Base Image: <span className="capitalize">{update.container_name}</span></>
                      ) : update.update_type.includes('rollback') ? (
                        'Rollback'
                      ) : (
                        update.update_type
                      )}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {update.from_version && update.to_version && (
                        <span className="font-mono">
                          {update.from_version} <ArrowRight className="h-3 w-3 inline" /> {update.to_version}
                        </span>
                      )}
                      {update.from_version && update.to_version && <span className="mx-2">|</span>}
                      {formatDate(update.started_at)}
                    </p>
                    {update.error_message && (
                      <p className="text-sm text-red-500 mt-1">{update.error_message}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {update.status === 'completed' && update.can_rollback && !update.rollback_performed && (
                    <button
                      onClick={() => handleRollback(update.id)}
                      disabled={isUpdateInProgress}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-input text-sm hover:bg-muted disabled:opacity-50"
                    >
                      <RotateCcw className="h-4 w-4" />
                      Rollback
                    </button>
                  )}

                  {update.rollback_performed && (
                    <span className="text-sm text-muted-foreground">Rolled back</span>
                  )}

                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    update.status === 'completed' ? 'bg-green-500/10 text-green-500' :
                    update.status === 'failed' ? 'bg-red-500/10 text-red-500' :
                    update.status === 'in_progress' ? 'bg-blue-500/10 text-blue-500' :
                    'bg-yellow-500/10 text-yellow-500'
                  }`}>
                    {update.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
