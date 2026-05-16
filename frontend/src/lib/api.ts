import axios from 'axios'
import { clearSession, setSessionActive } from './session'
import { toastError } from './toast'

const api = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 30000,
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage or session
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Shared refresh promise to deduplicate concurrent 401 refreshes
let refreshPromise: Promise<string> | null = null

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // If a refresh is already in flight, wait for it.
        // Clear the shared promise inside .finally so the next 401 starts a fresh
        // refresh — avoids a race where two requests both see a stale `null`.
        if (!refreshPromise) {
          refreshPromise = (async () => {
            const refreshToken = localStorage.getItem('refresh_token')
            if (!refreshToken) throw new Error('No refresh token')

            const response = await axios.post(
              `/api/auth/refresh`,
              { refresh_token: refreshToken }
            )

            const { access_token, refresh_token } = response.data
            localStorage.setItem('access_token', access_token)
            localStorage.setItem('refresh_token', refresh_token)
            setSessionActive()
            return access_token
          })().finally(() => {
            refreshPromise = null
          })
        }

        const newToken = await refreshPromise
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      } catch (refreshError) {
        // Refresh failed, clear session and redirect to login
        clearSession()
        window.location.href = '/auth/login'
        return Promise.reject(refreshError)
      }
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
