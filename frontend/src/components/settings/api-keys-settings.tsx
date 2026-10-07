'use client'

import { useCallback, useState } from 'react'
import Link from 'next/link'
import { format, formatDistanceToNowStrict } from 'date-fns'
import { KeyRound, Loader2, MoreHorizontal, Ban } from 'lucide-react'
import api from '@/lib/api'
import { usePageData } from '@/lib/use-page-data'
import { toastError, toastSuccess } from '@/lib/toast'
import { useConfirm } from '@/components/confirm-dialog'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { CreateKey, NewKeyAlert, type ApiKeyRow } from './create-api-key'

const STATUS_STYLE: Record<ApiKeyRow['status'], string> = {
  active: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/30',
  expired: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
  revoked: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30',
}

const when = (iso: string | null, empty: string) =>
  iso ? formatDistanceToNowStrict(new Date(iso), { addSuffix: true }) : empty

export function ApiKeysSettings() {
  const confirm = useConfirm()
  const [keys, setKeys] = useState<ApiKeyRow[] | null>(null)
  const [newKey, setNewKey] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/api-keys/')
      setKeys(data)
    } catch {
      setKeys([])
    }
  }, [])

  usePageData(() => { load() })

  async function revoke(key: ApiKeyRow) {
    const ok = await confirm({
      title: `Revoke "${key.name}"?`,
      description: 'Anything using this key, such as an AI agent or script, stops working straight away. This cannot be undone.',
      confirmLabel: 'Revoke',
      variant: 'destructive',
    })
    if (!ok) return
    try {
      await api.delete(`/api/api-keys/${key.id}`)
      toastSuccess('Key revoked')
      load()
    } catch {
      toastError('Could not revoke the key')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={KeyRound}
        title="API keys"
        description={
          <>
            Scoped keys for scripts and AI agents, sent as <code className="font-mono text-xs">Authorization: Bearer gwp_…</code>.
            To connect Claude Code, see{' '}
            <Link href="/dashboard/settings/mcp" className="text-primary underline-offset-4 hover:underline">
              AI agents (MCP)
            </Link>
            .
          </>
        }
        actions={<CreateKey onCreated={key => { setNewKey(key); load() }} />}
      />

      {newKey && <NewKeyAlert value={newKey} />}

      <div className="rounded-xl border border-border bg-card">
        {keys === null ? (
          <div className="flex items-center justify-center p-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : keys.length === 0 ? (
          <div className="flex flex-col items-start gap-2 p-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
              <KeyRound className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="font-medium">No API keys</p>
            <p className="text-sm text-muted-foreground">
              Create one to let a script or an AI agent configure this proxy. Creating a key asks for
              your two-factor code.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead className="hidden lg:table-cell">Scopes</TableHead>
                <TableHead className="hidden md:table-cell">Created</TableHead>
                <TableHead className="hidden md:table-cell">Last used</TableHead>
                <TableHead className="hidden sm:table-cell">Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map(key => (
                <TableRow key={key.id} className={key.status !== 'active' ? 'opacity-60' : undefined}>
                  <TableCell className="font-medium">
                    {key.name}
                    {key.created_by_email && (
                      <span className="block text-xs font-normal text-muted-foreground">{key.created_by_email}</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{key.display}</TableCell>
                  <TableCell className="hidden lg:table-cell">
                    <div className="flex max-w-xs flex-wrap gap-1">
                      {key.scopes.map(s => (
                        <Badge key={s} variant="outline" className="font-mono text-[10px] font-normal">{s}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {format(new Date(key.created_at), 'd MMM yyyy')}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {when(key.last_used_at, 'Never')}
                    {key.last_used_ip && <span className="block font-mono text-xs">{key.last_used_ip}</span>}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">
                    {key.expires_at ? format(new Date(key.expires_at), 'd MMM yyyy') : 'Never'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={STATUS_STYLE[key.status]}>{key.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {key.status !== 'revoked' && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label="Key actions">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            className="text-red-500 focus:text-red-500"
                            onClick={() => revoke(key)}
                          >
                            <Ban className="mr-2 h-4 w-4" />
                            Revoke
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
