'use client'

import { ColumnDef } from '@tanstack/react-table'
import { ArrowUpDown, Ban, Unlock, Trash2, ChevronDown, ChevronUp, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { IpAddress } from '@/components/ip-address'

export interface ThreatActor {
  id: string
  ip_address: string
  total_events: number
  threat_score: number
  first_seen: string
  last_seen: string
  current_status: string
  temp_block_until: string | null
  perm_blocked_at: string | null
  firewall_banned_at: string | null
  country_code: string | null
  country_name: string | null
  tags: string[]
  notes: string | null
}

const statusColors: Record<string, string> = {
  monitored: 'bg-slate-500/10 text-slate-400',
  warned: 'bg-yellow-500/10 text-yellow-500',
  temp_blocked: 'bg-orange-500/10 text-orange-500',
  perm_blocked: 'bg-red-500/10 text-red-500',
  firewall_banned: 'bg-purple-500/10 text-purple-500',
}

function formatDate(d: string): string {
  try {
    return new Date(d).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch { return d }
}

export function createActorColumns(actions: {
  onBlock: (ip: string) => void
  onUnblock: (ip: string) => void
  onDelete: (id: string, ip: string) => void
  onToggleExpand: (ip: string) => void
  onInvestigate?: (ip: string) => void
  expandedIp: string | null
}): ColumnDef<ThreatActor>[] {
  return [
    {
      accessorKey: 'ip_address',
      header: 'IP Address',
      cell: ({ row }) => {
        const actor = row.original
        return (
          <IpAddress ip={actor.ip_address} countryCode={actor.country_code} countryName={actor.country_name} />
        )
      },
      filterFn: 'includesString',
    },
    {
      accessorKey: 'country_name',
      header: 'Country',
      cell: ({ row }) => {
        const name = row.getValue('country_name') as string | null
        return <span className="text-xs text-muted-foreground">{name || '—'}</span>
      },
    },
    {
      accessorKey: 'current_status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('current_status') as string
        return (
          <span className={`text-xs px-2 py-0.5 rounded-full capitalize whitespace-nowrap ${statusColors[status] || statusColors.monitored}`}>
            {status.replace(/_/g, ' ')}
          </span>
        )
      },
      filterFn: 'equals',
    },
    {
      accessorKey: 'threat_score',
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-8 -ml-3 text-xs"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Score <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const score = row.getValue('threat_score') as number
        const color = score >= 100 ? 'text-red-500' : score >= 50 ? 'text-orange-500' : score >= 25 ? 'text-yellow-500' : 'text-muted-foreground'
        return <span className={`text-sm font-semibold tabular-nums ${color}`}>{score}</span>
      },
    },
    {
      accessorKey: 'total_events',
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-8 -ml-3 text-xs"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Events <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const actor = row.original
        const isExpanded = actions.expandedIp === actor.ip_address
        return (
          <button
            onClick={() => actions.onToggleExpand(actor.ip_address)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            <span className="underline underline-offset-2 tabular-nums">{actor.total_events}</span>
          </button>
        )
      },
    },
    {
      accessorKey: 'first_seen',
      header: 'First Seen',
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {formatDate(row.getValue('first_seen'))}
        </span>
      ),
    },
    {
      accessorKey: 'last_seen',
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-8 -ml-3 text-xs"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Last Seen <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {formatDate(row.getValue('last_seen'))}
        </span>
      ),
    },
    {
      accessorKey: 'tags',
      header: 'Tags',
      cell: ({ row }) => {
        const tags = row.getValue('tags') as string[]
        if (!tags || tags.length === 0) return <span className="text-xs text-muted-foreground">—</span>
        return (
          <div className="flex items-center gap-1 flex-wrap">
            {tags.slice(0, 3).map((tag) => (
              <span key={tag} className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                {tag}
              </span>
            ))}
            {tags.length > 3 && (
              <span className="text-xs text-muted-foreground">+{tags.length - 3}</span>
            )}
          </div>
        )
      },
      enableSorting: false,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const actor = row.original
        const isBlocked = actor.current_status === 'perm_blocked' || actor.current_status === 'temp_blocked' || actor.current_status === 'firewall_banned'
        return (
          <div className="flex items-center gap-1">
            {actions.onInvestigate && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-blue-500 hover:text-blue-400 hover:bg-blue-500/10"
                onClick={() => actions.onInvestigate!(actor.ip_address)}
                title="Investigate IP"
              >
                <Search className="h-3.5 w-3.5 mr-1" />
                <span className="hidden sm:inline">Intel</span>
              </Button>
            )}
            {isBlocked ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-green-500 hover:text-green-400 hover:bg-green-500/10"
                onClick={() => actions.onUnblock(actor.ip_address)}
              >
                <Unlock className="h-3.5 w-3.5 mr-1" />
                <span className="hidden sm:inline">Unblock</span>
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-red-500 hover:text-red-400 hover:bg-red-500/10"
                onClick={() => actions.onBlock(actor.ip_address)}
              >
                <Ban className="h-3.5 w-3.5 mr-1" />
                <span className="hidden sm:inline">Block</span>
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-red-500"
              onClick={() => actions.onDelete(actor.id, actor.ip_address)}
              title="Delete actor"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )
      },
      enableSorting: false,
    },
  ]
}
