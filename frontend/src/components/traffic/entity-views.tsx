'use client'

import { useState } from 'react'
import { ArrowLeft, Globe, Monitor, Server, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import {
  useBackendInfo,
  useClientInfo,
  useTrafficBackends,
  useTrafficOverview,
  useTrafficTop,
  type BackendHealth,
  type TrafficFilters,
} from '@/lib/queries/traffic'
import { RequestsTable } from './requests-table'
import { NodesPanel } from './nodes-panel'
import { LatencyChart, Panel, RequestsChart, StatusCodes, SummaryCards, TopList } from './traffic-panels'
import { formatBytes, formatCount, formatMs, formatPct, formatTime } from './format'

export type EntityKind = 'backend' | 'host' | 'client'

export interface Drill {
  kind: EntityKind
  id: string
}

/** The filters with the entity pinned (backend / proxy host / client IP). */
export function withEntity(f: TrafficFilters, drill: Drill): TrafficFilters {
  if (drill.kind === 'backend') return { ...f, backend: [drill.id] }
  if (drill.kind === 'host') return { ...f, host: [drill.id] }
  return { ...f, clientIp: drill.id }
}

/** Overview of whatever the filters match: cards, charts, codes, top lists, requests. */
export function TrafficOverviewView({
  filters,
  onFilter,
  onDrill,
  hide = {},
}: {
  filters: TrafficFilters
  onFilter: (patch: Partial<TrafficFilters>) => void
  onDrill: (d: Drill) => void
  hide?: Partial<Record<'hosts' | 'backends' | 'clients', boolean>>
}) {
  const { data, isPending } = useTrafficOverview(filters)
  const paths = useTrafficTop(filters, 'path', 10)
  const clients = useTrafficTop(filters, 'client_ip', 10, !hide.clients)
  const countries = useTrafficTop(filters, 'country', 10)
  const hosts = useTrafficTop(filters, 'proxy_host', 10, !hide.hosts)
  const backends = useTrafficTop(filters, 'backend_host', 10, !hide.backends)

  return (
    <div className="space-y-4">
      <SummaryCards data={data} loading={isPending} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Requests by status">
          <RequestsChart data={data} />
        </Panel>
        <Panel title="Latency (p50 / p95)">
          <LatencyChart data={data} />
        </Panel>
      </div>
      <Panel title="Status codes">
        <StatusCodes data={data} onSelect={(code) => onFilter({ status: [String(code)] })} />
      </Panel>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Panel title="Top paths">
          <TopList items={paths.data} loading={paths.isPending} onSelect={(i) => onFilter({ path: i.value, pathMode: 'prefix' })} />
        </Panel>
        {!hide.clients && (
          <Panel title="Top clients">
            <TopList
              items={clients.data}
              loading={clients.isPending}
              onSelect={(i) => onDrill({ kind: 'client', id: i.value })}
              render={(i) => (
                <>
                  {i.value}
                  {i.label && <span className="ml-2 text-muted-foreground">{i.label}</span>}
                  {i.known_label && <span className="ml-2 text-brand">{i.known_label}</span>}
                </>
              )}
            />
          </Panel>
        )}
        <Panel title="Countries">
          <TopList
            items={countries.data}
            loading={countries.isPending}
            onSelect={(i) => i.value && onFilter({ country: [i.value] })}
            render={(i) => (
              <>
                {i.value || 'Unknown'}
                {i.label && <span className="ml-2 text-muted-foreground">{i.label}</span>}
              </>
            )}
          />
        </Panel>
        {!hide.hosts && (
          <Panel title="Proxy hosts">
            <TopList
              items={hosts.data}
              loading={hosts.isPending}
              onSelect={(i) => onDrill({ kind: 'host', id: i.value })}
              render={(i) => i.label || i.value}
            />
          </Panel>
        )}
        {!hide.backends && (
          <Panel title="Backends">
            <TopList
              items={backends.data}
              loading={backends.isPending}
              onSelect={(i) => i.value && onDrill({ kind: 'backend', id: i.value })}
              render={(i) => i.value || '(answered by the proxy)'}
            />
          </Panel>
        )}
      </div>
      <RequestsTable
        filters={filters}
        onBackend={hide.backends ? undefined : (b) => onDrill({ kind: 'backend', id: b })}
        onClient={hide.clients ? undefined : (ip) => onDrill({ kind: 'client', id: ip })}
      />
    </div>
  )
}

/** Header + extra facts for a drilled-into backend / host / client, then the overview. */
export function EntityView({
  drill,
  filters,
  hostName,
  onBack,
  onFilter,
  onDrill,
}: {
  drill: Drill
  filters: TrafficFilters
  hostName?: string
  onBack: () => void
  onFilter: (patch: Partial<TrafficFilters>) => void
  onDrill: (d: Drill) => void
}) {
  const Icon = drill.kind === 'backend' ? Server : drill.kind === 'host' ? Globe : User
  const title = drill.kind === 'host' ? (hostName ?? drill.id) : drill.id
  const kindLabel = drill.kind === 'backend' ? 'Backend' : drill.kind === 'host' ? 'Proxy host' : 'Client'
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" className="h-9" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-5 w-5 shrink-0 text-brand" />
          <span className="text-sm text-muted-foreground">{kindLabel}</span>
          <span className="truncate font-mono text-base font-semibold" data-private={drill.kind === 'host' ? 'domain' : undefined}>
            {title}
          </span>
        </div>
      </div>
      {drill.kind === 'backend' && <BackendFacts backend={drill.id} />}
      {drill.kind === 'client' && <ClientFacts ip={drill.id} />}
      {drill.kind !== 'client' && (
        <NodesPanel
          filters={withEntity(filters, drill)}
          onNode={drill.kind === 'host' ? (node) => onFilter({ backend: [node] }) : undefined}
        />
      )}
      <TrafficOverviewView
        filters={withEntity(filters, drill)}
        onFilter={onFilter}
        onDrill={onDrill}
        hide={{ backends: false, hosts: drill.kind === 'host', clients: drill.kind === 'client' }}
      />
    </div>
  )
}

