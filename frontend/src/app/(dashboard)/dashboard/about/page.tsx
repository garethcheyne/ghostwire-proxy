'use client'

import { useState, useEffect } from 'react'
import {
  Globe,
  Shield,
  Github,
  Heart,
  ExternalLink,
  Server,
  Code,
  Database,
  Box,
  Layers,
  Cpu,
  FileText,
} from 'lucide-react'
import api from '@/lib/api'
import Link from 'next/link'

interface VersionInfo {
  version: string
  service: string
}

const techStack = [
  { name: 'OpenResty', description: 'Nginx + Lua reverse proxy engine', icon: Server, color: 'text-green-400' },
  { name: 'Next.js 16', description: 'React framework for the admin UI', icon: Layers, color: 'text-blue-400' },
  { name: 'FastAPI', description: 'Python async API backend', icon: Code, color: 'text-teal-400' },
  { name: 'PostgreSQL', description: 'Primary database', icon: Database, color: 'text-sky-400' },
  { name: 'Redis', description: 'Caching, pub/sub, rate limiting', icon: Cpu, color: 'text-red-400' },
  { name: 'Docker', description: 'Containerized deployment', icon: Box, color: 'text-cyan-400' },
]

const features = [
  'Reverse proxy management with Let\'s Encrypt SSL',
  'Web Application Firewall (WAF) with custom rules',
  'Threat detection and automated IP blocking',
  'Honeypot traps for attacker fingerprinting',
  'Firewall integration (UniFi)',
  'GeoIP blocking and rate limiting',
  'Authentication walls (local auth, TOTP)',
  'Access control lists with IP/CIDR rules',
  'Real-time analytics and traffic monitoring',
  'City-level geographic heatmaps',
  'IP enrichment and intelligence lookups',
  'Automated updates with rollback support',
  'Backup and restore system',
  'Security presets for quick configuration',
]

export default function AboutPage() {
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null)

  useEffect(() => {
    api.get('/version')
      .then(res => setVersionInfo(res.data))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="text-center space-y-4 pt-4">
        <div className="flex justify-center">
          <div className="relative h-20 w-20">
            <img
              src="/logo.png"
              alt="Ghostwire Logo"
              className="h-20 w-20 object-contain [filter:brightness(0)_saturate(100%)_invert(71%)_sepia(53%)_saturate(425%)_hue-rotate(162deg)_brightness(95%)_contrast(92%)]"
            />
          </div>
        </div>
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-purple-400 bg-clip-text text-transparent">
            Ghostwire Proxy
          </h1>
          <p className="text-muted-foreground mt-1">
            A modern, self-hosted reverse proxy manager with built-in security
          </p>
        </div>
        {versionInfo && (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-1.5">
            <span className="text-xs text-muted-foreground">Version</span>
            <span className="text-sm font-mono font-bold text-cyan-400">{versionInfo.version}</span>
          </div>
        )}
      </div>

      {/* Description */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-start gap-3">
          <Globe className="h-5 w-5 text-cyan-400 mt-0.5 shrink-0" />
          <div className="space-y-2">
            <h2 className="font-semibold">What is Ghostwire Proxy?</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Ghostwire Proxy is a full-featured reverse proxy management platform that combines the simplicity
              of Nginx Proxy Manager with enterprise-grade security features. It runs as a Docker stack and
              provides a clean web UI for managing proxy hosts, SSL certificates, authentication walls,
              firewall integrations, and more.
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed">
              It is a standalone subproject within the{' '}
              <a
                href="https://github.com/garethcheyne/ghostwire"
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-400 hover:underline inline-flex items-center gap-1"
              >
                Ghostwire <ExternalLink className="h-3 w-3" />
              </a>{' '}
              ecosystem — fully independent, but designed to integrate when needed.
            </p>
          </div>
        </div>
      </div>

      {/* Tech Stack */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <Layers className="h-5 w-5 text-purple-400" />
          Tech Stack
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {techStack.map((tech) => {
            const Icon = tech.icon
            return (
              <div
                key={tech.name}
                className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3"
              >
                <Icon className={`h-5 w-5 ${tech.color} shrink-0`} />
                <div>
                  <p className="text-sm font-medium">{tech.name}</p>
                  <p className="text-xs text-muted-foreground">{tech.description}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Features */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <Shield className="h-5 w-5 text-green-400" />
          Features
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
          {features.map((feature) => (
            <div key={feature} className="flex items-start gap-2 text-sm text-muted-foreground py-1">
              <span className="text-cyan-400 mt-0.5 shrink-0">•</span>
              {feature}
            </div>
          ))}
        </div>
      </div>

      {/* Links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <a
          href="https://github.com/garethcheyne/ghostwire-proxy"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 hover:border-cyan-500/50 transition-colors"
        >
          <Github className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">Source Code</p>
            <p className="text-xs text-muted-foreground">github.com</p>
          </div>
          <ExternalLink className="h-4 w-4 text-muted-foreground ml-auto" />
        </a>

        <Link
          href="/dashboard/license"
          className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 hover:border-cyan-500/50 transition-colors"
        >
          <FileText className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">MIT License</p>
            <p className="text-xs text-muted-foreground">Open source</p>
          </div>
        </Link>

        <a
          href="https://github.com/garethcheyne/ghostwire-proxy/issues"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 hover:border-cyan-500/50 transition-colors"
        >
          <Heart className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">Report Issue</p>
            <p className="text-xs text-muted-foreground">Bug reports & features</p>
          </div>
          <ExternalLink className="h-4 w-4 text-muted-foreground ml-auto" />
        </a>
      </div>

      {/* Copyright */}
      <div className="text-center text-xs text-muted-foreground pb-8">
        <p>
          Made with <Heart className="inline h-3 w-3 text-red-400" /> by{' '}
          <a
            href="https://github.com/garethcheyne"
            target="_blank"
            rel="noopener noreferrer"
            className="text-cyan-400 hover:underline"
          >
            Gareth Cheyne
          </a>
        </p>
        <p className="mt-1">© 2024–2026 · MIT License</p>
      </div>
    </div>
  )
}
