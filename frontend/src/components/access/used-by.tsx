import type { ProxyHostRef } from '@/types'

/** Which proxy hosts an access list or auth wall is assigned to. */
export function UsedBy({ hosts }: { hosts?: ProxyHostRef[] }) {
  if (!hosts?.length) {
    return <p className="text-xs text-muted-foreground">Not used by any host</p>
  }
  return (
    <p className="text-xs text-muted-foreground">
      Used by: <span className="text-foreground">{hosts.map((h) => h.domain_names[0]).join(', ')}</span>
    </p>
  )
}

/** Delete confirmation text that warns when hosts would lose this protection. */
export function deleteWarning(name: string, hosts: ProxyHostRef[] | undefined, what: string) {
  if (!hosts?.length) return `Are you sure you want to delete "${name}"?`
  const names = hosts.map((h) => h.domain_names[0]).join(', ')
  return `"${name}" protects ${hosts.length === 1 ? '1 host' : `${hosts.length} hosts`} (${names}). Deleting it removes the ${what} from them, leaving them open. Continue?`
}
