import axios from 'axios'
import { clearLegacySession } from './session'
import { toastError } from './toast'

const api = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 30000,
})

// The session is Better Auth's httpOnly cookie, sent with every same-origin request; the API
// reads it directly. A 401 means it expired or was revoked (password change, account disabled).
let redirectingToLogin = false

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && typeof window !== 'undefined') {
      if (!redirectingToLogin && !window.location.pathname.startsWith('/auth/')) {
        redirectingToLogin = true
        clearLegacySession()
        const next = window.location.pathname + window.location.search
        window.location.href = `/auth/login?next=${encodeURIComponent(next)}`
      }
      return Promise.reject(error)
    }

    // Surface common non-auth failures as a single, consistent toast so every
    // page doesn't have to repeat the same error-handling boilerplate.
    const status = error.response?.status
    const url = (originalRequest?.url || '') as string
    // Skip toasts for background polling endpoints (analytics/stats) to avoid spam.
    const isBackgroundCall = /\/(stats|auth-errors|metrics|health)/i.test(url)
    if (!isBackgroundCall) {
      if (status === 403) {
        toastError('You do not have permission to perform this action.')
      } else if (status && status >= 500) {
        toastError('Server error — please try again in a moment.')
      } else if (error.code === 'ECONNABORTED') {
        toastError('Request timed out — the server is taking too long to respond.')
      }
    }

    return Promise.reject(error)
  }
)

export default api
