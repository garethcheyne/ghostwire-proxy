'use client'

import { useState, useCallback } from 'react'
import { Globe, Shield, AlertTriangle, Crosshair, Loader2 } from 'lucide-react'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import api from '@/lib/api'

interface IpAddressProps {
  ip: string
  countryCode?: string | null
  countryName?: string | null
  className?: string
}

// Simple in-memory cache for enrichment data
const enrichmentCache: Record<string, { data: any; fetchedAt: number }> = {}
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

/**
 * Country badge that shows initials instead of emoji flags
 * (emoji flags don't render on Windows desktop).
 */
export function CountryBadge({ code, name }: { code: string; name?: string | null }) {
  return (
    <span
      className="inline-flex items-center justify-center h-5 w-7 rounded text-[10px] font-bold bg-muted text-muted-foreground shrink-0 uppercase"
      title={name || code}
    >
      {code}
    </span>
  )
}

/**
 * Reusable IP address display with hover card showing enrichment intel.
 *
 * Usage:
 *   <IpAddress ip="1.2.3.4" />
 *   <IpAddress ip="1.2.3.4" countryCode="US" countryName="United States" />
 */
export function IpAddress({ ip, countryCode, countryName, className }: IpAddressProps) {
  const [data, setData] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const fetchEnrichment = useCallback(async () => {
    // Check cache
    const cached = enrichmentCache[ip]
    if (cached && Date.now() - cached.fetchedAt < CACHE_TTL) {
      setData(cached.data)
      return
    }

    setLoading(true)
    setError(false)
    try {
      const res = await api.get(`/api/honeypot/enrich/${encodeURIComponent(ip)}`)
      enrichmentCache[ip] = { data: res.data, fetchedAt: Date.now() }
      setData(res.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [ip])

  return (
    <HoverCard openDelay={300} closeDelay={100}>
      <HoverCardTrigger asChild>
        <button
          className={`inline-flex items-center gap-1.5 font-mono text-xs font-semibold hover:text-blue-400 transition-colors cursor-pointer ${className || ''}`}
          onMouseEnter={fetchEnrichment}
          onFocus={fetchEnrichment}
          data-private="ip"
        >
          {countryCode && <CountryBadge code={countryCode} name={countryName} />}
          <span data-private="ip">{ip}</span>
        </button>
      </HoverCardTrigger>
      <HoverCardContent side="top" align="start" className="w-80 p-0">
        <div className="p-3 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-blue-500 shrink-0" />
            <code className="text-sm font-bold">{ip}</code>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            <span className="text-xs">Loading intel...</span>
          </div>
        )}

        {error && !loading && (
          <div className="text-xs text-muted-foreground text-center py-6">
            Could not load enrichment data
          </div>
        )}

        {data && !loading && (
          <div className="divide-y">
            {/* Location */}
            <div className="p-3 space-y-1.5">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                <Globe className="h-3 w-3" /> Location
              </h4>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <Row label="Country" value={data.country_name ? `${data.country_name} (${data.country_code})` : null} />
                <Row label="City" value={data.city} />
                <Row label="Region" value={data.region} />
                <Row label="TZ" value={data.timezone} />
              </div>
            </div>

            {/* Network */}
            <div className="p-3 space-y-1.5">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                <Shield className="h-3 w-3" /> Network
              </h4>
              <div className="grid grid-cols-1 gap-y-1 text-xs">
                <Row label="ISP" value={data.isp} />
                <Row label="Org" value={data.org} />
                <Row label="ASN" value={data.asn} mono />
                <Row label="rDNS" value={data.reverse_dns} mono />
              </div>
            </div>

            {/* Reputation + Flags */}
            <div className="p-3 space-y-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" /> Reputation
              </h4>
              {data.abuse_score !== null && data.abuse_score !== undefined ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Abuse:</span>
                  <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        data.abuse_score > 75 ? 'bg-red-500' :
                        data.abuse_score > 50 ? 'bg-orange-500' :
                        data.abuse_score > 25 ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(data.abuse_score, 100)}%` }}
                    />
                  </div>
                  <span className={`text-xs font-bold ${
                    data.abuse_score > 75 ? 'text-red-500' :
                    data.abuse_score > 50 ? 'text-orange-500' :
                    data.abuse_score > 25 ? 'text-yellow-500' : 'text-green-500'
                  }`}>
                    {data.abuse_score}%
                  </span>
                </div>
              ) : (
                <span className="text-[10px] text-muted-foreground">No AbuseIPDB data</span>
              )}
              <div className="flex flex-wrap gap-1">
                <Flag label="Tor" value={data.is_tor} />
                <Flag label="Proxy" value={data.is_proxy} />
                <Flag label="VPN" value={data.is_vpn} />
                <Flag label="DC" value={data.is_datacenter} />
              </div>
            </div>
          </div>
        )}
      </HoverCardContent>
    </HoverCard>
  )
}

function Row({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`truncate text-right ${mono ? 'font-mono text-[10px]' : ''}`}>{value}</span>
    </div>
  )
}

function Flag({ label, value }: { label: string; value: boolean | null }) {
  if (value === null || value === undefined) return null
  if (!value) return null
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-500 border border-red-500/20 font-medium">
      {label}
    </span>
  )
}

export default IpAddress
