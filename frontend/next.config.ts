import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://ghostwire-proxy-api:8000'
    return [
      // Collection endpoints - FastAPI routes defined with "/" need trailing slashes
      { source: '/api/proxy-hosts', destination: `${backendUrl}/api/proxy-hosts/` },
      { source: '/api/certificates', destination: `${backendUrl}/api/certificates/` },
      { source: '/api/access-lists', destination: `${backendUrl}/api/access-lists/` },
      { source: '/api/auth-walls', destination: `${backendUrl}/api/auth-walls/` },
      { source: '/api/dns-providers', destination: `${backendUrl}/api/dns-providers/` },
      { source: '/api/dns-zones', destination: `${backendUrl}/api/dns-zones/` },
      { source: '/api/traffic', destination: `${backendUrl}/api/traffic/` },
      { source: '/api/firewalls', destination: `${backendUrl}/api/firewalls` },
      { source: '/api/users', destination: `${backendUrl}/api/users/` },
      { source: '/api/backups', destination: `${backendUrl}/api/backups/` },
      // WAF and System endpoints don't use trailing slash routes
      { source: '/api/waf/rules', destination: `${backendUrl}/api/waf/rules` },
      { source: '/api/waf/rules/sets', destination: `${backendUrl}/api/waf/rules/sets` },
      { source: '/api/system/status', destination: `${backendUrl}/api/system/status` },
      { source: '/api/system/metrics', destination: `${backendUrl}/api/system/metrics` },
      { source: '/api/system/throughput', destination: `${backendUrl}/api/system/throughput` },
      { source: '/api/system/containers', destination: `${backendUrl}/api/system/containers` },
      // Generic fallback for all other API routes
      { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
    ]
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              "connect-src 'self' ws: wss:",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; '),
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
          },
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'off',
          },
        ],
      },
    ]
  },
}

export default nextConfig
