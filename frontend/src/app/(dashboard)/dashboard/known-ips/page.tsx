'use client'

import { useState } from 'react'
import { Tag, Plus, Pencil, Trash2, Search, BarChart3, ShieldCheck } from 'lucide-react'

import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { useConfirm } from '@/components/confirm-dialog'
import { useDebounced } from '@/lib/use-debounced'
import {
  useKnownIps,
  useCreateKnownIp,
  useUpdateKnownIp,
  useDeleteKnownIp,
  type KnownIp,
} from '@/lib/queries/known-ips'
import { IpReport } from '@/components/ip-report'

const CATEGORIES = ['office', 'staff', 'vendor', 'monitoring', 'cdn', 'scanner', 'other']

const EMPTY = { ip_address: '', label: '', category: '', notes: '', trusted: false }

export default function KnownIpsPage() {
  const confirm = useConfirm()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [showDialog, setShowDialog] = useState(false)
  const [editing, setEditing] = useState<KnownIp | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [reportIp, setReportIp] = useState<string | null>(null)
  const [lookupIp, setLookupIp] = useState('')

  const { data, isPending } = useKnownIps({ search: debouncedSearch || undefined, limit: 200 })
  const create = useCreateKnownIp()
  const update = useUpdateKnownIp()
  const remove = useDeleteKnownIp()

  const items = data?.items ?? []

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY)
    setShowDialog(true)
  }

  const openEdit = (k: KnownIp) => {
    setEditing(k)
    setForm({
      ip_address: k.ip_address,
      label: k.label,
      category: k.category ?? '',
      notes: k.notes ?? '',
      trusted: k.trusted,
    })
    setShowDialog(true)
  }

  const save = async () => {
    const payload = {
      label: form.label.trim(),
      category: form.category || null,
      notes: form.notes.trim() || null,
      trusted: form.trusted,
    }
    if (editing) {
      await update.mutateAsync({ id: editing.id, ...payload })
    } else {
      await create.mutateAsync({ ip_address: form.ip_address.trim(), ...payload })
    }
    setShowDialog(false)
  }

  const handleDelete = async (k: KnownIp) => {
    if (!(await confirm({
      description: `Remove the label "${k.label}" from ${k.ip_address}?`,
      variant: 'destructive',
    }))) return
    await remove.mutateAsync(k.id)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Known IPs</h1>
          <p className="text-muted-foreground">
            Put a name to the addresses you recognise. Labels appear wherever that
            IP shows up across the app.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          Label an IP
        </button>
      </div>

      {/* Look up any address, labelled or not */}
      <div className="rounded-xl border border-border bg-card p-4">
        <label className="block text-sm font-medium mb-2">Look up any IP</label>
        <div className="flex flex-wrap gap-2">
          <input
            value={lookupIp}
            onChange={(e) => setLookupIp(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && lookupIp.trim()) setReportIp(lookupIp.trim()) }}
            placeholder="e.g. 94.154.43.158"
            className="flex-1 min-w-[200px] px-3 py-2 rounded-lg border border-input bg-background text-sm font-mono"
          />
          <button
            onClick={() => lookupIp.trim() && setReportIp(lookupIp.trim())}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-input hover:bg-muted text-sm"
          >
            <Search className="h-4 w-4" />
            View traffic
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Works for any address — it does not need to be labelled first.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search labels, addresses or notes..."
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-input bg-background text-sm"
          />
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Label</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">IP Address</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground hidden md:table-cell">Category</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground hidden lg:table-cell">Notes</th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isPending ? (
                <tr><td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">Loading…</td></tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                    <Tag className="h-8 w-8 mx-auto mb-3 opacity-30" />
                    No labelled addresses yet.
                  </td>
                </tr>
              ) : (
                items.map((k) => (
                  <tr key={k.id} className="hover:bg-muted/50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{k.label}</span>
                        {k.trusted && (
                          <ShieldCheck className="h-4 w-4 text-green-500" aria-label="Recognised as benign" />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-sm" data-private="ip">{k.ip_address}</td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      {k.category && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          {k.category}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground hidden lg:table-cell max-w-[280px] truncate" title={k.notes ?? ''}>
                      {k.notes}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setReportIp(k.ip_address)} title="View traffic"
                          className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground hover:text-foreground">
                          <BarChart3 className="h-4 w-4" />
                        </button>
                        <button onClick={() => openEdit(k)} title="Edit"
                          className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground hover:text-foreground">
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDelete(k)} title="Remove label"
                          className="rounded-lg p-1.5 hover:bg-muted text-muted-foreground hover:text-red-500">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal open={showDialog} onOpenChange={setShowDialog} size="lg">
        <ModalHeader>
          <ModalTitle>{editing ? 'Edit label' : 'Label an IP'}</ModalTitle>
        </ModalHeader>
        <ModalBody className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">IP Address</label>
            <input
              value={form.ip_address}
              onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              disabled={Boolean(editing)}
              placeholder="203.0.113.10"
              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm font-mono disabled:opacity-60"
            />
            {editing && (
              <p className="text-xs text-muted-foreground mt-1">
                The address is the identity of the record — delete and re-add to change it.
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Label</label>
            <input
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              placeholder="Head office"
              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Category</label>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
            >
              <option value="">None</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Notes</label>
            <Textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={3}
              className="w-full rounded-lg bg-background"
              placeholder="Anything worth remembering about this address"
            />
          </div>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={form.trusted}
              onChange={(e) => setForm({ ...form, trusted: e.target.checked })}
              className="h-4 w-4 rounded border-input mt-0.5"
            />
            <span className="text-sm">
              Recognised as benign
              <span className="block text-xs text-muted-foreground">
                Display only. This does not exempt the address from the WAF or rate
                limits — that is the separate trusted-IP list under Access Control.
              </span>
            </span>
          </label>
        </ModalBody>
        <ModalFooter>
          <button onClick={() => setShowDialog(false)}
            className="px-4 py-2 rounded-lg border border-input hover:bg-muted text-sm">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!form.label.trim() || (!editing && !form.ip_address.trim())}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-sm disabled:opacity-50"
          >
            {editing ? 'Save' : 'Add'}
          </button>
        </ModalFooter>
      </Modal>

      <IpReport ip={reportIp} onClose={() => setReportIp(null)} />
    </div>
  )
}
