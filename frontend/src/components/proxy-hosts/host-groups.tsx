'use client'

/**
 * Groups and ordering for the Proxy Hosts list.
 *
 * Layout only: nothing here reaches nginx. The page hands in its hosts and
 * groups, renders each host card itself (via `renderHost`) and saves whatever
 * order comes back through `onLayoutChange`.
 *
 * Desktop: drag a host or group by its grip. Phones (no HTML drag and drop):
 * Move up / Move down / Move to group in the host's ⋯ menu, and the same for
 * groups in the group's menu.
 */

import { useState, type DragEvent, type ReactNode } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  FolderInput,
  GripVertical,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'
import type { ProxyHost, ProxyHostGroup } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Modal, ModalBody, ModalFooter, ModalHeader, ModalTitle } from '@/components/ui/modal'
import { cn } from '@/lib/utils'

export interface HostSection {
  /** null = Ungrouped, always shown first. */
  group: ProxyHostGroup | null
  hosts: ProxyHost[]
}

const UNGROUPED = 'ungrouped'
const COLLAPSED_KEY = 'ghostwire.proxyHosts.collapsedGroups'

function sectionKey(section: HostSection) {
  return section.group?.id ?? UNGROUPED
}

// ── Pure layout helpers ─────────────────────────────────────────────────────

export function buildSections(hosts: ProxyHost[], groups: ProxyHostGroup[]): HostSection[] {
  const known = new Set(groups.map((g) => g.id))
  const byGroup = new Map<string, ProxyHost[]>()
  for (const host of hosts) {
    const key = host.group_id && known.has(host.group_id) ? host.group_id : UNGROUPED
    const list = byGroup.get(key) ?? []
    list.push(host)
    byGroup.set(key, list)
  }
  const ordered = (list: ProxyHost[] = []) =>
    [...list].sort(
      (a, b) =>
        (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
        (b.created_at ?? '').localeCompare(a.created_at ?? '')
    )
  return [
    { group: null, hosts: ordered(byGroup.get(UNGROUPED)) },
    ...[...groups]
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
      .map((group) => ({ group, hosts: ordered(byGroup.get(group.id)) })),
  ]
}

export function layoutPayload(sections: HostSection[]) {
  return {
    sections: sections.map((s) => ({ group_id: s.group?.id ?? null, host_ids: s.hosts.map((h) => h.id) })),
  }
}

/** Move a host to `toIndex` within the section for `toGroupId` (null = Ungrouped). */
export function moveHost(
  sections: HostSection[],
  hostId: string,
  toGroupId: string | null,
  toIndex: number
): HostSection[] {
  const host = sections.flatMap((s) => s.hosts).find((h) => h.id === hostId)
  if (!host) return sections
  const fromKey = sections.find((s) => s.hosts.some((h) => h.id === hostId))
  const fromIndex = fromKey ? fromKey.hosts.findIndex((h) => h.id === hostId) : -1
  const sameSection = (fromKey?.group?.id ?? null) === toGroupId
  // Removing the host first shifts later positions in its own section up by one.
  const index = sameSection && fromIndex !== -1 && fromIndex < toIndex ? toIndex - 1 : toIndex
  const without = sections.map((s) => ({ ...s, hosts: s.hosts.filter((h) => h.id !== hostId) }))
  return without.map((s) => {
    if ((s.group?.id ?? null) !== toGroupId) return s
    const hosts = [...s.hosts]
    hosts.splice(Math.max(0, Math.min(index, hosts.length)), 0, { ...host, group_id: toGroupId })
    return { ...s, hosts }
  })
}

/** Move a group to sit before `beforeGroupId` (null = to the end). Ungrouped stays first. */
export function moveGroup(sections: HostSection[], groupId: string, beforeGroupId: string | null): HostSection[] {
  if (groupId === beforeGroupId) return sections
  const [ungrouped, ...groups] = sections
  const moving = groups.find((s) => s.group?.id === groupId)
  if (!moving) return sections
  const rest = groups.filter((s) => s.group?.id !== groupId)
  const at = beforeGroupId ? rest.findIndex((s) => s.group?.id === beforeGroupId) : -1
  if (at === -1) rest.push(moving)
  else rest.splice(at, 0, moving)
  return [ungrouped, ...rest]
}

// ── Collapsed groups (per browser) ──────────────────────────────────────────

function readCollapsed(): Set<string> {
  // The list only renders after hosts load in the browser, so reading storage
  // in the initialiser can't cause a server/client mismatch.
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = localStorage.getItem(COLLAPSED_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    // Private window or blocked storage: everything starts expanded.
    return new Set()
  }
}

function useCollapsed() {
  const [collapsed, setCollapsed] = useState<Set<string>>(readCollapsed)
  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      try {
        localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]))
      } catch {
        // Not saved; still collapses for this visit.
      }
      return next
    })
  return { collapsed, toggle }
}

