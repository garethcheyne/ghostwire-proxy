'use client'

import { useState } from 'react'
import { Activity, ChevronLeft, ChevronRight, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { IpAddress } from '@/components/ip-address'
import { cn } from '@/lib/utils'
import { useTrafficLogDetail, useTrafficRequests, type TrafficFilters } from '@/lib/queries/traffic'
import { formatBytes, formatMs, formatTime, methodTone, statusTone } from './format'

const PAGE_SIZE = 50

/** Paginated newest-first request list for the filters; a row opens its details. */
export function RequestsTable({
  filters,
  onBackend,
  onClient,
}: {
  filters: TrafficFilters
  onBackend?: (backend: string) => void
  onClient?: (ip: string) => void
}) {
  const [page, setPage] = useState(1)
  const [filterKey, setFilterKey] = useState(filters)
  // A new filter set starts again at page 1.
  if (filterKey !== filters) {
    setFilterKey(filters)
    setPage(1)
  }
  const { data, isPending, isFetching } = useTrafficRequests(filters, page, PAGE_SIZE)
  const [openId, setOpenId] = useState<string>()
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE))

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="overflow-x-auto">
        <Table className={cn(isFetching && !isPending && 'opacity-70 transition-opacity')}>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead className="hidden md:table-cell">Host</TableHead>
              <TableHead className="hidden md:table-cell">Method</TableHead>
              <TableHead>Path</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="hidden lg:table-cell">Client</TableHead>
              <TableHead className="hidden xl:table-cell">Backend</TableHead>
              <TableHead className="hidden md:table-cell text-right">Time taken</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending ? (
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={8}>
                    <Skeleton className="h-5 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : !data?.items.length ? (
              <TableRow>
                <TableCell colSpan={8} className="py-12 text-center text-muted-foreground">
                  <Activity className="mx-auto mb-3 h-10 w-10 opacity-50" />
                  No requests match these filters.
                </TableCell>
              </TableRow>
            ) : (
              data.items.map((log) => (
                <TableRow key={log.id} className="cursor-pointer" onClick={() => setOpenId(log.id)}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {new Date(log.timestamp).toLocaleString()}
                  </TableCell>
                  <TableCell className="hidden max-w-[180px] truncate text-sm md:table-cell" data-private="domain">
                    {log.host_name || '–'}
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <span className={cn('rounded px-2 py-0.5 text-xs font-medium', methodTone(log.request_method))}>
                      {log.request_method}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-[320px] truncate font-mono text-xs" title={log.request_uri}>
                    {log.request_uri}
                  </TableCell>
                  <TableCell>
                    <span className={cn('rounded px-2 py-0.5 text-xs font-medium', statusTone(log.status))}>
                      {log.status}
                    </span>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1.5">
                      <IpAddress ip={log.client_ip} countryCode={log.country_code} countryName={log.country_name} />
                      {onClient && (
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => onClient(log.client_ip)}
                          title="Drill into this client"
                        >
                          <ChevronRight className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs xl:table-cell" onClick={(e) => e.stopPropagation()}>
                    {log.upstream_addr ? (
                      <button
                        type="button"
                        className="hover:underline disabled:no-underline"
                        disabled={!onBackend}
                        onClick={() => onBackend?.(lastUpstream(log.upstream_addr!).replace(/:\d+$/, ''))}
                        title="Drill into this backend"
                      >
                        {lastUpstream(log.upstream_addr)}
                      </button>
                    ) : (
                      '–'
                    )}
                  </TableCell>
                  <TableCell className="hidden text-right text-xs text-muted-foreground md:table-cell">
                    {formatMs(log.response_time)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex items-center justify-between border-t border-border px-4 py-3">
        <p className="text-sm text-muted-foreground">
          {data
            ? `${data.total.toLocaleString()}${data.capped ? '+' : ''} request${data.total === 1 ? '' : 's'} · page ${page} of ${totalPages}${data.capped ? '+' : ''}`
            : ' '}
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" size="icon" disabled={page === 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={!data || (page >= totalPages && !data.capped) || data.items.length < PAGE_SIZE}
            onClick={() => setPage(page + 1)}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <RequestDetailSheet id={openId} onClose={() => setOpenId(undefined)} />
    </div>
  )
}

function lastUpstream(addr: string): string {
  const parts = addr.split(',')
  return parts[parts.length - 1].trim()
}

function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className={cn('break-all text-sm', mono && 'font-mono text-xs')}>{children ?? '–'}</div>
    </div>
  )
}

/** Everything logged for one request. */
export function RequestDetailSheet({ id, onClose }: { id?: string; onClose: () => void }) {
  const { data, isPending } = useTrafficLogDetail(id)
  return (
    <Sheet open={Boolean(id)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Request details</SheetTitle>
          <SheetDescription className="break-all font-mono text-xs">
            {data ? `${data.request_method} ${data.request_uri}` : ' '}
          </SheetDescription>
        </SheetHeader>
        {isPending || !data ? (
          <div className="mt-6 space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <section className="grid grid-cols-2 gap-4">
              <Field label="Time">{formatTime(data.timestamp)}</Field>
              <Field label="Status">
                <span className={cn('rounded px-2 py-0.5 text-xs font-medium', statusTone(data.status))}>{data.status}</span>
              </Field>
              <Field label="Host">{data.host_name}</Field>
              <Field label="Method">{data.request_method}</Field>
              <Field label="Path" mono>
                {data.request_uri}
              </Field>
              <Field label="Query string" mono>
                {data.query_string || '–'}
              </Field>
            </section>

            <section>
              <h4 className="mb-2 text-sm font-medium">Timing and size</h4>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Field label="Total time">{formatMs(data.response_time)}</Field>
                <Field label="Upstream time">{formatMs(data.upstream_response_time)}</Field>
                <Field label="Streaming">{data.is_streaming ? 'Yes (websocket / SSE)' : 'No'}</Field>
                <Field label="Sent">{formatBytes(data.bytes_sent)}</Field>
                <Field label="Received">{formatBytes(data.bytes_received)}</Field>
              </div>
            </section>

            {data.attempts.length > 0 && (
              <section>
                <h4 className="mb-2 text-sm font-medium">
                  Upstream attempts{data.attempts.length > 1 ? ` (failed over ${data.attempts.length - 1}×)` : ''}
                </h4>
                <ol className="space-y-1">
                  {data.attempts.map((a, i) => (
                    <li key={i} className="flex items-center gap-3 rounded-md border border-border px-3 py-1.5 text-xs">
                      <span className="w-4 text-muted-foreground">{i + 1}</span>
                      <span className="font-mono">{a.node}</span>
                      {a.status != null && (
                        <span className={cn('rounded px-1.5 py-0.5 font-medium', statusTone(a.status))}>{a.status}</span>
                      )}
                      {a.status == null && !a.final && <span className="text-red-600 dark:text-red-400">failed</span>}
                      <span className="ml-auto text-muted-foreground">{a.time_ms != null ? formatMs(a.time_ms) : ''}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <section>
              <h4 className="mb-2 text-sm font-medium">Backend</h4>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Upstream" mono>
                  {data.upstream_addr}
                </Field>
                <Field label="Known as">{data.backend?.label || '–'}</Field>
                <Field label="Configured for">
                  {data.backend?.configured_for.length
                    ? data.backend.configured_for.map((c) => `${c.name}:${c.port}`).join(', ')
                    : '–'}
                </Field>
              </div>
            </section>

            <section>
              <h4 className="mb-2 text-sm font-medium">Client</h4>
              <div className="grid grid-cols-2 gap-4">
                <Field label="IP" mono>
                  <IpAddress ip={data.client_ip} countryCode={data.country_code} countryName={data.country_name} />
                </Field>
                <Field label="Location">
                  {[data.city, data.client.region, data.country_name].filter(Boolean).join(', ') || '–'}
                </Field>
                <Field label="Known as">{data.client.known_label || '–'}</Field>
                <Field label="Network">
                  {[data.client.isp || data.client.org, data.client.asn].filter(Boolean).join(' · ') || '–'}
                </Field>
                <Field label="Reverse DNS" mono>
                  {data.client.reverse_dns || '–'}
                </Field>
                <Field label="Signed-in user">{data.auth_user || '–'}</Field>
                <Field label="Bot">{data.is_bot == null ? 'Not classified' : data.is_bot ? 'Yes' : 'No'}</Field>
              </div>
              <div className="mt-4 space-y-4">
                <Field label="User agent" mono>
                  {data.user_agent || '–'}
                </Field>
                <Field label="Referer" mono>
                  {data.referer || '–'}
                </Field>
              </div>
            </section>

            <section>
              <h4 className="mb-2 text-sm font-medium">TLS</h4>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Protocol">{data.ssl_protocol || '–'}</Field>
                <Field label="Cipher" mono>
                  {data.ssl_cipher || '–'}
                </Field>
              </div>
            </section>

            <section>
              <h4 className="mb-2 flex items-center gap-2 text-sm font-medium">
                <ShieldAlert className="h-4 w-4" />
                Security events (same client, ±5 s)
              </h4>
              {data.security_events.length ? (
                <ul className="space-y-2">
                  {data.security_events.map((e) => (
                    <li key={e.id} className="rounded-lg border border-border p-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary">{e.category || 'event'}</Badge>
                        {e.action_taken && <Badge variant="outline">{e.action_taken}</Badge>}
                        {e.severity && <span className="text-muted-foreground">{e.severity}</span>}
                        <span className="ml-auto text-muted-foreground">{formatTime(e.timestamp)}</span>
                      </div>
                      {e.rule_name && <p className="mt-1">{e.rule_name}</p>}
                      {e.matched_payload && <p className="mt-1 break-all font-mono text-muted-foreground">{e.matched_payload}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">None.</p>
              )}
            </section>

            {data.request_headers && (
              <section>
                <h4 className="mb-2 text-sm font-medium">Logged request headers</h4>
                <dl className="space-y-1 font-mono text-xs">
                  {Object.entries(data.request_headers).map(([k, v]) => (
                    <div key={k} className="grid grid-cols-[140px_1fr] gap-2">
                      <dt className="truncate text-muted-foreground">{k}</dt>
                      <dd className="break-all">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
