import type { AuthWallConfig, LoginResponse, TotpResponse } from './types'

const API_BASE = '/api/auth-portal'

export async function getAuthWallConfig(wallId: string): Promise<AuthWallConfig> {
  const res = await fetch(`${API_BASE}/${wallId}/config`)
  if (!res.ok) {
    throw new Error('Failed to load authentication configuration')
  }
  return res.json()
}

export async function loginLocal(
  wallId: string,
  username: string,
  password: string
): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/${wallId}/login/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  })
  return res.json()
}

export async function verifyTotp(
  wallId: string,
  partialSessionId: string,
  code: string,
  isBackupCode: boolean = false
): Promise<TotpResponse> {
  const res = await fetch(`${API_BASE}/${wallId}/login/totp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      partial_session_id: partialSessionId,
      code,
      is_backup_code: isBackupCode,
    }),
    credentials: 'include',
  })
  return res.json()
}

export async function logout(wallId: string): Promise<void> {
  await fetch(`${API_BASE}/${wallId}/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export function getOAuthStartUrl(wallId: string, providerId: string, redirect: string): string {
  const params = new URLSearchParams({ redirect })
  return `${API_BASE}/${wallId}/oauth/${providerId}/start?${params}`
}
