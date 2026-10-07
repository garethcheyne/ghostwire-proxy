'use client'
/*
 * How to connect an AI agent (Claude Code and friends) to this proxy over MCP.
 *
 * The endpoint and every snippet are built from the URL the browser is on, not from a configured
 * value: someone reading this has reached the instance, so that address is known to work.
 */
import { useState, useSyncExternalStore } from 'react'
import Link from 'next/link'
import { Bot, ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { CopyButton, CreateKey, NewKeyAlert, PRESETS } from './create-api-key'

function useOrigin() {
  return useSyncExternalStore(
    () => () => {},
    () => window.location.origin,
    () => '',
  )
}

const TOOLS: [string, string, string][] = [
  ['ghostwire_proxy_list_proxy_hosts', 'Every host: domains, backend, SSL, access control, health', 'read'],
  ['ghostwire_proxy_get_proxy_host', 'One host in full, by ID or domain', 'read'],
  ['ghostwire_proxy_get_proxy_host_config', 'The nginx config nginx is running for a host', 'read'],
  ['ghostwire_proxy_preview_config', 'Render a proposed change and diff it, saving nothing', 'read'],
  ['ghostwire_proxy_list_certificates', 'Certificates with status and expiry', 'read'],
  ['ghostwire_proxy_list_access_lists', 'IP access lists', 'read'],
  ['ghostwire_proxy_list_auth_walls', 'Auth walls (login pages)', 'read'],
  ['ghostwire_proxy_list_upstreams', "A host's balancing method and upstream servers", 'read'],
  ['ghostwire_proxy_get_health_summary', 'Health of every host and upstream server', 'read'],
  ['ghostwire_proxy_get_traffic_summary', 'Requests, status codes, top hosts and paths', 'read'],
  ['ghostwire_proxy_get_recent_changes', 'The audit log, including changes made with keys', 'read'],
  ['ghostwire_proxy_create_proxy_host', 'Create a host (dry_run to preview)', 'write:proxy-hosts'],
  ['ghostwire_proxy_update_proxy_host', 'Change SSL, websockets, access list, auth wall, … (dry_run)', 'write:proxy-hosts'],
  ['ghostwire_proxy_set_proxy_host_enabled', 'Enable or disable a host (dry_run)', 'write:proxy-hosts'],
  ['ghostwire_proxy_set_load_balancing', 'Balancing method, or replace the upstream list (dry_run)', 'write:proxy-hosts'],
  ['ghostwire_proxy_add_upstream', 'Add an upstream server (dry_run)', 'write:upstreams'],
  ['ghostwire_proxy_update_upstream', 'Weight, backup, down, max_conns, … (dry_run)', 'write:upstreams'],
  ['ghostwire_proxy_remove_upstream', 'Remove an upstream server (dry_run)', 'write:upstreams'],
  ['ghostwire_proxy_request_certificate', "Request a Let's Encrypt certificate", 'write:certificates'],
  ['ghostwire_proxy_test_nginx_config', 'Run nginx -t', 'write:nginx'],
  ['ghostwire_proxy_reload_nginx', 'Regenerate every config and reload (needs confirm)', 'write:nginx'],
]

function Step({ n, title, description, children }: { n: number; title: string; description?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-6">
      <div>
        <h2 className="text-lg font-semibold">{n}. {title}</h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  )
}

function Snippet({ value, rows, label }: { value: string; rows: number; label: string }) {
  return (
    <div className="space-y-2">
      <Textarea value={value} readOnly rows={rows} className="resize-none font-mono text-xs" aria-label={label} />
      <div className="flex justify-end">
        <CopyButton value={value} label="Copy" />
      </div>
    </div>
  )
}

export function McpSettings() {
  const origin = useOrigin()
  const [newKey, setNewKey] = useState<string | null>(null)
  const endpoint = `${origin}/api/mcp`
  const key = newKey ?? 'gwp_your_api_key'

  const claudeCode = `claude mcp add --transport http ghostwire-proxy ${endpoint} \\
  --header "Authorization: Bearer ${key}"`

  const jsonConfig = JSON.stringify(
    {
      mcpServers: {
        'ghostwire-proxy': {
          type: 'http',
          url: endpoint,
          headers: { Authorization: `Bearer ${key}` },
        },
      },
    },
    null,
    2,
  )

  const configure = PRESETS.find(p => p.label === 'Configure hosts')?.scopes ?? ['read']

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Bot}
        title="AI agents (MCP)"
        description="Let an AI assistant such as Claude Code read and configure this proxy through the Model Context Protocol."
      />

      {newKey && <NewKeyAlert value={newKey} />}

      <Step
        n={1}
        title="Create an API key for the agent"
        description={
          <>
            Give the agent its own key so you can revoke it without affecting anything else. Manage
            keys under{' '}
            <Link href="/dashboard/settings/api-keys" className="text-primary underline-offset-4 hover:underline">API keys</Link>.
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <CreateKey onCreated={setNewKey} defaultName="Claude Code" defaultScopes={configure} />
          <p className="text-sm text-muted-foreground">
            {newKey
              ? 'The snippets below now carry your new key. Copy one before you leave — it is not shown again.'
              : <>The snippets show <code className="font-mono text-xs">gwp_your_api_key</code> until you create one.</>}
          </p>
        </div>
        <div className="space-y-1 text-sm text-muted-foreground">
          <p>Scopes the agent needs:</p>
          <ul className="list-disc space-y-0.5 pl-5">
            <li><code className="font-mono text-xs">read</code> — look at hosts, certificates, health, traffic and the audit log, and preview changes (every key has it).</li>
            <li><code className="font-mono text-xs">write:proxy-hosts</code> — create and change hosts, enable/disable, load-balancing method.</li>
            <li><code className="font-mono text-xs">write:upstreams</code> — add, change and remove upstream servers.</li>
            <li><code className="font-mono text-xs">write:certificates</code> — request certificates; <code className="font-mono text-xs">write:access</code> — access lists and auth walls; <code className="font-mono text-xs">write:nginx</code> — nginx -t and reload.</li>
          </ul>
        </div>
      </Step>

      <Step
        n={2}
        title="Connect your editor"
        description={<>The endpoint is <code className="font-mono text-xs">{endpoint}</code> (Streamable HTTP, stateless).</>}
      >
        <div className="space-y-2">
          <p className="text-sm font-medium">Claude Code</p>
          <p className="text-sm text-muted-foreground">
            Run once. Add <code className="font-mono text-xs">--scope user</code> to make it available in every project.
          </p>
          <Snippet value={claudeCode} rows={2} label="Claude Code command" />
        </div>
        <Separator />
        <div className="space-y-2">
          <p className="text-sm font-medium">Claude Desktop, Cursor, VS Code</p>
          <p className="text-sm text-muted-foreground">Add this to the client&apos;s MCP configuration file.</p>
          <Snippet value={jsonConfig} rows={11} label="MCP JSON configuration" />
        </div>
      </Step>

      <Step
        n={3}
        title="Ask it for something"
        description={'For example: "put app.example.com in front of 10.0.0.5:3000 with websockets and the office access list — show me the diff first".'}
      >
        <div className="space-y-2">
          {TOOLS.map(([name, what, scope]) => (
            <div key={name} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <code className="font-mono text-xs text-foreground">{name}</code>
              <span className="text-sm text-muted-foreground">{what}</span>
              <span className="font-mono text-[11px] text-muted-foreground">({scope})</span>
            </div>
          ))}
        </div>
        <Separator />
        <p className="text-sm text-muted-foreground">
          Every change goes through the same nginx -t check as the admin UI and is not saved if it
          fails. Deleting hosts, certificates or users is deliberately not exposed.
        </p>
      </Step>

      <Alert>
        <ShieldAlert className="h-4 w-4" />
        <AlertTitle>A key is as powerful as its scopes</AlertTitle>
        <AlertDescription className="text-muted-foreground">
          An agent holding a write key can change live routing. Give keys an expiry, keep the scopes
          to what the job needs, and revoke them under API keys when you are done. Every change made
          with a key is in the audit log under the key&apos;s name.
        </AlertDescription>
      </Alert>
    </div>
  )
}