function HealthBadge({ h }: { h: BackendHealth }) {
  const tone =
    h.down || !h.enabled
      ? 'bg-muted text-muted-foreground'
      : h.status === 'up'
        ? 'bg-green-500/10 text-green-600 dark:text-green-400'
        : h.status === 'down'
          ? 'bg-red-500/10 text-red-600 dark:text-red-400'
          : 'bg-muted text-muted-foreground'
  const label = !h.enabled ? 'disabled' : h.down ? 'maintenance' : (h.status ?? 'unknown')
  return (
    <span className={cn('rounded px-2 py-0.5 text-xs font-medium', tone)} title={h.error ?? undefined}>
      :{h.port} {label}
      {h.latency_ms != null && h.status === 'up' ? ` · ${h.latency_ms} ms` : ''}
      {h.backup ? ' · backup' : ''}
    </span>
  )
}

function BackendFacts({ backend }: { backend: string }) {
  const { data } = useBackendInfo(backend)
  if (!data) return <Skeleton className="h-14 w-full rounded-xl" />
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border bg-card p-4 text-sm">
      <div>
        <span className="text-muted-foreground">Known as </span>
        <span className="font-medium">{data.label || '–'}</span>
      </div>
      <div className="min-w-0">
        <span className="text-muted-foreground">Configured for </span>
        {data.configured_for.length
          ? data.configured_for.map((c) => (
              <Badge key={`${c.id}:${c.port}:${c.via}`} variant="secondary" className="mr-1 font-normal">
                {c.name} → :{c.port}
              </Badge>
            ))
          : '–'}
      </div>
      {data.health.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground">Health </span>
          {data.health.map((h, i) => (
            <HealthBadge key={i} h={h} />
          ))}
        </div>
      )}
    </div>
  )
}

function ClientFacts({ ip }: { ip: string }) {
  const { data } = useClientInfo(ip)
  if (!data) return <Skeleton className="h-14 w-full rounded-xl" />
  const e = data.enrichment
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border bg-card p-4 text-sm">
      <div>
        <span className="text-muted-foreground">Known as </span>
        <span className="font-medium">{data.known?.label || '–'}</span>
        {data.known?.trusted && (
          <Badge variant="secondary" className="ml-2 font-normal">
            trusted
          </Badge>
        )}
      </div>
      <div>
        <span className="text-muted-foreground">Location </span>
        {e ? [e.city, e.region, e.country_name].filter(Boolean).join(', ') || '–' : 'not enriched yet'}
      </div>
      {e && (
        <div>
          <span className="text-muted-foreground">Network </span>
          {[e.isp || e.org, e.asn].filter(Boolean).join(' · ') || '–'}
          {e.is_tor ? ' · Tor' : ''}
          {e.is_vpn ? ' · VPN' : ''}
          {e.is_datacenter ? ' · datacenter' : ''}
        </div>
      )}
      {data.threat && (
        <div>
          <span className="text-muted-foreground">Threat </span>
          <span className="font-medium">{data.threat.status}</span>
          <span className="text-muted-foreground"> · score {data.threat.score} · {data.threat.events} events</span>
        </div>
      )}
    </div>
  )
}

