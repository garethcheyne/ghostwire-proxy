import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.qrserver.com',
        pathname: '/v1/create-qr-code/**',
      },
    ],
  },
  serverExternalPackages: ['gray-matter', 'unified', 'remark-parse', 'remark-gfm', 'remark-rehype', 'rehype-raw', 'rehype-stringify'],
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://ghostwire-proxy-api:8000'
    return {
      beforeFiles: [],
      afterFiles: [
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
      ],
      fallback: [
        // Generic fallback for API routes not handled by Next.js route handlers
        { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
      ],
    }
  },
  async headers() {
    const isDev = process.env.NODE_ENV === 'development'
    const isHttps = (process.env.NEXTAUTH_URL || '').startsWith('https://')

    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              // unsafe-inline required for Next.js framework; unsafe-eval only in dev
              isDev
                ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
                : "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob: https://*.basemaps.cartocdn.com",
              "font-src 'self' data:",
              "connect-src 'self' ws: wss: https://*.basemaps.cartocdn.com",
              "worker-src 'self' blob:",
              "manifest-src 'self'",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              // Only upgrade insecure requests when served over HTTPS
              ...(isHttps ? ["upgrade-insecure-requests"] : []),
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
