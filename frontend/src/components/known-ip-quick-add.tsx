'use client'

import { useState, useEffect } from 'react'

import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import {
  useCreateKnownIp,
  useUpdateKnownIp,
  useKnownIpGroups,
  type KnownIpLabel,
} from '@/lib/queries/known-ips'

const CATEGORIES = ['office', 'staff', 'vendor', 'monitoring', 'cdn', 'scanner', 'other']

interface Props {
  ip: string
  /** Present when the address already has a label, so this edits instead of creating. */
  existing?: KnownIpLabel | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Label an address without leaving the page you spotted it on.
 *
 * Reached from the IP hover card, so it works anywhere an IP is rendered —
 * analytics, traffic logs, threats, honeypot — rather than only from the Known
 * IPs page. Noticing an address and naming it are the same moment; making that
 * a separate trip to another screen is how addresses stay anonymous.
 */
export function KnownIpQuickAdd({ ip, existing, open, onOpenChange }: Props) {
  const { data: groups } = useKnownIpGroups()
  const create = useCreateKnownIp()
  const update = useUpdateKnownIp()

  const [form, setForm] = useState({ label: '', category: '', group_name: '', notes: '', trusted: false })

  // Re-seed each time it opens: the same component instance is reused for
  // whichever address the user hovered last.
  useEffect(() => {
    if (!open) return
    setForm({
      label: existing?.label ?? '',
      category: existing?.category ?? '',
      group_name: existing?.group_name ?? '',
      notes: '',
      trusted: existing?.trusted ?? false,
    })
  }, [open, existing])

  const save = async () => {
    const payload = {
      label: form.label.trim(),
      category: form.category || null,
      group_name: form.group_name.trim() || null,
      notes: form.notes.trim() || null,
      trusted: form.trusted,
    }
    if (existing) {
      await update.mutateAsync({ id: existing.id, ...payload })
    } else {
      await create.mutateAsync({ ip_address: ip, ...payload })
    }
    onOpenChange(false)
  }

  const busy = create.isPending || update.isPending

  return (
    <Modal open={open} onOpenChange={onOpenChange} size="md">
      <ModalHeader>
        <ModalTitle>{existing ? 'Edit label' : 'Label this IP'}</ModalTitle>
      </ModalHeader>
      <ModalBody className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">IP Address</label>
          <code className="block px-3 py-2 rounded-lg border border-input bg-muted text-sm font-mono" data-private="ip">
            {ip}
          </code>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Label</label>
          <input
            autoFocus
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter' && form.label.trim()) void save() }}
            placeholder="Head office"
            className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Group</label>
            <input
              value={form.group_name}
              onChange={(e) => setForm({ ...form, group_name: e.target.value })}
              list="quick-add-groups"
              placeholder="e.g. Microsoft Dataverse"
              className="w-full px-3 py-2 rounded-lg border border-input bg-background text-sm"
            />
            <datalist id="quick-add-groups">
              {groups?.map((g) => <option key={g.group_name} value={g.group_name} />)}
            </datalist>
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
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Notes</label>
          <Textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={2}
            className="w-full rounded-lg bg-background"
            placeholder="Optional"
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
              Display only — does not exempt the address from the WAF or rate limits.
            </span>
          </span>
        </label>
      </ModalBody>
      <ModalFooter>
        <button onClick={() => onOpenChange(false)}
          className="px-4 py-2 rounded-lg border border-input hover:bg-muted text-sm">
          Cancel
        </button>
        <button
          onClick={save}
          disabled={!form.label.trim() || busy}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-sm disabled:opacity-50"
        >
          {existing ? 'Save' : 'Add'}
        </button>
      </ModalFooter>
    </Modal>
  )
}

export default KnownIpQuickAdd
