/**
 * Session management utilities
 * Sets/clears session indicator cookie for middleware auth checks
 */

const SESSION_COOKIE_NAME = 'gw_session_active'

export function setSessionActive(): void {
  if (typeof document === 'undefined') return

  // Set cookie that expires in 7 days (matches refresh token)
  const expires = new Date()
  expires.setDate(expires.getDate() + 7)

  document.cookie = `${SESSION_COOKIE_NAME}=1; path=/; expires=${expires.toUTCString()}; SameSite=Lax`
}

export function clearSession(): void {
  if (typeof document === 'undefined') return

  // Clear the session cookie
  document.cookie = `${SESSION_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`

  // Also clear tokens from localStorage
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function isSessionActive(): boolean {
  if (typeof document === 'undefined') return false

  return document.cookie.includes(`${SESSION_COOKIE_NAME}=1`)
}
