'use client'

import { Suspense, useCallback, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { Activity as HeaderIcon, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/layout/page-header'
import { useConfirm } from '@/components/confirm-dialog'
import api from '@/lib/api'
import { toastError, toastSuccess } from '@/lib/toast'
import { cn } from '@/lib/utils'
import { trafficKeys } from '@/lib/queries/keys'
import { useProxyHosts } from '@/lib/queries/proxy-hosts'
import { filtersToParams, parseFilters, type TrafficFilters } from '@/lib/queries/traffic'
import { TrafficFiltersBar } from '@/components/traffic/traffic-filters'
import {
  BackendsView,
  EntityView,
  RankedView,
  TrafficOverviewView,
  type Drill,
  type EntityKind,
} from '@/components/traffic/entity-views'

const TABS = [
  { value: 'requests', label: 'Overview' },
  { value: 'backends', label: 'Backends' },
  { value: 'hosts', label: 'Hosts' },
  { value: 'clients', label: 'Clients' },
] as const
type Tab = (typeof TABS)[number]['value']
const KINDS: EntityKind[] = ['backend', 'host', 'client']

export default function TrafficPage() {
  // useSearchParams needs a Suspense boundary; the fallback is a plain skeleton.
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
      <TrafficPageContent />
    </Suspense>
  )
}

function TrafficPageContent() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const confirm = useConfirm()
  const { data: hostsData } = useProxyHosts({ limit: 100 })

  // The URL is the single source of truth, so every view is shareable and
  // back/forward walk through drill-downs.
  const query = searchParams.toString()
  const filters = useMemo(() => parseFilters(new URLSearchParams(query)), [query])
  const tabParam = searchParams.get('tab')
  const tab: Tab = TABS.some((t) => t.value === tabParam) ? (tabParam as Tab) : 'requests'
  const view = searchParams.get('view') as EntityKind | null
  const id = searchParams.get('id')
  const drill = useMemo<Drill | null>(
    () => (view && KINDS.includes(view) && id ? { kind: view, id } : null),
    [view, id]
  )

  const go = useCallback(
    (next: { filters?: TrafficFilters; tab?: Tab; drill?: Drill | null }, push = false) => {
      const p = filtersToParams(next.filters ?? filters)
      const t = next.tab ?? tab
      if (t !== 'requests') p.set('tab', t)
      const d = next.drill === undefined ? drill : next.drill
      if (d) {
        p.set('view', d.kind)
        p.set('id', d.id)
      }
      const url = `${pathname}?${p.toString()}`
      if (push) router.push(url, { scroll: false })
      else router.replace(url, { scroll: false })
    },
    [filters, tab, drill, pathname, router]
  )

  const setFilters = (f: TrafficFilters) => go({ filters: f })
  const patchFilters = (patch: Partial<TrafficFilters>) => go({ filters: { ...filters, ...patch } })
  const openDrill = (d: Drill) => go({ drill: d }, true)

  const refresh = () => queryClient.invalidateQueries({ queryKey: trafficKeys.all })

  const purge = async () => {
    if (!(await confirm({ description: 'Delete ALL traffic logs? This cannot be undone.', variant: 'destructive' }))) return
    try {
      await api.delete('/api/traffic')
      refresh()
      toastSuccess('Traffic logs purged')
    } catch {
      toastError('Failed to purge traffic logs')
    }
  }

  const hostName =
    drill?.kind === 'host' ? hostsData?.items.find((h) => h.id === drill.id)?.domain_names[0] : undefined

  return (
    <div className="space-y-6">
      <PageHeader
        icon={HeaderIcon}
        title="Traffic"
        description="Every request through your proxy hosts: filter it, then drill into a backend, host or client."
        actions={
          <>
            <Button variant="outline" onClick={purge} className="text-red-600 hover:text-red-600 dark:text-red-400">
              <Trash2 className="h-4 w-4" />
              Purge all
            </Button>
            <Button variant="outline" onClick={refresh}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </>
        }
      />

      <div className="flex w-full gap-1 overflow-x-auto rounded-lg bg-muted p-1 sm:w-fit">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => go({ tab: t.value, drill: null }, true)}
            className={cn(
              'whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium',
              tab === t.value && !drill ? 'bg-background shadow-sm' : 'text-muted-foreground hover:bg-background/50'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <TrafficFiltersBar
        filters={filters}
        onChange={setFilters}
        locked={{
          backend: drill?.kind === 'backend',
          host: drill?.kind === 'host',
          clientIp: drill?.kind === 'client',
        }}
      />

      {drill ? (
        <EntityView
          drill={drill}
          filters={filters}
          hostName={hostName}
          onBack={() => go({ drill: null }, true)}
          onFilter={patchFilters}
          onDrill={openDrill}
        />
      ) : tab === 'backends' ? (
        <BackendsView filters={filters} onDrill={openDrill} />
      ) : tab === 'hosts' ? (
        <RankedView filters={filters} kind="host" onDrill={openDrill} />
      ) : tab === 'clients' ? (
        <RankedView filters={filters} kind="client" onDrill={openDrill} />
      ) : (
        <TrafficOverviewView filters={filters} onFilter={patchFilters} onDrill={openDrill} />
      )}
    </div>
  )
}
