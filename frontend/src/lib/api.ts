import axios from 'axios'

const api = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

// Request interceptor to add auth token and ensure trailing slashes on collection endpoints
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage or session
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    }

    // Add trailing slash to collection endpoints (those that end with a resource name, not an ID)
    // This fixes the 307 redirect issue with FastAPI
    if (config.url) {
      const collectionEndpoints = [
        '/api/proxy-hosts',
        '/api/certificates',
        '/api/access-lists',
        '/api/auth-walls',
        '/api/waf/rules',
        '/api/waf/rules/sets',
        '/api/dns-providers',
        '/api/dns-zones',
        '/api/firewall/connectors',
        '/api/firewalls',
        '/api/alerts/channels',
        '/api/system/status',
        '/api/system/metrics',
        '/api/system/throughput',
        '/api/system/containers',
        '/api/backups',
        '/api/backups/settings/current',
      ]

      for (const endpoint of collectionEndpoints) {
        if (config.url === endpoint) {
          config.url = `${endpoint}/`
          break
        }
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

          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, redirect to login
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/auth/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api