/** Every backend (VM) in the window with its figures; a row drills in. */
export function BackendsView({ filters, onDrill }: { filters: TrafficFilters; onDrill: (d: Drill) => void }) {
  const [group, setGroup] = useState<'host' | 'hostport'>('host')
  const { data, isPending, isFetching } = useTrafficBackends(filters, group)
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex w-full gap-1 overflow-x-auto rounded-lg bg-muted p-1 sm:w-fit">
          {(
            [
              ['host', 'By machine'],
              ['hostport', 'By machine and port'],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              onClick={() => setGroup(v)}
              className={cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium',
                group === v ? 'bg-background shadow-sm' : 'text-muted-foreground hover:bg-background/50'
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          The upstream that answered each request (the last one when nginx retried).
        </p>
      </div>
      <div className="rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <Table className={cn(isFetching && !isPending && 'opacity-70 transition-opacity')}>
            <TableHeader>
              <TableRow>
                <TableHead>Backend</TableHead>
                <TableHead className="text-right">Requests</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="hidden text-right md:table-cell">p50 / p95</TableHead>
                <TableHead className="hidden text-right lg:table-cell">Out / in</TableHead>
                <TableHead className="hidden lg:table-cell">Serves</TableHead>
                <TableHead className="hidden xl:table-cell">Last seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              ) : !data?.length ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-12 text-center text-muted-foreground">
                    <Monitor className="mx-auto mb-3 h-10 w-10 opacity-50" />
                    No backend traffic in this window.
                  </TableCell>
                </TableRow>
              ) : (
                data.map((b) => (
                  <TableRow
                    key={b.backend || '(none)'}
                    className={cn(b.backend && 'cursor-pointer')}
                    onClick={() => b.backend && onDrill({ kind: 'backend', id: b.backend })}
                  >
                    <TableCell>
                      <div className="font-mono text-sm">{b.backend || '(answered by the proxy)'}</div>
                      <div className="text-xs text-muted-foreground">
                        {b.label ||
                          (b.configured_for.length ? `forward host of ${b.configured_for.map((c) => c.name).join(', ')}` : '')}
                        {b.health.some((h) => h.status === 'down' && !h.down) && (
                          <span className="ml-2 text-red-600 dark:text-red-400">health check failing</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatCount(b.requests)}</TableCell>
                    <TableCell
                      className={cn(
                        'text-right tabular-nums',
                        b.server_error_rate >= 5 ? 'text-red-600 dark:text-red-400' : b.error_rate >= 10 ? 'text-amber-700 dark:text-amber-400' : ''
                      )}
                    >
                      {formatPct(b.error_rate)}
                      <div className="text-xs text-muted-foreground">{formatCount(b.errors_5xx)} 5xx</div>
                    </TableCell>
                    <TableCell className="hidden text-right text-sm md:table-cell">
                      {formatMs(b.p50)} / {formatMs(b.p95)}
                    </TableCell>
                    <TableCell className="hidden text-right text-sm lg:table-cell">
                      {formatBytes(b.bytes_sent)} / {formatBytes(b.bytes_received)}
                    </TableCell>
                    <TableCell className="hidden max-w-[260px] lg:table-cell">
                      <div className="truncate text-sm" data-private="domain" title={b.hosts.map((h) => h.name).join(', ')}>
                        {b.hosts.slice(0, 3).map((h) => h.name).join(', ')}
                        {b.hosts.length > 3 ? ` +${b.hosts.length - 3}` : ''}
                      </div>
                    </TableCell>
                    <TableCell className="hidden whitespace-nowrap text-xs text-muted-foreground xl:table-cell">
                      {formatTime(b.last_seen)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}

/** Proxy hosts or clients ranked by requests; a row drills in. */
export function RankedView({
  filters,
  kind,
  onDrill,
}: {
  filters: TrafficFilters
  kind: 'host' | 'client'
  onDrill: (d: Drill) => void
}) {
  const { data, isPending } = useTrafficTop(filters, kind === 'host' ? 'proxy_host' : 'client_ip', 50)
  return (
    <Panel
      title={kind === 'host' ? 'Proxy hosts by requests' : 'Clients by requests (top 50)'}
      action={<span className="text-xs text-muted-foreground">Select one to see its traffic</span>}
    >
      <TopList
        items={data}
        loading={isPending}
        onSelect={(i) => i.value && onDrill({ kind, id: i.value })}
        render={(i) => (
          <>
            <span data-private={kind === 'host' ? 'domain' : undefined}>{kind === 'host' ? i.label || i.value : i.value}</span>
            {kind === 'client' && i.label && <span className="ml-2 text-muted-foreground">{i.label}</span>}
            {i.known_label && <span className="ml-2 text-brand">{i.known_label}</span>}
          </>
        )}
      />
    </Panel>
  )
}
