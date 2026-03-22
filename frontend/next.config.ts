import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://ghostwire-proxy-api:8000'
    return [
      // Collection endpoints need trailing slashes
      { source: '/api/proxy-hosts', destination: `${backendUrl}/api/proxy-hosts/` },
      { source: '/api/certificates', destination: `${backendUrl}/api/certificates/` },
      { source: '/api/access-lists', destination: `${backendUrl}/api/access-lists/` },
      { source: '/api/auth-walls', destination: `${backendUrl}/api/auth-walls/` },
      { source: '/api/dns-providers', destination: `${backendUrl}/api/dns-providers/` },
      { source: '/api/dns-zones', destination: `${backendUrl}/api/dns-zones/` },
      { source: '/api/traffic', destination: `${backendUrl}/api/traffic/` },
      { source: '/api/waf/rules', destination: `${backendUrl}/api/waf/rules/` },
      { source: '/api/waf/rules/sets', destination: `${backendUrl}/api/waf/rules/sets/` },
      { source: '/api/firewall/connectors', destination: `${backendUrl}/api/firewall/connectors/` },
      { source: '/api/firewalls', destination: `${backendUrl}/api/firewalls/` },
      { source: '/api/alerts/channels', destination: `${backendUrl}/api/alerts/channels/` },
      { source: '/api/users', destination: `${backendUrl}/api/users/` },
      { source: '/api/system/status', destination: `${backendUrl}/api/system/status/` },
      { source: '/api/system/metrics', destination: `${backendUrl}/api/system/metrics/` },
      { source: '/api/system/throughput', destination: `${backendUrl}/api/system/throughput/` },
      { source: '/api/system/containers', destination: `${backendUrl}/api/system/containers/` },
      { source: '/api/backups', destination: `${backendUrl}/api/backups/` },
      { source: '/api/backups/settings/current', destination: `${backendUrl}/api/backups/settings/current/` },
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
        ],
      },
    ]
  },
}

export default nextConfig
