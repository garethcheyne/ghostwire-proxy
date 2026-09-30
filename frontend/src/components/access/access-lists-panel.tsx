'use client'

import { useState } from 'react'
import { Modal, ModalBody } from '@/components/ui/modal'
import { usePageData } from '@/lib/use-page-data'
import { toastSuccess, toastError } from '@/lib/toast'
import {
  Lock,
  Plus,
  MoreHorizontal,
  Trash2,
  Pencil,
  ChevronDown,
  ChevronRight,
  Loader2,
  ShieldCheck,
  ShieldX,
  CheckCircle,
} from 'lucide-react'
import api from '@/lib/api'
import { useConfirm } from '@/components/confirm-dialog'
import type { AccessList, AccessListBlockedBehavior, AccessListEntry } from '@/types'

/** What a blocked visitor gets - the Default Site choices, plus nginx's plain 403. */
const BLOCKED_OPTIONS: Array<{ value: AccessListBlockedBehavior; label: string; desc: string }> = [
  { value: '403', label: '403 Forbidden', desc: 'Return a 403 error page' },
  { value: 'congratulations', label: 'Ghostwire Welcome', desc: 'Show the Ghostwire Proxy landing page' },
  { value: 'redirect', label: 'Redirect', desc: 'Redirect to a custom URL' },
  { value: '404', label: '404 Not Found', desc: 'Return a 404 error page' },
  { value: '444', label: 'Drop Connection', desc: 'Silently close the connection' },
]
import { UsedBy, deleteWarning } from '@/components/access/used-by'
import { PageHeader } from '@/components/layout/page-header'
import { Key as HeaderIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/** IP access lists and editor. `embedded` drops the page title (the host page has its own) but keeps the Add button. */
export function AccessListsPanel({ embedded = false }: { embedded?: boolean }) {
  const [accessLists, setAccessLists] = useState<AccessList[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingList, setEditingList] = useState<AccessList | null>(null)
  const [expandedLists, setExpandedLists] = useState<Set<string>>(new Set())
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Form state
  const [formName, setFormName] = useState('')
  const [formMode, setFormMode] = useState<'whitelist' | 'blacklist'>('whitelist')
  const [formEntries, setFormEntries] = useState<Array<{ ip_or_cidr: string; action: 'allow' | 'deny' }>>([])
  const [newEntryIp, setNewEntryIp] = useState('')
  const [newEntryAction, setNewEntryAction] = useState<'allow' | 'deny'>('allow')
  const [formBlocked, setFormBlocked] = useState<AccessListBlockedBehavior>('403')
  const [formRedirectUrl, setFormRedirectUrl] = useState('')
  const confirm = useConfirm()

  usePageData(() => { fetchAccessLists() })

  const fetchAccessLists = async () => {
    try {
      const response = await api.get('/api/access-lists')
      setAccessLists(response.data)
    } catch (error) {
      console.error('Failed to fetch access lists:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setFormName('')
    setFormMode('whitelist')
    setFormEntries([])
    setNewEntryIp('')
    setNewEntryAction('allow')
    setFormBlocked('403')
    setFormRedirectUrl('')
    setError('')
  }

  const handleCreate = () => {
    resetForm()
    setEditingList(null)
    setShowCreateDialog(true)
  }

  const handleEdit = (list: AccessList) => {
    setFormName(list.name)
    setFormMode(list.mode)
    setFormBlocked(list.blocked_behavior ?? '403')
    setFormRedirectUrl(list.blocked_redirect_url ?? '')
    setFormEntries(
      list.entries.map((e) => ({
        ip_or_cidr: e.ip_or_cidr,
        action: e.action,
      }))
    )
    setEditingList(list)
    setShowCreateDialog(true)
  }

  const toggleExpanded = (listId: string) => {
    const newExpanded = new Set(expandedLists)
    if (newExpanded.has(listId)) {
      newExpanded.delete(listId)
    } else {
      newExpanded.add(listId)
    }
    setExpandedLists(newExpanded)
  }

  const handleAddEntry = () => {
    if (newEntryIp.trim()) {
      setFormEntries([
        ...formEntries,
        { ip_or_cidr: newEntryIp.trim(), action: newEntryAction },
      ])
      setNewEntryIp('')
    }
  }

  const handleRemoveEntry = (index: number) => {
    setFormEntries(formEntries.filter((_, i) => i !== index))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const data = {
        name: formName,
        mode: formMode,
        blocked_behavior: formBlocked,
        blocked_redirect_url: formBlocked === 'redirect' ? formRedirectUrl.trim() : null,
        entries: formEntries,
      }

      if (editingList) {
        await api.put(`/api/access-lists/${editingList.id}`, data)
      } else {
        await api.post('/api/access-lists', data)
      }

      setShowCreateDialog(false)
      fetchAccessLists()
      toastSuccess(editingList ? 'Access list updated' : 'Access list created')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save access list')
      toastError('Failed to save access list')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (list: AccessList) => {
    if (!(await confirm({ description: deleteWarning(list.name, list.proxy_hosts, 'IP access list'), variant: 'destructive' }))) return

    try {
      await api.delete(`/api/access-lists/${list.id}`)
      fetchAccessLists()
      toastSuccess('Access list deleted')
    } catch (error) {
      console.error('Failed to delete access list:', error)
      toastError('Failed to delete access list')
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading access lists...</div>
      </div>
    )
  }

  const addButton = (
    <button
      onClick={handleCreate}
      className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
    >
      <Plus className="h-4 w-4" />
      Add Access List
    </button>
  )

  return (
    <div className="space-y-6">
      {embedded ? (
        <div className="flex justify-end">{addButton}</div>
      ) : (
        <PageHeader
          icon={HeaderIcon}
          title="Access Lists"
          description="Control access to your proxy hosts with IP whitelists and blacklists"
          actions={addButton}
        />
      )}

      {/* Access Lists */}
      <div className="space-y-4">
        {accessLists.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Lock className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No access lists configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click "Add Access List" to create one
            </p>
          </div>
        ) : (
          accessLists.map((list) => (
            <div key={list.id} className="rounded-xl border border-border bg-card">
              <div
                className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50"
                onClick={() => toggleExpanded(list.id)}
              >
                <div className="flex items-center gap-3">
                  <button className="p-1">
                    {expandedLists.has(list.id) ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </button>
                  {list.mode === 'whitelist' ? (
                    <ShieldCheck className="h-5 w-5 text-green-500" />
                  ) : (
                    <ShieldX className="h-5 w-5 text-red-500" />
                  )}
                  <div>
                    <h3 className="font-semibold">{list.name}</h3>
                    <p className="text-sm text-muted-foreground">
                      {list.entries.length} {list.entries.length === 1 ? 'entry' : 'entries'} •{' '}
                      <span
                        className={
                          list.mode === 'whitelist' ? 'text-green-500' : 'text-red-500'
                        }
                      >
                        {list.mode === 'whitelist' ? 'Whitelist' : 'Blacklist'}
                      </span>
                      {list.blocked_behavior && list.blocked_behavior !== '403' && (
                        <>
                          {' '}• Blocked:{' '}
                          {list.blocked_behavior === 'redirect'
                            ? `redirect to ${list.blocked_redirect_url}`
                            : BLOCKED_OPTIONS.find((o) => o.value === list.blocked_behavior)?.label}
                        </>
                      )}
                    </p>
                    <UsedBy hosts={list.proxy_hosts} />
                  </div>
                </div>

                <div onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="rounded-lg p-2 hover:bg-muted" aria-label="Actions">
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      <DropdownMenuItem
                        onSelect={() => handleEdit(list)}
                        className="gap-2"
                      >
                        <Pencil className="h-4 w-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onSelect={() => handleDelete(list)}
                        className="gap-2 text-red-500 focus:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              {expandedLists.has(list.id) && (
                <div className="border-t border-border p-4">
                  {list.entries.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No entries in this access list
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {list.entries.map((entry) => (
                        <div
                          key={entry.id}
                          className="flex items-center justify-between rounded-lg border border-border p-3"
                        >
                          <code className="text-sm font-mono">{entry.ip_or_cidr}</code>
                          <span
                            className={`text-xs px-2 py-1 rounded-full ${
                              entry.action === 'allow'
                                ? 'bg-green-500/10 text-green-500'
                                : 'bg-red-500/10 text-red-500'
                            }`}
                          >
                            {entry.action}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Modal
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        size="lg"
        srTitle="Access lists — Create"
      >
        <ModalBody className="p-0">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">
                {editingList ? 'Edit Access List' : 'Add Access List'}
              </h2>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                  placeholder="My Access List"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Mode</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="mode"
                      value="whitelist"
                      checked={formMode === 'whitelist'}
                      onChange={() => setFormMode('whitelist')}
                      className="h-4 w-4"
                    />
                    <span className="text-sm">Whitelist (allow only listed)</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="mode"
                      value="blacklist"
                      checked={formMode === 'blacklist'}
                      onChange={() => setFormMode('blacklist')}
                      className="h-4 w-4"
                    />
                    <span className="text-sm">Blacklist (block listed)</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">When someone is blocked</label>
                <p className="text-xs text-muted-foreground mb-2">
                  What a visitor this list blocks gets instead of the site.
                </p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {BLOCKED_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`relative flex flex-col rounded-lg border p-3 cursor-pointer transition-colors ${
                        formBlocked === opt.value
                          ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                          : 'border-border hover:border-muted-foreground/30'
                      }`}
                    >
                      <input
                        type="radio"
                        name="blockedBehavior"
                        value={opt.value}
                        checked={formBlocked === opt.value}
                        onChange={() => setFormBlocked(opt.value)}
                        className="sr-only"
                      />
                      {formBlocked === opt.value && (
                        <span className="absolute top-2 right-2 flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
                          <CheckCircle className="h-3 w-3" />
                          Active
                        </span>
                      )}
                      <span className="font-medium text-sm">{opt.label}</span>
                      <span className="text-xs text-muted-foreground mt-1">{opt.desc}</span>
                    </label>
                  ))}
                </div>

                {formBlocked === 'redirect' && (
                  <div className="mt-3">
                    <label className="block text-sm font-medium mb-2">Redirect URL</label>
                    <input
                      type="url"
                      value={formRedirectUrl}
                      onChange={(e) => setFormRedirectUrl(e.target.value)}
                      placeholder="https://example.com"
                      className="w-full max-w-md px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                      required
                    />
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Entries</label>
                <div className="flex flex-wrap gap-2 mb-3">
                  <input
                    type="text"
                    value={newEntryIp}
                    onChange={(e) => setNewEntryIp(e.target.value)}
                    className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                    placeholder="192.168.1.0/24 or single IP"
                  />
                  <select
                    value={newEntryAction}
                    onChange={(e) => setNewEntryAction(e.target.value as 'allow' | 'deny')}
                    className="px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                  >
                    <option value="allow">Allow</option>
                    <option value="deny">Deny</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleAddEntry}
                    className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                  >
                    Add
                  </button>
                </div>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {formEntries.map((entry, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between rounded-lg border border-border p-2"
                    >
                      <div className="flex items-center gap-2">
                        <code className="text-sm">{entry.ip_or_cidr}</code>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            entry.action === 'allow'
                              ? 'bg-green-500/10 text-green-500'
                              : 'bg-red-500/10 text-red-500'
                          }`}
                        >
                          {entry.action}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveEntry(index)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowCreateDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editingList ? 'Save Changes' : 'Create'}
                </button>
              </div>
            </form>
        </ModalBody>
      </Modal>

    </div>
  )
}