// ── The list ────────────────────────────────────────────────────────────────

type Drag = { kind: 'host'; id: string } | { kind: 'group'; id: string } | null
type Drop =
  | { kind: 'host'; groupId: string | null; index: number }
  | { kind: 'group'; beforeGroupId: string | null }
  | null

export interface HostRenderExtras {
  /** Grip to drag the card by (hidden on phones). */
  handle: ReactNode
  /** Move up / down / to group items for the card's ⋯ menu. */
  moveMenuItems: ReactNode
}

interface HostSectionsProps {
  sections: HostSection[]
  renderHost: (host: ProxyHost, extras: HostRenderExtras) => ReactNode
  onLayoutChange: (next: HostSection[]) => void
  onRenameGroup: (group: ProxyHostGroup) => void
  onDeleteGroup: (group: ProxyHostGroup) => void
  onAddHostToGroup: (group: ProxyHostGroup) => void
}

export function HostSections({
  sections,
  renderHost,
  onLayoutChange,
  onRenameGroup,
  onDeleteGroup,
  onAddHostToGroup,
}: HostSectionsProps) {
  const { collapsed, toggle } = useCollapsed()
  const [drag, setDrag] = useState<Drag>(null)
  const [drop, setDrop] = useState<Drop>(null)
  const groups = sections.filter((s) => s.group) as (HostSection & { group: ProxyHostGroup })[]
  const hasGroups = groups.length > 0

  const endDrag = () => {
    setDrag(null)
    setDrop(null)
  }

  const commitDrop = () => {
    if (drag?.kind === 'host' && drop?.kind === 'host') {
      onLayoutChange(moveHost(sections, drag.id, drop.groupId, drop.index))
    } else if (drag?.kind === 'group' && drop?.kind === 'group') {
      onLayoutChange(moveGroup(sections, drag.id, drop.beforeGroupId))
    }
    endDrag()
  }

  const startDrag = (e: DragEvent, next: NonNullable<Drag>, selector: string) => {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', next.id)
    const card = (e.currentTarget as HTMLElement).closest(selector)
    if (card) e.dataTransfer.setDragImage(card, 16, 16)
    setDrag(next)
  }

  const moveMenuFor = (host: ProxyHost, section: HostSection, index: number) => {
    const groupId = section.group?.id ?? null
    return (
      <>
        <DropdownMenuItem disabled={index === 0} onClick={() => onLayoutChange(moveHost(sections, host.id, groupId, index - 1))}>
          <ArrowUp className="h-4 w-4" />
          Move up
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={index === section.hosts.length - 1}
          onClick={() => onLayoutChange(moveHost(sections, host.id, groupId, index + 2))}
        >
          <ArrowDown className="h-4 w-4" />
          Move down
        </DropdownMenuItem>
        {hasGroups && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <FolderInput className="h-4 w-4" />
              Move to group
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="w-48">
              {[{ id: null as string | null, name: 'Ungrouped' }, ...groups.map((g) => g.group)].map((g) => {
                const target = sections.find((s) => (s.group?.id ?? null) === g.id)
                return (
                  <DropdownMenuItem
                    key={g.id ?? UNGROUPED}
                    disabled={g.id === groupId}
                    onClick={() => onLayoutChange(moveHost(sections, host.id, g.id, target?.hosts.length ?? 0))}
                  >
                    <span className="truncate">{g.name}</span>
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
      </>
    )
  }

  const hostDragOver = (e: DragEvent<HTMLDivElement>, groupId: string | null, index: number) => {
    if (drag?.kind !== 'host') return
    e.preventDefault()
    e.stopPropagation()
    const rect = e.currentTarget.getBoundingClientRect()
    const after = e.clientY > rect.top + rect.height / 2
    setDrop({ kind: 'host', groupId, index: after ? index + 1 : index })
  }

  const sectionDragOver = (e: DragEvent<HTMLDivElement>, section: HostSection) => {
    if (drag?.kind !== 'host') return
    e.preventDefault()
    // Over the section but not a card (its header, gaps, an empty group): drop at the end.
    setDrop({ kind: 'host', groupId: section.group?.id ?? null, index: section.hosts.length })
  }

  const groupDragOver = (e: DragEvent<HTMLDivElement>, groupId: string, nextGroupId: string | null) => {
    if (drag?.kind !== 'group') return
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    const after = e.clientY > rect.top + rect.height / 2
    setDrop({ kind: 'group', beforeGroupId: after ? nextGroupId : groupId })
  }

  const indicator = <div className="h-0.5 rounded-full bg-primary" aria-hidden />

  return (
    <div className="space-y-6" onDragEnd={endDrag}>
      {sections.map((section) => {
        const key = sectionKey(section)
        const group = section.group
        const groupId = group?.id ?? null
        // Ungrouped gets no heading until there are groups to tell it apart from,
        // and hides when empty unless a host is being dragged (so it can be dropped there).
        if (!group && hasGroups && section.hosts.length === 0 && drag?.kind !== 'host') return null
        const isCollapsed = collapsed.has(key)
        const nextGroupId = groups[groups.findIndex((g) => g.group.id === groupId) + 1]?.group.id ?? null
        const groupPos = groups.findIndex((g) => g.group.id === groupId)
        const showGroupDropBefore = drag?.kind === 'group' && drop?.kind === 'group' && group && drop.beforeGroupId === group.id
        const showGroupDropAfter =
          drag?.kind === 'group' && drop?.kind === 'group' && group && drop.beforeGroupId === null && groupPos === groups.length - 1

        return (
          <div key={key} className="space-y-3" onDragOver={(e) => sectionDragOver(e, section)} onDrop={commitDrop}>
            {showGroupDropBefore && indicator}
            {(group || hasGroups) && (
              <div
                data-group-header
                className={cn(
                  'flex items-center gap-2',
                  drag?.kind === 'group' && drag.id === groupId && 'opacity-50'
                )}
                onDragOver={group ? (e) => groupDragOver(e, group.id, nextGroupId) : undefined}
              >
                {group && (
                  <span
                    draggable
                    onDragStart={(e) => startDrag(e, { kind: 'group', id: group.id }, '[data-group-header]')}
                    className="hidden sm:flex cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
                    title="Drag to reorder groups"
                    aria-hidden
                  >
                    <GripVertical className="h-4 w-4" />
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  className="flex min-w-0 items-center gap-1.5 text-sm font-semibold hover:text-primary transition-colors"
                  aria-expanded={!isCollapsed}
                >
                  {isCollapsed ? <ChevronRight className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
                  <span className="truncate">{group ? group.name : 'Ungrouped'}</span>
                </button>
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                  {section.hosts.length}
                </span>
                <div className="h-px flex-1 bg-border" />
                {group && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" type="button" title="Group actions" aria-label={`Actions for ${group.name}`}>
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                      <DropdownMenuItem onClick={() => onAddHostToGroup(group)}>
                        <Plus className="h-4 w-4" />
                        Add host here
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onRenameGroup(group)}>
                        <Pencil className="h-4 w-4" />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={groupPos === 0}
                        onClick={() => onLayoutChange(moveGroup(sections, group.id, groups[groupPos - 1]?.group.id ?? null))}
                      >
                        <ArrowUp className="h-4 w-4" />
                        Move group up
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={groupPos === groups.length - 1}
                        onClick={() => onLayoutChange(moveGroup(sections, group.id, groups[groupPos + 2]?.group.id ?? null))}
                      >
                        <ArrowDown className="h-4 w-4" />
                        Move group down
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => onDeleteGroup(group)} className="text-red-500 focus:text-red-500">
                        <Trash2 className="h-4 w-4" />
                        Delete group
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            )}

            {!isCollapsed && (
              <div className="space-y-3">
                {section.hosts.length === 0 && group && (
                  <div
                    className={cn(
                      'rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground',
                      drag?.kind === 'host' && drop?.kind === 'host' && drop.groupId === groupId
                        ? 'border-primary text-foreground'
                        : 'border-border'
                    )}
                  >
                    No hosts in this group. Drag one here, or use Move to group in a host&apos;s menu.
                  </div>
                )}
                {section.hosts.map((host, index) => {
                  const showBefore =
                    drag?.kind === 'host' && drop?.kind === 'host' && drop.groupId === groupId && drop.index === index
                  return (
                    <div key={host.id} className="space-y-3">
                      {showBefore && indicator}
                      <div
                        data-host-card
                        className={cn(drag?.kind === 'host' && drag.id === host.id && 'opacity-50')}
                        onDragOver={(e) => hostDragOver(e, groupId, index)}
                      >
                        {renderHost(host, {
                          handle: (
                            <span
                              draggable
                              onDragStart={(e) => startDrag(e, { kind: 'host', id: host.id }, '[data-host-card]')}
                              className="hidden sm:flex mt-1 cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
                              title="Drag to reorder or move to another group"
                              aria-hidden
                            >
                              <GripVertical className="h-4 w-4" />
                            </span>
                          ),
                          moveMenuItems: moveMenuFor(host, section, index),
                        })}
                      </div>
                    </div>
                  )
                })}
                {drag?.kind === 'host' &&
                  drop?.kind === 'host' &&
                  drop.groupId === groupId &&
                  drop.index === section.hosts.length &&
                  section.hosts.length > 0 &&
                  indicator}
              </div>
            )}
            {showGroupDropAfter && indicator}
          </div>
        )
      })}
    </div>
  )
}

// ── Add / rename dialog ─────────────────────────────────────────────────────

interface GroupNameDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The group being renamed; null to add a new one. */
  group: ProxyHostGroup | null
  onSave: (name: string) => Promise<void>
}

export function GroupNameDialog({ open, onOpenChange, group, onSave }: GroupNameDialogProps) {
  return (
    <Modal open={open} onOpenChange={onOpenChange} size="md">
      {/* Mounted only while open, so each opening starts from the group's current name. */}
      {open && <GroupNameForm group={group} onSave={onSave} onClose={() => onOpenChange(false)} />}
    </Modal>
  )
}

function GroupNameForm({
  group,
  onSave,
  onClose,
}: {
  group: ProxyHostGroup | null
  onSave: (name: string) => Promise<void>
  onClose: () => void
}) {
  const [name, setName] = useState(group?.name ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Give the group a name')
      return
    }
    setSaving(true)
    setError('')
    try {
      await onSave(trimmed)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Could not save the group')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <ModalHeader className="p-6 pb-2">
        <ModalTitle>{group ? 'Rename group' : 'Add group'}</ModalTitle>
      </ModalHeader>
      <ModalBody className="px-6 py-4 space-y-2">
        <label htmlFor="host-group-name" className="block text-sm font-medium">
          Name
        </label>
        <Input
          id="host-group-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          placeholder="e.g. Media, Dev sites, Customers"
          autoFocus
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
      </ModalBody>
      <ModalFooter className="p-6 pt-2">
        <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving}>
          {group ? 'Save' : 'Add group'}
        </Button>
      </ModalFooter>
    </form>
  )
}
