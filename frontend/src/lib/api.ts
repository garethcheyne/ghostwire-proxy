import axios from 'axios'
import { clearSession, setSessionActive } from './session'

const api = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
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

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (refreshToken) {
          const response = await axios.post(
            `/api/auth/refresh`,
            { refresh_token: refreshToken }
          )

          const { access_token, refresh_token } = response.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', refresh_token)
          setSessionActive()

          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, clear session and redirect to login
        clearSession()
        window.location.href = '/auth/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api
