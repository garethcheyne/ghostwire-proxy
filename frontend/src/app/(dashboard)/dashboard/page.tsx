'use client'

import { useState, useEffect } from 'react'
import {
  Globe,
  Shield,
  Activity,
  AlertTriangle,
  CheckCircle,
  Server,
  ArrowUp,
  ArrowDown,
  ShieldAlert,
  Ban,
  ShieldX,
  KeyRound,
} from 'lucide-react'
import api from '@/lib/api'
import { formatBytes } from '@/lib/utils'
import { IpAddress } from '@/components/ip-address'
import type { ProxyHost, Certificate, TrafficStats } from '@/types'

interface ThreatStats {
  total_events: number
  events_today: number
  events_this_week: number
  total_actors: number
  blocked_actors: number
  top_categories: { category: string; count: number }[]
  top_actors: { ip: string; score: number; events: number; status: string }[]
  severity_breakdown: Record<string, number>
}

interface AuthErrorSummary {
  total_401: number
  total_403: number
  failed_logins: number
}

interface AuthErrorEvent {
  timestamp: string
  ip: string
  status: number
  method: string
  uri: string
  host: string
  country: string | null
}

interface AuthErrorOffender {
  ip: string
  count: number
  last_seen: string
}

interface FailedLogin {
  timestamp: string
  email: string
  type: string
  ip: string
  details: string | null
}

interface AuthErrors {
  summary: AuthErrorSummary
  recent_events: AuthErrorEvent[]
  top_offenders: AuthErrorOffender[]
  top_hosts: { host: string; count: number }[]
  failed_logins: FailedLogin[]
}

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  description?: string
  trend?: 'up' | 'down' | null
  trendValue?: string
}

