'use client'

import { useState } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  Loader2,
  KeyRound,
  RefreshCw,
} from 'lucide-react'
import api from '@/lib/api'
import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '@/components/ui/modal'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { LoadError } from '@/components/load-state'
import { usePageData } from '@/lib/use-page-data'
import { toastError, toastSuccess } from '@/lib/toast'

interface MfaStatus {
  enabled: boolean
  verified: boolean
  enrolled_at: string | null
  backup_codes_remaining: number
  required_org_wide: boolean
}

interface Policy {
  required: boolean
  total_active_users: number
  enrolled_count: number
  not_enrolled: { id: string; email: string; name: string; role: string }[]
}

export function MfaCard() {
  const [status, setStatus] = useState<MfaStatus | null>(null)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState(false)

  // Enrolment flow
  const [setupOpen, setSetupOpen] = useState(false)
  const [secret, setSecret] = useState('')
  const [qr, setQr] = useState('')
  const [codes, setCodes] = useState<string[]>([])
  const [savedCodes, setSavedCodes] = useState(false)
  const [verifyCode, setVerifyCode] = useState('')

  // Disable flow
  const [disableOpen, setDisableOpen] = useState(false)
  const [disablePassword, setDisablePassword] = useState('')
  const [disableCode, setDisableCode] = useState('')

  // Backup code regeneration
  const [regenOpen, setRegenOpen] = useState(false)
  const [regenCode, setRegenCode] = useState('')
  const [newCodes, setNewCodes] = useState<string[]>([])

  const load = async () => {
    try {
      const [s, p] = await Promise.all([
        api.get('/api/admin-mfa/status'),
        api.get('/api/admin-mfa/policy').catch(() => null), // admin-only
      ])
      setStatus(s.data)
      if (p) setPolicy(p.data)
      setLoadError(false)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }

  usePageData(() => {
    void load()
  })

  const startSetup = async () => {
    setBusy(true)
    try {
      const { data } = await api.post('/api/admin-mfa/setup', {})
      setSecret(data.secret)
      setQr(data.qr_code || '')
      setCodes(data.backup_codes || [])
      setSavedCodes(false)
      setVerifyCode('')
      setSetupOpen(true)
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not start setup')
    } finally {
      setBusy(false)
    }
  }

  const confirmSetup = async () => {
    setBusy(true)
    try {
      await api.post('/api/admin-mfa/verify', { code: verifyCode.trim() })
      setSetupOpen(false)
      toastSuccess('Two-factor authentication is now enabled on your account.')
      await load()
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'That code did not match')
    } finally {
      setBusy(false)
    }
  }

  const doDisable = async () => {
    setBusy(true)
    try {
      await api.post('/api/admin-mfa/disable', {
        password: disablePassword,
        code: disableCode.trim(),
      })
      setDisableOpen(false)
      setDisablePassword('')
      setDisableCode('')
      toastSuccess('Two-factor authentication disabled.')
      await load()
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not disable two-factor authentication')
    } finally {
      setBusy(false)
    }
  }

  const doRegenerate = async () => {
    setBusy(true)
    try {
      const { data } = await api.post('/api/admin-mfa/backup-codes/regenerate', {
        code: regenCode.trim(),
      })
      setNewCodes(data.backup_codes)
      setRegenCode('')
      await load()
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not regenerate backup codes')
    } finally {
      setBusy(false)
    }
  }

  const togglePolicy = async (required: boolean) => {
    setBusy(true)
    try {
      await api.put('/api/admin-mfa/policy', { required })
      toastSuccess(
        required
          ? 'Two-factor authentication is now required. Anyone not enrolled will be asked to set it up at their next sign-in.'
          : 'The org-wide two-factor requirement has been turned off.'
      )
      await load()
    } catch (e: any) {
      toastError(e.response?.data?.detail || 'Could not change the policy')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading two-factor settings…
        </div>
      </div>
    )
  }

  const enrolled = !!status?.enabled && !!status?.verified
  const lowCodes = enrolled && (status?.backup_codes_remaining ?? 0) <= 3

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <ShieldCheck className="h-5 w-5" />
        Two-Factor Authentication
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        A time-based code from an authenticator app, required in addition to your
        password. This protects the admin portal itself — the account that can
        rewrite every proxy host and read every traffic log.
      </p>

      {loadError ? (
        <LoadError what="two-factor status" onRetry={load} className="border-0 bg-transparent p-0" />
      ) : (
      <>
      {/* Your own account */}
      <div className="flex items-center justify-between py-3 border-t border-border">
        <div>
          <p className="font-medium flex items-center gap-2">
            Your account
            {enrolled ? (
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                Enabled
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400">
                Not enabled
              </span>
            )}
          </p>
          <p className="text-sm text-muted-foreground">
            {enrolled
              ? `${status?.backup_codes_remaining} backup code${
                  status?.backup_codes_remaining === 1 ? '' : 's'
                } remaining`
              : 'Protect your sign-in with an authenticator app'}
          </p>
        </div>
        <div className="flex gap-2">
          {enrolled ? (
            <>
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  setNewCodes([])
                  setRegenOpen(true)
                }}
                disabled={busy}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                New backup codes
              </Button>
              <Button
                variant="outline"
                size="lg"
                onClick={() => setDisableOpen(true)}
                disabled={busy || status?.required_org_wide}
                title={
                  status?.required_org_wide
                    ? 'Two-factor authentication is required for all admin accounts'
                    : undefined
                }
                className="text-destructive hover:text-destructive"
              >
                Disable
              </Button>
            </>
          ) : (
            <Button size="lg" onClick={startSetup} disabled={busy}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
              Set up
            </Button>
          )}
        </div>
      </div>

      {lowCodes && (
        <div className="flex items-center gap-2 p-3 mb-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-sm">
          <ShieldAlert className="h-4 w-4 flex-shrink-0" />
          <span>
            Only {status?.backup_codes_remaining} backup code
            {status?.backup_codes_remaining === 1 ? '' : 's'} left. Generate a new set
            before you run out.
          </span>
        </div>
      )}

      {/* Org-wide policy — admins only */}
      {policy && (
        <div className="pt-3 border-t border-border">
          <div className="flex items-center justify-between">
            <div className="pr-4">
              <p className="font-medium">Require for all admin accounts</p>
              <p className="text-sm text-muted-foreground">
                {policy.enrolled_count} of {policy.total_active_users} active account
                {policy.total_active_users === 1 ? '' : 's'} enrolled.{' '}
                {policy.not_enrolled.length > 0 && (
                  <>
                    Not enrolled: {policy.not_enrolled.map((u) => u.email).join(', ')}. They
                    will be asked to set it up at their next sign-in.
                  </>
                )}
              </p>
              {!enrolled && (
                <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                  Enable it on your own account first — otherwise turning this on would lock
                  you out at your next sign-in.
                </p>
              )}
            </div>
            <Switch
              checked={policy.required}
              disabled={busy || (!enrolled && !policy.required)}
              onCheckedChange={(checked) => togglePolicy(checked)}
              aria-label="Require two-factor authentication for all admin accounts"
              className="flex-shrink-0"
            />
          </div>
        </div>
      )}
      </>
      )}

      {/* ── Setup modal ── */}
      <Modal open={setupOpen} onOpenChange={setSetupOpen} size="md">
        <ModalHeader>
          <ModalTitle>Set up two-factor authentication</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-5">
          <div className="space-y-2">
            <p className="text-sm font-medium">1. Scan with your authenticator app</p>
            {qr && (
              <div className="flex justify-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={qr}
                  alt="Two-factor setup QR code"
                  className="h-44 w-44 rounded-lg border border-border bg-white p-2"
                />
              </div>
            )}
            <div className="rounded-md border border-border bg-muted/50 p-3">
              <p className="text-xs text-muted-foreground mb-1">Or enter this key manually</p>
              <code className="text-sm font-mono break-all select-all">{secret}</code>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">2. Save your backup codes</p>
            <p className="text-xs text-muted-foreground">
              Each works once if you lose your device. They are shown only now.
            </p>
            <div className="grid grid-cols-2 gap-1.5 rounded-md border border-border bg-muted/50 p-3">
              {codes.map((c) => (
                <code key={c} className="text-sm font-mono select-all">
                  {c}
                </code>
              ))}
            </div>
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={savedCodes}
                onCheckedChange={(checked) => setSavedCodes(checked === true)}
                className="mt-0.5"
              />
              <span>I have saved these backup codes somewhere safe</span>
            </label>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">3. Enter the code from your app</p>
            <input
              type="text"
              inputMode="numeric"
              value={verifyCode}
              onChange={(e) => setVerifyCode(e.target.value)}
              maxLength={6}
              placeholder="000000"
              className="w-full h-12 px-4 rounded-md border border-input bg-background text-center text-2xl tracking-[0.4em] font-mono focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="outline" size="lg" onClick={() => setSetupOpen(false)}>
            Cancel
          </Button>
          <Button
            size="lg"
            onClick={confirmSetup}
            disabled={busy || !savedCodes || verifyCode.trim().length < 6}
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Enable
          </Button>
        </ModalFooter>
      </Modal>

      {/* ── Disable modal ── */}
      <Modal open={disableOpen} onOpenChange={setDisableOpen} size="sm">
        <ModalHeader>
          <ModalTitle>Disable two-factor authentication</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Confirm with both factors, so someone at an unattended session cannot quietly
            remove it.
          </p>
          <div className="space-y-2">
            <label className="block text-sm font-medium">Password</label>
            <input
              type="password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium">Current code</label>
            <input
              type="text"
              inputMode="numeric"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value)}
              maxLength={8}
              placeholder="000000"
              className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="outline" size="lg" onClick={() => setDisableOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="lg"
            onClick={doDisable}
            disabled={busy || !disablePassword || disableCode.trim().length < 6}
          >
            Disable
          </Button>
        </ModalFooter>
      </Modal>

      {/* ── Regenerate backup codes modal ── */}
      <Modal open={regenOpen} onOpenChange={setRegenOpen} size="sm">
        <ModalHeader>
          <ModalTitle>New backup codes</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          {newCodes.length === 0 ? (
            <>
              <p className="text-sm text-muted-foreground">
                This invalidates your current codes. Enter a code from your authenticator
                app to confirm — a backup code will not work here.
              </p>
              <input
                type="text"
                inputMode="numeric"
                value={regenCode}
                onChange={(e) => setRegenCode(e.target.value)}
                maxLength={6}
                placeholder="000000"
                className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-hidden focus:ring-2 focus:ring-primary"
              />
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Save these now — they will not be shown again.
              </p>
              <div className="grid grid-cols-2 gap-1.5 rounded-md border border-border bg-muted/50 p-3">
                {newCodes.map((c) => (
                  <code key={c} className="text-sm font-mono select-all">
                    {c}
                  </code>
                ))}
              </div>
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {newCodes.length === 0 ? (
            <>
              <Button variant="outline" size="lg" onClick={() => setRegenOpen(false)}>
                Cancel
              </Button>
              <Button size="lg" onClick={doRegenerate} disabled={busy || regenCode.trim().length < 6}>
                Generate
              </Button>
            </>
          ) : (
            <Button
              size="lg"
              onClick={() => {
                setRegenOpen(false)
                setNewCodes([])
              }}
            >
              Done
            </Button>
          )}
        </ModalFooter>
      </Modal>
    </div>
  )
}
