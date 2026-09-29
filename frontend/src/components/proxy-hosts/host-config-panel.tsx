'use client'

import { useQuery } from '@tanstack/react-query'
import { Check, Copy, Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import api from '@/lib/api'

interface HostConfigFile {
  exists: boolean
  enabled: boolean
  path: string
  content: string | null
  modified_at: string | null
}

/**
 * The host's nginx config file, read-only and byte for byte as it is on disk:
 * the same file nginx loaded at its last reload.
 */
export function HostConfigPanel({ hostId }: { hostId: string }) {
  const [copied, setCopied] = useState(false)
  const query = useQuery({
    queryKey: ['proxy-hosts', hostId, 'config'],
    queryFn: async () => (await api.get<HostConfigFile>(`/api/proxy-hosts/${hostId}/config`)).data,
    staleTime: 0,
    refetchOnMount: 'always',
  })

  const copy = async () => {
    if (!query.data?.content) return
    await navigator.clipboard.writeText(query.data.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (query.isPending) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (query.isError) {
    return <p className="p-6 text-sm text-destructive">Could not load the config file.</p>
  }

  const file = query.data
  // Split on \n only, so any \r or trailing whitespace stays visible as it is in the file
  const lines = file.content?.split('\n') ?? []
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop()

  return (
    <div className="space-y-3 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 text-sm">
          <p className="break-all font-mono text-xs">{file.path}</p>
          <p className="text-muted-foreground">
            {file.exists && file.modified_at
              ? `Written ${new Date(file.modified_at).toLocaleString()}. This is what nginx is running; unsaved changes in this dialog are not in it.`
              : file.enabled
                ? 'No config file on disk for this host.'
                : 'No config file: the host is disabled, so nginx has nothing for it.'}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => query.refetch()}
            className="flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-muted"
          >
            <RefreshCw className={`h-4 w-4 ${query.isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {file.exists && (
            <button
              type="button"
              onClick={copy}
              className="flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-muted"
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
        </div>
      </div>

      {file.exists && (
        <div className="max-h-[60vh] overflow-auto rounded-lg border border-border bg-muted/40">
          <pre className="font-mono text-xs leading-5">
            {lines.map((line, i) => (
              <div key={i} className="flex">
                <span className="sticky left-0 w-12 shrink-0 select-none border-r border-border bg-muted pr-2 text-right text-muted-foreground">
                  {i + 1}
                </span>
                <span className="whitespace-pre pl-3 pr-4">{line}</span>
              </div>
            ))}
          </pre>
        </div>
      )}
    </div>
  )
}
