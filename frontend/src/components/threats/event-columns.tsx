'use client'

import { ColumnDef } from '@tanstack/react-table'
import { ArrowUpDown, Ban, Globe, Trash2, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { IpAddress } from '@/components/ip-address'

export interface ThreatEvent {
  id: string
  proxy_host_id: string | null
  client_ip: string
  rule_id: string | null
  rule_name: string | null
  category: string
  severity: string
  action_taken: string
  request_method: string | null
  request_uri: string | null
  matched_payload: string | null
  user_agent: string | null
  host: string | null
  timestamp: string
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

const categoryColors: Record<string, string> = {
  sqli: 'bg-red-500/10 text-red-500',
  xss: 'bg-orange-500/10 text-orange-500',
  path_traversal: 'bg-yellow-500/10 text-yellow-500',
  rce: 'bg-purple-500/10 text-purple-500',
  scanner: 'bg-blue-500/10 text-blue-500',
  sensitive_data: 'bg-cyan-500/10 text-cyan-400',
  injection: 'bg-red-500/10 text-red-400',
  recon: 'bg-slate-500/10 text-slate-400',
  dos: 'bg-amber-500/10 text-amber-500',
  blocked_ip: 'bg-red-500/10 text-red-500',
}

export function createEventColumns(actions: {
  onBlock: (ip: string) => void
  onDelete: (id: string) => void
  onInvestigate?: (ip: string) => void
}): ColumnDef<ThreatEvent>[] {
  return [
    {
      accessorKey: 'timestamp',
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-8 -ml-3 text-xs"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Time <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const d = row.getValue('timestamp') as string
        try {
          const date = new Date(d)
          return (
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}{' '}
              {date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )
        } catch { return <span className="text-xs text-muted-foreground">{d}</span> }
      },
    },
    {
      accessorKey: 'client_ip',
      header: 'IP Address',
      cell: ({ row }) => (
        <IpAddress ip={row.getValue('client_ip')} />
      ),
      filterFn: 'includesString',
    },
    {
      accessorKey: 'host',
      header: 'Host',
      cell: ({ row }) => {
        const host = row.getValue('host') as string | null
        if (!host) return <span className="text-xs text-muted-foreground">—</span>
        return (
          <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 max-w-40 truncate">
            <Globe className="h-3 w-3 shrink-0" />
            <span className="truncate">{host}</span>
          </span>
        )
      },
    },
    {
      accessorKey: 'category',
      header: 'Category',
      cell: ({ row }) => {
        const cat = row.getValue('category') as string
        return (
          <span className={`text-xs px-2 py-0.5 rounded-full capitalize whitespace-nowrap ${categoryColors[cat] || 'bg-muted text-muted-foreground'}`}>
            {cat.replace(/_/g, ' ')}
          </span>
        )
      },
      filterFn: 'equals',
    },
    {
      accessorKey: 'severity',
      header: ({ column }) => (
        <Button variant="ghost" size="sm" className="h-8 -ml-3 text-xs"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
          Severity <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => {
        const sev = row.getValue('severity') as string
        return (
          <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${severityColors[sev] || severityColors.medium}`}>
            {sev}
          </span>
        )
      },
      filterFn: 'equals',
      sortingFn: (rowA, rowB) => {
        const order = { critical: 4, high: 3, medium: 2, low: 1 }
        const a = order[rowA.getValue('severity') as keyof typeof order] || 0
        const b = order[rowB.getValue('severity') as keyof typeof order] || 0
        return a - b
      },
    },
    {
      accessorKey: 'action_taken',
      header: 'Action',
      cell: ({ row }) => {
        const action = row.getValue('action_taken') as string
        return (
          <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${
            action === 'blocked' ? 'bg-red-500/10 text-red-500' : 'bg-slate-500/10 text-slate-400'
          }`}>
            {action}
          </span>
        )
      },
    },
    {
      accessorKey: 'rule_name',
      header: 'Rule',
      cell: ({ row }) => {
        const rule = row.getValue('rule_name') as string | null
        if (!rule) return <span className="text-xs text-muted-foreground">—</span>
        return (
          <span className="text-xs text-muted-foreground max-w-48 truncate block" title={rule}>
            {rule}
          </span>
        )
      },
    },
    {
      accessorKey: 'request_uri',
      header: 'Request',
      cell: ({ row }) => {
        const method = row.original.request_method
        const uri = row.getValue('request_uri') as string | null
        if (!uri) return <span className="text-xs text-muted-foreground">—</span>
        return (
          <code className="text-xs text-muted-foreground max-w-56 truncate block" title={`${method} ${uri}`}>
            <span className="text-foreground/70 font-medium">{method}</span> {uri}
          </code>
        )
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          {actions.onInvestigate && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-blue-500"
              onClick={() => actions.onInvestigate!(row.original.client_ip)}
              title="Investigate IP"
            >
              <Search className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-red-500"
            onClick={() => actions.onBlock(row.original.client_ip)}
            title="Block IP"
          >
            <Ban className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-red-500"
            onClick={() => actions.onDelete(row.original.id)}
            title="Delete event"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
      enableSorting: false,
    },
  ]
}
