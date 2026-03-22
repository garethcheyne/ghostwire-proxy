'use client'

import { useState, useEffect, useRef } from 'react'
import {
  Archive,
  Download,
  Upload,
  Trash2,
  RotateCcw,
  RefreshCw,
  Plus,
  Settings,
  Clock,
  HardDrive,
  Database,
  Shield,
  FileText,
  Activity,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import api from '@/lib/api'

interface Backup {
  id: string
  filename: string
  file_size: number
  backup_type: 'manual' | 'scheduled'
  includes_database: boolean
  includes_certificates: boolean
  includes_letsencrypt: boolean
  includes_configs: boolean
  includes_traffic_logs: boolean
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  error_message?: string
  created_at: string
  completed_at?: string
}

interface BackupSettings {
  auto_backup_enabled: boolean
  schedule_cron: string
  retention_days: number
  retention_count: number
  include_traffic_logs: boolean
  encryption_enabled: boolean
}

export default function BackupsPage() {
  const [backups, setBackups] = useState<Backup[]>([])
  const [settings, setSettings] = useState<BackupSettings | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Create backup options
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [includeDatabase, setIncludeDatabase] = useState(true)
  const [includeCertificates, setIncludeCertificates] = useState(true)
  const [includeLetsencrypt, setIncludeLetsencrypt] = useState(true)
  const [includeConfigs, setIncludeConfigs] = useState(true)
  const [includeTrafficLogs, setIncludeTrafficLogs] = useState(false)

  // Restore dialog
  const [showRestoreDialog, setShowRestoreDialog] = useState(false)
  const [restoreBackupId, setRestoreBackupId] = useState<string | null>(null)
  const [restoreOptions, setRestoreOptions] = useState({
    restore_database: true,
    restore_certificates: true,
    restore_letsencrypt: true,
    restore_configs: true,
  })

  // Settings dialog
  const [showSettingsDialog, setShowSettingsDialog] = useState(false)
  const [editedSettings, setEditedSettings] = useState<BackupSettings | null>(null)
  const [isSavingSettings, setIsSavingSettings] = useState(false)

  // Upload state
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchBackups()
    fetchSettings()
  }, [])

  const fetchBackups = async () => {
    try {
      const response = await api.get('/api/backups/')
      setBackups(response.data.backups)
    } catch (err: any) {
      console.error('Failed to fetch backups:', err)
      setError('Failed to load backups')
    } finally {
      setIsLoading(false)
    }
  }

  const fetchSettings = async () => {
    try {
      const response = await api.get('/api/backups/settings/current')
      setSettings(response.data)
    } catch (err) {
      console.error('Failed to fetch settings:', err)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString()
  }

  const handleCreateBackup = async () => {
    setIsCreating(true)
    setError(null)

    try {
      const response = await api.post('/api/backups/', {
        include_database: includeDatabase,
        include_certificates: includeCertificates,
        include_letsencrypt: includeLetsencrypt,
        include_configs: includeConfigs,
        include_traffic_logs: includeTrafficLogs,
      })

      setSuccess('Backup created successfully')
      setShowCreateDialog(false)
      fetchBackups()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create backup')
    } finally {
      setIsCreating(false)
    }
  }

  const handleDownload = async (backup: Backup) => {
    try {
      const response = await api.get(`/api/backups/${backup.id}/download`, {
        responseType: 'blob',
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', backup.filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (err: any) {
      setError('Failed to download backup')
    }
  }

  const handleDelete = async (backup: Backup) => {
    if (!confirm(`Are you sure you want to delete backup "${backup.filename}"?`)) {
      return
    }

    try {
      await api.delete(`/api/backups/${backup.id}`)
      setSuccess('Backup deleted')
      fetchBackups()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete backup')
    }
  }

  const handleRestore = async () => {
    if (!restoreBackupId) return

    if (!confirm('WARNING: This will overwrite existing data. Are you sure you want to restore from this backup?')) {
      return
    }

    setIsRestoring(true)
    setError(null)

    try {
      const response = await api.post('/api/backups/restore', {
        backup_id: restoreBackupId,
        ...restoreOptions,
      })

      setSuccess(`Restore completed: ${response.data.message}`)
      setShowRestoreDialog(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to restore backup')
    } finally {
      setIsRestoring(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!editedSettings) return

    setIsSavingSettings(true)
    setError(null)

    try {
      await api.put('/api/backups/settings/current', editedSettings)
      setSettings(editedSettings)
      setSuccess('Settings saved')
      setShowSettingsDialog(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save settings')
    } finally {
      setIsSavingSettings(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.name.endsWith('.tar.gz') && !file.name.endsWith('.tgz')) {
      setError('Please select a .tar.gz backup file')
      return
    }

    setIsUploading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      await api.post('/api/backups/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      setSuccess('Backup uploaded successfully')
      fetchBackups()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload backup')
    } finally {
      setIsUploading(false)
      // Reset file input so same file can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />
      case 'in_progress':
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading backups...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Backup & Restore</h1>
          <p className="text-muted-foreground">
            Create and manage backups of your Ghostwire Proxy configuration
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".tar.gz,.tgz"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {isUploading ? 'Uploading...' : 'Upload Backup'}
          </button>
          <button
            onClick={() => {
              setEditedSettings(settings)
              setShowSettingsDialog(true)
            }}
            className="flex items-center gap-2 rounded-lg border border-input px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            <Settings className="h-4 w-4" />
            Settings
          </button>
          <button
            onClick={() => setShowCreateDialog(true)}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Create Backup
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-destructive flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-xs underline">
            Dismiss
          </button>
        </div>
      )}

      {success && (
        <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-4 text-green-500 flex items-center gap-2">
          <CheckCircle className="h-5 w-5" />
          {success}
          <button onClick={() => setSuccess(null)} className="ml-auto text-xs underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Settings Summary */}
      {settings && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">
                Auto Backup:{' '}
                <span className={settings.auto_backup_enabled ? 'text-green-500' : 'text-muted-foreground'}>
                  {settings.auto_backup_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </span>
            </div>
            <div className="text-muted-foreground">|</div>
            <div className="text-sm text-muted-foreground">
              Schedule: {settings.schedule_cron}
            </div>
            <div className="text-muted-foreground">|</div>
            <div className="text-sm text-muted-foreground">
              Retention: {settings.retention_days} days / {settings.retention_count} backups
            </div>
          </div>
        </div>
      )}

      {/* Backups List */}
      {backups.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Archive className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
          <p className="text-muted-foreground">No backups yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Create your first backup to protect your configuration
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Backup
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Size
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Includes
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Date
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {backups.map((backup) => (
                <tr key={backup.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    {getStatusIcon(backup.status)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm">{backup.filename}</span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {formatBytes(backup.file_size)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                      backup.backup_type === 'scheduled'
                        ? 'bg-blue-500/10 text-blue-500'
                        : backup.backup_type === 'uploaded'
                        ? 'bg-orange-500/10 text-orange-500'
                        : 'bg-purple-500/10 text-purple-500'
                    }`}>
                      {backup.backup_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {backup.includes_database && (
                        <span title="Database" className="p-1 rounded bg-muted">
                          <Database className="h-3 w-3" />
                        </span>
                      )}
                      {backup.includes_certificates && (
                        <span title="Certificates" className="p-1 rounded bg-muted">
                          <Shield className="h-3 w-3" />
                        </span>
                      )}
                      {backup.includes_configs && (
                        <span title="Configs" className="p-1 rounded bg-muted">
                          <FileText className="h-3 w-3" />
                        </span>
                      )}
                      {backup.includes_traffic_logs && (
                        <span title="Traffic Logs" className="p-1 rounded bg-muted">
                          <Activity className="h-3 w-3" />
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {formatDate(backup.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {backup.status === 'completed' && (
                        <>
                          <button
                            onClick={() => handleDownload(backup)}
                            className="p-2 rounded hover:bg-muted"
                            title="Download"
                          >
                            <Download className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setRestoreBackupId(backup.id)
                              setShowRestoreDialog(true)
                            }}
                            className="p-2 rounded hover:bg-muted text-blue-500"
                            title="Restore"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => handleDelete(backup)}
                        className="p-2 rounded hover:bg-muted text-red-500"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Backup Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Create Backup</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Select what to include in the backup
              </p>
            </div>

            <div className="p-6 space-y-4">
              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <span>Database</span>
                </div>
                <input
                  type="checkbox"
                  checked={includeDatabase}
                  onChange={(e) => setIncludeDatabase(e.target.checked)}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-muted-foreground" />
                  <span>SSL Certificates</span>
                </div>
                <input
                  type="checkbox"
                  checked={includeCertificates}
                  onChange={(e) => setIncludeCertificates(e.target.checked)}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-muted-foreground" />
                  <span>Let's Encrypt Data</span>
                </div>
                <input
                  type="checkbox"
                  checked={includeLetsencrypt}
                  onChange={(e) => setIncludeLetsencrypt(e.target.checked)}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <span>Nginx Configs</span>
                </div>
                <input
                  type="checkbox"
                  checked={includeConfigs}
                  onChange={(e) => setIncludeConfigs(e.target.checked)}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <span>Traffic Logs</span>
                    <p className="text-xs text-muted-foreground">Warning: Can be large!</p>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={includeTrafficLogs}
                  onChange={(e) => setIncludeTrafficLogs(e.target.checked)}
                  className="h-4 w-4"
                />
              </label>

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  onClick={() => setShowCreateDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateBackup}
                  disabled={isCreating}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isCreating && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create Backup
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Restore Dialog */}
      {showRestoreDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Restore Backup</h2>
              <p className="text-sm text-destructive mt-1">
                Warning: This will overwrite existing data!
              </p>
            </div>

            <div className="p-6 space-y-4">
              <label className="flex items-center justify-between cursor-pointer">
                <span>Restore Database</span>
                <input
                  type="checkbox"
                  checked={restoreOptions.restore_database}
                  onChange={(e) => setRestoreOptions({
                    ...restoreOptions,
                    restore_database: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <span>Restore Certificates</span>
                <input
                  type="checkbox"
                  checked={restoreOptions.restore_certificates}
                  onChange={(e) => setRestoreOptions({
                    ...restoreOptions,
                    restore_certificates: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <span>Restore Let's Encrypt</span>
                <input
                  type="checkbox"
                  checked={restoreOptions.restore_letsencrypt}
                  onChange={(e) => setRestoreOptions({
                    ...restoreOptions,
                    restore_letsencrypt: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <span>Restore Configs</span>
                <input
                  type="checkbox"
                  checked={restoreOptions.restore_configs}
                  onChange={(e) => setRestoreOptions({
                    ...restoreOptions,
                    restore_configs: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  onClick={() => setShowRestoreDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRestore}
                  disabled={isRestoring}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
                >
                  {isRestoring && <Loader2 className="h-4 w-4 animate-spin" />}
                  Restore
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Settings Dialog */}
      {showSettingsDialog && editedSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Backup Settings</h2>
            </div>

            <div className="p-6 space-y-4">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <span className="font-medium">Automatic Backups</span>
                  <p className="text-xs text-muted-foreground">Run backups on schedule</p>
                </div>
                <input
                  type="checkbox"
                  checked={editedSettings.auto_backup_enabled}
                  onChange={(e) => setEditedSettings({
                    ...editedSettings,
                    auto_backup_enabled: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <div>
                <label className="block text-sm font-medium mb-2">Schedule (Cron)</label>
                <input
                  type="text"
                  value={editedSettings.schedule_cron}
                  onChange={(e) => setEditedSettings({
                    ...editedSettings,
                    schedule_cron: e.target.value,
                  })}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                  placeholder="0 2 * * *"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Default: 0 2 * * * (daily at 2 AM)
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Retention Days</label>
                  <input
                    type="number"
                    value={editedSettings.retention_days}
                    onChange={(e) => setEditedSettings({
                      ...editedSettings,
                      retention_days: parseInt(e.target.value) || 30,
                    })}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                    min={1}
                    max={365}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Min Backups</label>
                  <input
                    type="number"
                    value={editedSettings.retention_count}
                    onChange={(e) => setEditedSettings({
                      ...editedSettings,
                      retention_count: parseInt(e.target.value) || 10,
                    })}
                    className="w-full px-4 py-2 rounded-lg border border-input bg-background"
                    min={1}
                    max={100}
                  />
                </div>
              </div>

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <span className="font-medium">Include Traffic Logs</span>
                  <p className="text-xs text-muted-foreground">Warning: Significantly increases backup size</p>
                </div>
                <input
                  type="checkbox"
                  checked={editedSettings.include_traffic_logs}
                  onChange={(e) => setEditedSettings({
                    ...editedSettings,
                    include_traffic_logs: e.target.checked,
                  })}
                  className="h-4 w-4"
                />
              </label>

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  onClick={() => setShowSettingsDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveSettings}
                  disabled={isSavingSettings}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isSavingSettings && <Loader2 className="h-4 w-4 animate-spin" />}
                  Save Settings
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
