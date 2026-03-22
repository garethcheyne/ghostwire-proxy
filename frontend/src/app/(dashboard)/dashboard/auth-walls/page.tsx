'use client'

import { useState, useEffect } from 'react'
import {
  Key,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  Loader2,
  User,
  Server,
  Shield,
  Github,
  MonitorSmartphone,
  ShieldCheck,
  Clock,
  XCircle,
  Users,
  Settings2,
  Copy,
  Eye,
  EyeOff,
  RefreshCw,
} from 'lucide-react'
import api from '@/lib/api'
import type { AuthWall, LocalAuthUser, AuthProvider } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface AuthSession {
  id: string
  user_type: string
  user_id: string
  username: string
  email?: string
  ip_address?: string
  user_agent?: string
  created_at: string
  expires_at: string
  last_activity_at?: string
  revoked: boolean
}

export default function AuthWallPage() {
  const [authWalls, setAuthWalls] = useState<AuthWall[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showWallDialog, setShowWallDialog] = useState(false)
  const [showProviderDialog, setShowProviderDialog] = useState(false)
  const [showUserDialog, setShowUserDialog] = useState(false)
  const [showSessionsDialog, setShowSessionsDialog] = useState(false)
  const [showTotpDialog, setShowTotpDialog] = useState(false)
  const [editingWall, setEditingWall] = useState<AuthWall | null>(null)
  const [selectedWall, setSelectedWall] = useState<AuthWall | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)

  // Wall form state
  const [wallName, setWallName] = useState('')
  const [wallAuthType, setWallAuthType] = useState<'basic' | 'oauth' | 'ldap' | 'multi'>('multi')
  const [wallTimeout, setWallTimeout] = useState(3600)
  const [wallTheme, setWallTheme] = useState('default')

  // Provider form state
  const [providerName, setProviderName] = useState('')
  const [providerType, setProviderType] = useState<'google' | 'github' | 'oidc'>('google')
  const [providerClientId, setProviderClientId] = useState('')
  const [providerClientSecret, setProviderClientSecret] = useState('')
  const [providerEnabled, setProviderEnabled] = useState(true)
  const [showSecret, setShowSecret] = useState(false)

  // User form state
  const [userUsername, setUserUsername] = useState('')
  const [userPassword, setUserPassword] = useState('')
  const [userEmail, setUserEmail] = useState('')
  const [userDisplayName, setUserDisplayName] = useState('')

  // Sessions state
  const [sessions, setSessions] = useState<AuthSession[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)

  // TOTP state
  const [totpSetupData, setTotpSetupData] = useState<{
    secret: string
    provisioning_uri: string
    backup_codes: string[]
  } | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [selectedUser, setSelectedUser] = useState<LocalAuthUser | null>(null)

  useEffect(() => {
    fetchAuthWalls()
  }, [])

  const fetchAuthWalls = async () => {
    try {
      const response = await api.get('/api/auth-walls')
      setAuthWalls(response.data)
    } catch (error) {
      console.error('Failed to fetch auth walls:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchSessions = async (wallId: string) => {
    setLoadingSessions(true)
    try {
      const response = await api.get(`/api/auth-walls/${wallId}/sessions`)
      setSessions(response.data)
    } catch (error) {
      console.error('Failed to fetch sessions:', error)
    } finally {
      setLoadingSessions(false)
    }
  }

  const handleCreateWall = () => {
    setWallName('')
    setWallAuthType('multi')
    setWallTimeout(3600)
    setWallTheme('default')
    setError('')
    setEditingWall(null)
    setShowWallDialog(true)
  }

  const handleEditWall = (wall: AuthWall) => {
    setWallName(wall.name)
    setWallAuthType(wall.auth_type)
    setWallTimeout(wall.session_timeout)
    setWallTheme(wall.theme || 'default')
    setEditingWall(wall)
    setShowWallDialog(true)
    setActiveDropdown(null)
  }

  const handleSubmitWall = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const data = {
        name: wallName,
        auth_type: wallAuthType,
        session_timeout: wallTimeout,
        theme: wallTheme,
      }

      if (editingWall) {
        await api.put(`/api/auth-walls/${editingWall.id}`, data)
      } else {
        await api.post('/api/auth-walls', data)
      }

      setShowWallDialog(false)
      fetchAuthWalls()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save auth wall')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteWall = async (wall: AuthWall) => {
    if (!confirm(`Are you sure you want to delete "${wall.name}"?`)) return

    try {
      await api.delete(`/api/auth-walls/${wall.id}`)
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to delete auth wall:', error)
    }
    setActiveDropdown(null)
  }

  // Provider handlers
  const handleAddProvider = (wall: AuthWall) => {
    setSelectedWall(wall)
    setProviderName('')
    setProviderType('google')
    setProviderClientId('')
    setProviderClientSecret('')
    setProviderEnabled(true)
    setShowSecret(false)
    setError('')
    setShowProviderDialog(true)
  }

  const handleSubmitProvider = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedWall) return
    setError('')
    setIsSubmitting(true)

    try {
      await api.post(`/api/auth-walls/${selectedWall.id}/providers`, {
        name: providerName || `${providerType.charAt(0).toUpperCase()}${providerType.slice(1)}`,
        provider_type: providerType,
        client_id: providerClientId,
        client_secret: providerClientSecret,
        enabled: providerEnabled,
      })

      setShowProviderDialog(false)
      fetchAuthWalls()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add provider')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteProvider = async (wallId: string, providerId: string) => {
    try {
      await api.delete(`/api/auth-walls/${wallId}/providers/${providerId}`)
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to delete provider:', error)
    }
  }

  const handleToggleProvider = async (wallId: string, provider: AuthProvider) => {
    try {
      await api.put(`/api/auth-walls/${wallId}/providers/${provider.id}`, {
        enabled: !provider.enabled,
      })
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to toggle provider:', error)
    }
  }

  // User handlers
  const handleAddUser = (wall: AuthWall) => {
    setSelectedWall(wall)
    setUserUsername('')
    setUserPassword('')
    setUserEmail('')
    setUserDisplayName('')
    setError('')
    setShowUserDialog(true)
  }

  const handleSubmitUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedWall) return
    setError('')
    setIsSubmitting(true)

    try {
      await api.post(`/api/auth-walls/${selectedWall.id}/users`, {
        username: userUsername,
        password: userPassword,
        email: userEmail || undefined,
        display_name: userDisplayName || undefined,
      })

      setShowUserDialog(false)
      fetchAuthWalls()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add user')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteUser = async (wallId: string, userId: string) => {
    if (!confirm('Are you sure you want to delete this user?')) return
    try {
      await api.delete(`/api/auth-walls/${wallId}/users/${userId}`)
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to delete user:', error)
    }
  }

  const handleToggleUserActive = async (wallId: string, user: LocalAuthUser) => {
    try {
      await api.put(`/api/auth-walls/${wallId}/users/${user.id}`, {
        is_active: !user.is_active,
      })
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to toggle user:', error)
    }
  }

  // Session handlers
  const handleViewSessions = (wall: AuthWall) => {
    setSelectedWall(wall)
    setShowSessionsDialog(true)
    fetchSessions(wall.id)
  }

  const handleRevokeSession = async (sessionId: string) => {
    if (!selectedWall) return
    try {
      await api.post(`/api/auth-walls/${selectedWall.id}/sessions/${sessionId}/revoke`)
      fetchSessions(selectedWall.id)
    } catch (error) {
      console.error('Failed to revoke session:', error)
    }
  }

  const handleRevokeAllSessions = async () => {
    if (!selectedWall) return
    if (!confirm('Revoke all active sessions? Users will need to log in again.')) return
    try {
      await api.post(`/api/auth-walls/${selectedWall.id}/sessions/revoke-all`)
      fetchSessions(selectedWall.id)
    } catch (error) {
      console.error('Failed to revoke sessions:', error)
    }
  }

  // TOTP handlers
  const handleSetupTotp = async (wall: AuthWall, user: LocalAuthUser) => {
    setSelectedWall(wall)
    setSelectedUser(user)
    setTotpCode('')
    setError('')
    setTotpSetupData(null)
    setShowTotpDialog(true)

    try {
      const response = await api.post(`/api/auth-walls/${wall.id}/users/${user.id}/totp/setup`)
      setTotpSetupData(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to setup TOTP')
    }
  }

  const handleVerifyTotp = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedWall || !selectedUser) return
    setError('')
    setIsSubmitting(true)

    try {
      await api.post(`/api/auth-walls/${selectedWall.id}/users/${selectedUser.id}/totp/verify`, {
        code: totpCode,
      })

      setShowTotpDialog(false)
      fetchAuthWalls()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid code')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDisableTotp = async (wallId: string, userId: string) => {
    if (!confirm('Disable two-factor authentication for this user?')) return
    try {
      await api.delete(`/api/auth-walls/${wallId}/users/${userId}/totp`)
      fetchAuthWalls()
    } catch (error) {
      console.error('Failed to disable TOTP:', error)
    }
  }

  const getProviderIcon = (type: string) => {
    switch (type) {
      case 'google':
        return (
          <svg className="h-4 w-4" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="currentColor"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="currentColor"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="currentColor"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
        )
      case 'github':
        return <Github className="h-4 w-4" />
      default:
        return <Server className="h-4 w-4" />
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Authentication Walls</h1>
          <p className="text-muted-foreground">
            Protect your proxy hosts with OAuth, local auth, or LDAP
          </p>
        </div>
        <Button onClick={handleCreateWall}>
          <Plus className="h-4 w-4 mr-2" />
          Add Auth Wall
        </Button>
      </div>

      {/* Auth Walls Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {authWalls.length === 0 ? (
          <div className="col-span-full rounded-xl border border-border bg-card p-12 text-center">
            <Key className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No auth walls configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click "Add Auth Wall" to create one
            </p>
          </div>
        ) : (
          authWalls.map((wall) => (
            <div key={wall.id} className="rounded-xl border border-border bg-card">
              <div className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-primary/10 p-2">
                      <Shield className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <h3 className="font-semibold">{wall.name}</h3>
                      <Badge variant="secondary" className="mt-1">
                        {wall.auth_type.toUpperCase()}
                      </Badge>
                    </div>
                  </div>
                  <div className="relative">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setActiveDropdown(activeDropdown === wall.id ? null : wall.id)
                      }
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>

                    {activeDropdown === wall.id && (
                      <div className="absolute right-0 top-full z-10 mt-1 w-48 rounded-lg border border-border bg-popover shadow-lg">
                        <div className="p-1">
                          <button
                            onClick={() => handleEditWall(wall)}
                            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                          >
                            <Pencil className="h-4 w-4" />
                            Edit
                          </button>
                          <button
                            onClick={() => handleViewSessions(wall)}
                            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                          >
                            <MonitorSmartphone className="h-4 w-4" />
                            View Sessions
                          </button>
                          <button
                            onClick={() => handleDeleteWall(wall)}
                            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                  <div className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {Math.floor(wall.session_timeout / 60)} min
                  </div>
                  <div className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {wall.local_users?.length || 0} users
                  </div>
                  <div className="flex items-center gap-1">
                    <Server className="h-3.5 w-3.5" />
                    {wall.providers?.length || 0} providers
                  </div>
                </div>

                <Tabs defaultValue="providers" className="w-full">
                  <TabsList className="w-full">
                    <TabsTrigger value="providers" className="flex-1">Providers</TabsTrigger>
                    <TabsTrigger value="users" className="flex-1">Users</TabsTrigger>
                  </TabsList>

                  <TabsContent value="providers" className="mt-3">
                    <div className="space-y-2">
                      {wall.providers?.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-2">
                          No OAuth providers
                        </p>
                      ) : (
                        wall.providers?.map((provider) => (
                          <div
                            key={provider.id}
                            className="flex items-center justify-between rounded-lg border border-border p-2"
                          >
                            <div className="flex items-center gap-2">
                              {getProviderIcon(provider.provider_type)}
                              <span className="text-sm">{provider.name}</span>
                              <Badge
                                variant={provider.enabled ? 'default' : 'secondary'}
                                className="text-xs"
                              >
                                {provider.enabled ? 'Active' : 'Disabled'}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => handleToggleProvider(wall.id, provider)}
                              >
                                {provider.enabled ? (
                                  <EyeOff className="h-3.5 w-3.5" />
                                ) : (
                                  <Eye className="h-3.5 w-3.5" />
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-red-500"
                                onClick={() => handleDeleteProvider(wall.id, provider.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                        ))
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => handleAddProvider(wall)}
                      >
                        <Plus className="h-3.5 w-3.5 mr-1" />
                        Add Provider
                      </Button>
                    </div>
                  </TabsContent>

                  <TabsContent value="users" className="mt-3">
                    <div className="space-y-2">
                      {wall.local_users?.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-2">
                          No local users
                        </p>
                      ) : (
                        wall.local_users?.map((user) => (
                          <div
                            key={user.id}
                            className="flex items-center justify-between rounded-lg border border-border p-2"
                          >
                            <div className="flex items-center gap-2">
                              <User className="h-4 w-4 text-muted-foreground" />
                              <div>
                                <span className="text-sm">{user.username}</span>
                                <div className="flex items-center gap-1">
                                  {user.totp_enabled && (
                                    <Badge variant="secondary" className="text-[10px] px-1">
                                      <ShieldCheck className="h-2.5 w-2.5 mr-0.5" />
                                      2FA
                                    </Badge>
                                  )}
                                  {!user.is_active && (
                                    <Badge variant="destructive" className="text-[10px] px-1">
                                      Disabled
                                    </Badge>
                                  )}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1">
                              {!user.totp_enabled ? (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7"
                                  onClick={() => handleSetupTotp(wall, user)}
                                  title="Enable 2FA"
                                >
                                  <ShieldCheck className="h-3.5 w-3.5" />
                                </Button>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7 text-amber-500"
                                  onClick={() => handleDisableTotp(wall.id, user.id)}
                                  title="Disable 2FA"
                                >
                                  <ShieldCheck className="h-3.5 w-3.5" />
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => handleToggleUserActive(wall.id, user)}
                              >
                                {user.is_active ? (
                                  <EyeOff className="h-3.5 w-3.5" />
                                ) : (
                                  <Eye className="h-3.5 w-3.5" />
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-red-500"
                                onClick={() => handleDeleteUser(wall.id, user.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                        ))
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => handleAddUser(wall)}
                      >
                        <Plus className="h-3.5 w-3.5 mr-1" />
                        Add User
                      </Button>
                    </div>
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create/Edit Wall Dialog */}
      <Dialog open={showWallDialog} onOpenChange={setShowWallDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingWall ? 'Edit Auth Wall' : 'Add Auth Wall'}
            </DialogTitle>
            <DialogDescription>
              Configure authentication settings for protected resources
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmitWall} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wallName">Name</Label>
              <Input
                id="wallName"
                value={wallName}
                onChange={(e) => setWallName(e.target.value)}
                placeholder="My Auth Wall"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="authType">Authentication Type</Label>
              <Select value={wallAuthType} onValueChange={(v) => setWallAuthType(v as any)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="multi">Multi (OAuth + Local)</SelectItem>
                  <SelectItem value="basic">Basic Auth Only</SelectItem>
                  <SelectItem value="oauth">OAuth Only</SelectItem>
                  <SelectItem value="ldap">LDAP / Active Directory</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {wallAuthType === 'multi' && 'Allow users to login with OAuth providers or local credentials'}
                {wallAuthType === 'basic' && 'HTTP Basic Authentication (browser popup)'}
                {wallAuthType === 'oauth' && 'OAuth providers only (Google, GitHub, etc.)'}
                {wallAuthType === 'ldap' && 'LDAP/Active Directory authentication'}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timeout">Session Timeout (seconds)</Label>
              <Input
                id="timeout"
                type="number"
                value={wallTimeout}
                onChange={(e) => setWallTimeout(parseInt(e.target.value) || 3600)}
                min={60}
              />
              <p className="text-xs text-muted-foreground">
                {Math.floor(wallTimeout / 60)} minutes / {Math.floor(wallTimeout / 3600)} hours
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="theme">Login Portal Theme</Label>
              <Select value={wallTheme} onValueChange={setWallTheme}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">Default (Ghostwire)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                The theme used for the login portal. Additional themes can be added in the proxy container.
              </p>
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowWallDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {editingWall ? 'Save Changes' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add Provider Dialog */}
      <Dialog open={showProviderDialog} onOpenChange={setShowProviderDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add OAuth Provider</DialogTitle>
            <DialogDescription>
              Configure an OAuth provider for {selectedWall?.name}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmitProvider} className="space-y-4">
            <div className="space-y-2">
              <Label>Provider Type</Label>
              <Select value={providerType} onValueChange={(v) => setProviderType(v as any)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="google">
                    <div className="flex items-center gap-2">
                      {getProviderIcon('google')}
                      Google
                    </div>
                  </SelectItem>
                  <SelectItem value="github">
                    <div className="flex items-center gap-2">
                      {getProviderIcon('github')}
                      GitHub
                    </div>
                  </SelectItem>
                  <SelectItem value="oidc">
                    <div className="flex items-center gap-2">
                      {getProviderIcon('oidc')}
                      Generic OIDC
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="providerName">Display Name (optional)</Label>
              <Input
                id="providerName"
                value={providerName}
                onChange={(e) => setProviderName(e.target.value)}
                placeholder={providerType.charAt(0).toUpperCase() + providerType.slice(1)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="clientId">Client ID</Label>
              <Input
                id="clientId"
                value={providerClientId}
                onChange={(e) => setProviderClientId(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="clientSecret">Client Secret</Label>
              <div className="relative">
                <Input
                  id="clientSecret"
                  type={showSecret ? 'text' : 'password'}
                  value={providerClientSecret}
                  onChange={(e) => setProviderClientSecret(e.target.value)}
                  required
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full"
                  onClick={() => setShowSecret(!showSecret)}
                >
                  {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="enabled">Enabled</Label>
              <Switch
                id="enabled"
                checked={providerEnabled}
                onCheckedChange={setProviderEnabled}
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowProviderDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Add Provider
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Add User Dialog */}
      <Dialog open={showUserDialog} onOpenChange={setShowUserDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Local User</DialogTitle>
            <DialogDescription>
              Add a user to {selectedWall?.name}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmitUser} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={userUsername}
                onChange={(e) => setUserUsername(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={userPassword}
                onChange={(e) => setUserPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email (optional)</Label>
              <Input
                id="email"
                type="email"
                value={userEmail}
                onChange={(e) => setUserEmail(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="displayName">Display Name (optional)</Label>
              <Input
                id="displayName"
                value={userDisplayName}
                onChange={(e) => setUserDisplayName(e.target.value)}
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowUserDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Add User
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Sessions Dialog */}
      <Dialog open={showSessionsDialog} onOpenChange={setShowSessionsDialog}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Active Sessions - {selectedWall?.name}</DialogTitle>
            <DialogDescription>
              View and manage active sessions for this auth wall
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => selectedWall && fetchSessions(selectedWall.id)}
                disabled={loadingSessions}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${loadingSessions ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleRevokeAllSessions}
                disabled={sessions.length === 0}
              >
                <XCircle className="h-4 w-4 mr-2" />
                Revoke All
              </Button>
            </div>

            {loadingSessions ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No active sessions
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>IP Address</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sessions.map((session) => (
                    <TableRow key={session.id}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{session.username}</div>
                          {session.email && (
                            <div className="text-xs text-muted-foreground">{session.email}</div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{session.user_type}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {session.ip_address || '-'}
                      </TableCell>
                      <TableCell className="text-xs">
                        {formatDate(session.created_at)}
                      </TableCell>
                      <TableCell className="text-xs">
                        {formatDate(session.expires_at)}
                      </TableCell>
                      <TableCell>
                        {session.revoked ? (
                          <Badge variant="destructive">Revoked</Badge>
                        ) : new Date(session.expires_at) < new Date() ? (
                          <Badge variant="secondary">Expired</Badge>
                        ) : (
                          <Badge variant="default">Active</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {!session.revoked && new Date(session.expires_at) >= new Date() && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500"
                            onClick={() => handleRevokeSession(session.id)}
                          >
                            Revoke
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSessionsDialog(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* TOTP Setup Dialog */}
      <Dialog open={showTotpDialog} onOpenChange={setShowTotpDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enable Two-Factor Authentication</DialogTitle>
            <DialogDescription>
              Set up TOTP for {selectedUser?.username}
            </DialogDescription>
          </DialogHeader>

          {totpSetupData ? (
            <form onSubmit={handleVerifyTotp} className="space-y-4">
              <div className="text-center space-y-4">
                <p className="text-sm text-muted-foreground">
                  Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
                </p>

                <div className="bg-white p-4 rounded-lg inline-block">
                  <img
                    src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(totpSetupData.provisioning_uri)}`}
                    alt="TOTP QR Code"
                    className="w-48 h-48"
                  />
                </div>

                <div className="space-y-2">
                  <Label>Manual entry code:</Label>
                  <div className="flex items-center gap-2 justify-center">
                    <code className="bg-muted px-3 py-1 rounded text-sm font-mono">
                      {totpSetupData.secret}
                    </code>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => navigator.clipboard.writeText(totpSetupData.secret)}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="totpCode">Enter verification code</Label>
                <Input
                  id="totpCode"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  placeholder="000000"
                  className="text-center text-2xl font-mono tracking-widest"
                  maxLength={6}
                  required
                />
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">
                  View backup codes
                </summary>
                <div className="mt-2 p-3 bg-muted rounded-lg">
                  <p className="text-xs text-muted-foreground mb-2">
                    Save these backup codes in a secure place. Each code can only be used once.
                  </p>
                  <div className="grid grid-cols-2 gap-1 font-mono text-xs">
                    {totpSetupData.backup_codes.map((code, i) => (
                      <div key={i}>{code}</div>
                    ))}
                  </div>
                </div>
              </details>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setShowTotpDialog(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting || totpCode.length !== 6}>
                  {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Verify & Enable
                </Button>
              </DialogFooter>
            </form>
          ) : error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Click outside to close dropdown */}
      {activeDropdown && (
        <div
          className="fixed inset-0 z-0"
          onClick={() => setActiveDropdown(null)}
        />
      )}
    </div>
  )
}