function StatCard({ title, value, icon: Icon, description, trend, trendValue }: StatCardProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 sm:p-6">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs sm:text-sm font-medium text-muted-foreground truncate">{title}</p>
          <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-bold truncate">{value}</p>
          {description && (
            <p className="mt-1 text-xs sm:text-sm text-muted-foreground truncate">{description}</p>
          )}
          {trend && trendValue && (
            <div className="mt-2 flex items-center gap-1 text-xs sm:text-sm">
              {trend === 'up' ? (
                <ArrowUp className="h-3 w-3 sm:h-4 sm:w-4 text-green-500" />
              ) : (
                <ArrowDown className="h-3 w-3 sm:h-4 sm:w-4 text-red-500" />
              )}
              <span className={trend === 'up' ? 'text-green-500' : 'text-red-500'}>
                {trendValue}
              </span>
            </div>
          )}
        </div>
        <div className="rounded-lg bg-primary/10 p-2 sm:p-3 shrink-0">
          <Icon className="h-5 w-5 sm:h-6 sm:w-6 text-primary" />
        </div>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [hosts, setHosts] = useState<ProxyHost[]>([])
  const [certificates, setCertificates] = useState<Certificate[]>([])
  const [trafficStats, setTrafficStats] = useState<TrafficStats | null>(null)
  const [threatStats, setThreatStats] = useState<ThreatStats | null>(null)
  const [authErrors, setAuthErrors] = useState<AuthErrors | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [hostsRes, certsRes, trafficRes, threatRes, authRes] = await Promise.all([
        api.get('/api/proxy-hosts'),
        api.get('/api/certificates'),
        api.get('/api/traffic/stats'),
        api.get('/api/waf/stats').catch(() => ({ data: null })),
        api.get('/api/analytics/auth-errors?period=24h').catch(() => ({ data: null })),
      ])
      setHosts(hostsRes.data)
      setCertificates(certsRes.data)
      setTrafficStats(trafficRes.data)
      setThreatStats(threatRes.data)
      setAuthErrors(authRes.data)
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const activeHosts = hosts.filter((h) => h.enabled).length
  const validCerts = certificates.filter((c) => c.status === 'valid').length
  const expiringCerts = certificates.filter((c) => {
    if (!c.expires_at) return false
    const daysUntilExpiry = Math.floor(
      (new Date(c.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    )
    return daysUntilExpiry <= 30 && daysUntilExpiry > 0
  }).length

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold">Dashboard</h1>
        <p className="text-sm sm:text-base text-muted-foreground">
          Overview of your reverse proxy infrastructure
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:gap-6 lg:grid-cols-4">
        <StatCard
          title="Proxy Hosts"
          value={hosts.length}
          icon={Globe}
          description={`${activeHosts} active`}
        />
        <StatCard
          title="SSL Certificates"
          value={certificates.length}
          icon={Shield}
          description={
            expiringCerts > 0
              ? `${expiringCerts} expiring soon`
              : `${validCerts} valid`
          }
        />
        <StatCard
          title="Requests Today"
          value={trafficStats?.requests_today.toLocaleString() || '0'}
          icon={Activity}
        />
        <StatCard
          title="Total Traffic"
          value={formatBytes(
            (trafficStats?.total_bytes_sent || 0) +
              (trafficStats?.total_bytes_received || 0)
          )}
          icon={Server}
        />
      </div>

      {/* Security Stats */}
      {threatStats && (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:gap-6 lg:grid-cols-4">
          <StatCard
            title="Threats Today"
            value={threatStats.events_today}
            icon={ShieldAlert}
            description={`${threatStats.events_this_week} this week`}
          />
          <StatCard
            title="Blocked IPs"
            value={threatStats.blocked_actors}
            icon={Ban}
            description={`${threatStats.total_actors} tracked actors`}
          />
          <StatCard
            title="Total Threats"
            value={threatStats.total_events.toLocaleString()}
            icon={AlertTriangle}
            description={
              threatStats.severity_breakdown.critical
                ? `${threatStats.severity_breakdown.critical} critical`
                : 'All time'
            }
          />
          <StatCard
            title="Top Category"
            value={
              threatStats.top_categories.length > 0
                ? threatStats.top_categories[0].category.replace('_', ' ')
                : 'None'
            }
            icon={Activity}
            description={
              threatStats.top_categories.length > 0
                ? `${threatStats.top_categories[0].count} events`
                : 'No threats detected'
            }
          />
        </div>
      )}

      {/* Recent Activity */}
      <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
        {/* Active Hosts */}
        <div className="rounded-xl border border-border bg-card">
          <div className="border-b border-border p-3 sm:p-4">
            <h2 className="text-sm sm:text-base font-semibold">Active Proxy Hosts</h2>
          </div>
          <div className="p-3 sm:p-4">
            {hosts.length === 0 ? (
              <p className="text-center text-muted-foreground py-6 sm:py-8 text-sm">
                No proxy hosts configured
              </p>
            ) : (
              <div className="space-y-2 sm:space-y-3">
                {hosts.slice(0, 5).map((host) => (
                  <div
                    key={host.id}
                    className="flex items-center justify-between rounded-lg border border-border p-2.5 sm:p-3"
                  >
                    <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
                      <div
                        className={`h-2 w-2 rounded-full shrink-0 ${
                          host.enabled ? 'bg-green-500' : 'bg-gray-400'
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-sm sm:text-base truncate">{host.domain_names[0]}</p>
                        <p className="text-xs sm:text-sm text-muted-foreground truncate">
                          → {host.forward_host}:{host.forward_port}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      {host.ssl_enabled && (
                        <Shield className="h-4 w-4 text-green-500" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Certificates Status */}
        <div className="rounded-xl border border-border bg-card">
          <div className="border-b border-border p-3 sm:p-4">
            <h2 className="text-sm sm:text-base font-semibold">SSL Certificates</h2>
          </div>
          <div className="p-3 sm:p-4">
            {certificates.length === 0 ? (
              <p className="text-center text-muted-foreground py-6 sm:py-8 text-sm">
                No certificates configured
              </p>
            ) : (
              <div className="space-y-2 sm:space-y-3">
                {certificates.slice(0, 5).map((cert) => {
                  const daysUntilExpiry = cert.expires_at
                    ? Math.floor(
                        (new Date(cert.expires_at).getTime() - Date.now()) /
                          (1000 * 60 * 60 * 24)
                      )
                    : null

                  return (
                    <div
                      key={cert.id}
                      className="flex items-center justify-between rounded-lg border border-border p-2.5 sm:p-3 gap-2"
                    >
                      <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
                        {cert.status === 'valid' ? (
                          <CheckCircle className="h-4 w-4 sm:h-5 sm:w-5 text-green-500 shrink-0" />
                        ) : cert.status === 'error' ? (
                          <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-red-500 shrink-0" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-yellow-500 shrink-0" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-sm sm:text-base truncate">{cert.name}</p>
                          <p className="text-xs sm:text-sm text-muted-foreground truncate">
                            {cert.domain_names.slice(0, 2).join(', ')}
                            {cert.domain_names.length > 2 &&
                              ` +${cert.domain_names.length - 2} more`}
                          </p>
                        </div>
                      </div>
                      {daysUntilExpiry !== null && (
                        <span
                          className={`text-xs sm:text-sm shrink-0 ${
                            daysUntilExpiry <= 7
                              ? 'text-red-500'
                              : daysUntilExpiry <= 30
                              ? 'text-yellow-500'
                              : 'text-muted-foreground'
                          }`}
                        >
                          {daysUntilExpiry}d
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Threat Overview */}
      {threatStats && threatStats.top_actors.length > 0 && (
        <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
          {/* Top Threat Actors */}
          <div className="rounded-xl border border-border bg-card">
            <div className="border-b border-border p-4 flex items-center justify-between">
              <h2 className="font-semibold">Top Threat Actors</h2>
              <a href="/dashboard/threats" className="text-xs text-cyan-500 hover:underline">View all →</a>
            </div>
            <div className="p-4">
              <div className="space-y-3">
                {threatStats.top_actors.slice(0, 5).map((actor) => (
                  <div
                    key={actor.ip}
                    className="flex items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`h-2 w-2 rounded-full ${
                          actor.status === 'firewall_banned' || actor.status === 'perm_blocked'
                            ? 'bg-red-500'
                            : actor.status === 'temp_blocked'
                            ? 'bg-orange-500'
                            : actor.status === 'warned'
                            ? 'bg-yellow-500'
                            : 'bg-slate-400'
                        }`}
                      />
                      <div>
                        <IpAddress ip={actor.ip} />
                        <p className="text-xs text-muted-foreground">
                          {actor.events} events • {actor.status.replace('_', ' ')}
                        </p>
                      </div>
                    </div>
                    <span className="text-sm font-semibold text-orange-400">{actor.score}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Threat Categories */}
          <div className="rounded-xl border border-border bg-card">
            <div className="border-b border-border p-4 flex items-center justify-between">
              <h2 className="font-semibold">Attack Categories</h2>
              <a href="/dashboard/waf" className="text-xs text-cyan-500 hover:underline">WAF Rules →</a>
            </div>
            <div className="p-4">
              {threatStats.top_categories.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No threats detected yet
                </p>
              ) : (
                <div className="space-y-3">
                  {threatStats.top_categories.slice(0, 6).map((cat) => {
                    const max = threatStats.top_categories[0].count
                    const pct = max > 0 ? (cat.count / max) * 100 : 0
                    const catColors: Record<string, string> = {
                      sqli: 'bg-red-500',
                      xss: 'bg-orange-500',
                      path_traversal: 'bg-yellow-500',
                      rce: 'bg-purple-500',
                      scanner: 'bg-blue-500',
                    }
                    return (
                      <div key={cat.category} className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="capitalize">{cat.category.replace('_', ' ')}</span>
                          <span className="text-muted-foreground">{cat.count}</span>
                        </div>
                        <div className="h-2 rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${catColors[cat.category] || 'bg-cyan-500'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 403 & Auth Failures Monitor */}
      {authErrors && (authErrors.summary.total_403 > 0 || authErrors.summary.total_401 > 0 || authErrors.summary.failed_logins > 0) && (
        <>
          {/* Auth Error Summary */}
          <div className="grid grid-cols-3 gap-2 sm:gap-4 md:gap-6">
            <div className="rounded-xl border border-orange-500/20 bg-orange-500/5 p-2.5 sm:p-4">
              <div className="flex items-center justify-between">
                <p className="text-[10px] sm:text-sm font-medium text-muted-foreground">403</p>
                <ShieldX className="h-3 w-3 sm:h-4 sm:w-4 text-orange-500" />
              </div>
              <p className="text-lg sm:text-2xl font-bold mt-0.5 sm:mt-1 text-orange-500">{authErrors.summary.total_403}</p>
              <p className="text-[9px] sm:text-xs text-muted-foreground mt-0.5 sm:mt-1 hidden sm:block">Last 24 hours</p>
            </div>
            <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-2.5 sm:p-4">
              <div className="flex items-center justify-between">
                <p className="text-[10px] sm:text-sm font-medium text-muted-foreground">401</p>
                <Ban className="h-3 w-3 sm:h-4 sm:w-4 text-yellow-500" />
              </div>
              <p className="text-lg sm:text-2xl font-bold mt-0.5 sm:mt-1 text-yellow-500">{authErrors.summary.total_401}</p>
              <p className="text-[9px] sm:text-xs text-muted-foreground mt-0.5 sm:mt-1 hidden sm:block">Last 24 hours</p>
            </div>
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-2.5 sm:p-4">
              <div className="flex items-center justify-between">
                <p className="text-[10px] sm:text-sm font-medium text-muted-foreground">Failed</p>
                <KeyRound className="h-3 w-3 sm:h-4 sm:w-4 text-red-500" />
              </div>
              <p className="text-lg sm:text-2xl font-bold mt-0.5 sm:mt-1 text-red-500">{authErrors.summary.failed_logins}</p>
              <p className="text-[9px] sm:text-xs text-muted-foreground mt-0.5 sm:mt-1 hidden sm:block">Last 24 hours</p>
            </div>
          </div>

          <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
            {/* Recent 403/401 Events */}
            <div className="rounded-xl border border-border bg-card">
              <div className="border-b border-border p-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldX className="h-4 w-4 text-orange-500" />
                  <h2 className="font-semibold">Recent 403/401 Events</h2>
                </div>
                <a href="/dashboard/analytics" className="text-xs text-cyan-500 hover:underline">Analytics →</a>
              </div>
              <div className="p-4 max-h-80 overflow-y-auto">
                {authErrors.recent_events.length === 0 ? (
                  <p className="text-center text-muted-foreground py-4">No events in this period</p>
                ) : (
                  <div className="space-y-2">
                    {authErrors.recent_events.slice(0, 15).map((evt, idx) => (
                      <div key={idx} className="flex items-start gap-3 rounded-lg border border-border p-2.5 text-sm">
                        <span className={`shrink-0 text-xs font-mono font-bold px-1.5 py-0.5 rounded ${
                          evt.status === 403 ? 'bg-orange-500/10 text-orange-500' : 'bg-yellow-500/10 text-yellow-500'
                        }`}>
                          {evt.status}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <IpAddress ip={evt.ip} />
                            <span className="text-xs text-muted-foreground">→</span>
                            <span className="text-xs font-medium truncate">{evt.host}</span>
                          </div>
                          <code className="text-xs text-muted-foreground block truncate mt-0.5">
                            {evt.method} {evt.uri}
                          </code>
                        </div>
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap shrink-0">
                          {new Date(evt.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Top Offenders & Failed Logins */}
            <div className="space-y-6">
              {/* Top Offenders */}
              <div className="rounded-xl border border-border bg-card">
                <div className="border-b border-border p-4">
                  <h2 className="font-semibold">Top Offenders (403/401)</h2>
                </div>
                <div className="p-4">
                  {authErrors.top_offenders.length === 0 ? (
                    <p className="text-center text-muted-foreground py-4">No offenders</p>
                  ) : (
                    <div className="space-y-2">
                      {authErrors.top_offenders.map((ip) => {
                        const max = authErrors.top_offenders[0]?.count || 1
                        const pct = (ip.count / max) * 100
                        return (
                          <div key={ip.ip}>
                            <div className="flex items-center justify-between text-sm mb-1">
                              <IpAddress ip={ip.ip} />
                              <span className="text-xs text-muted-foreground">{ip.count} hits</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                              <div className="h-full rounded-full bg-orange-500" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Failed Logins */}
              {authErrors.failed_logins.length > 0 && (
                <div className="rounded-xl border border-red-500/20 bg-card">
                  <div className="border-b border-border p-4 flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-red-500" />
                    <h2 className="font-semibold">Failed Login Attempts</h2>
                  </div>
                  <div className="p-4">
                    <div className="space-y-2">
                      {authErrors.failed_logins.slice(0, 8).map((login, idx) => (
                        <div key={idx} className="flex items-center justify-between rounded-lg border border-border p-2.5 text-sm">
                          <div className="flex items-center gap-3 min-w-0">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                              login.type === 'admin' ? 'bg-red-500/10 text-red-500' : 'bg-yellow-500/10 text-yellow-500'
                            }`}>
                              {login.type}
                            </span>
                            <div className="min-w-0">
                              <span className="text-xs font-medium">{login.email || 'Unknown'}</span>
                              <span className="text-xs text-muted-foreground ml-2 inline-flex items-center gap-1">from <IpAddress ip={login.ip || '?'} /></span>
                            </div>
                          </div>
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {new Date(login.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
