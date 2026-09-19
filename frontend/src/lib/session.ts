/**
 * Sign-out helpers. Sessions are Better Auth's httpOnly cookie; the tokens earlier versions kept
 * in localStorage (and the gw_session_active cookie) are cleared so nothing stale is left behind.
 */
import { authClient } from './auth-client'

export function clearLegacySession(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  document.cookie = 'gw_session_active=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
}

/** Ends the session and goes to the sign-in page. */
export async function signOutAndRedirect(): Promise<void> {
  try {
    await authClient.signOut()
  } catch {
    // Already signed out, or the server is unreachable; either way leave the dashboard.
  }
  clearLegacySession()
  window.location.href = '/auth/login'
}
