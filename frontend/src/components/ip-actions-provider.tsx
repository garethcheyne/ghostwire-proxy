'use client'

import { createContext, useCallback, useContext, useMemo, useState } from 'react'

import { closeAllModals } from '@/components/ui/modal'
import { KnownIpQuickAdd } from '@/components/known-ip-quick-add'
import { IpReport } from '@/components/ip-report'
import { useKnownIpMap, type KnownIpLabel } from '@/lib/queries/known-ips'

interface IpActions {
  labelIp: (ip: string) => void
  showReport: (ip: string) => void
}

const noop: IpActions = { labelIp: () => {}, showReport: () => {} }
const IpActionsContext = createContext<IpActions>(noop)

export const useIpActions = () => useContext(IpActionsContext)

/**
 * Owns the one label dialog and the one traffic report for the whole page.
 *
 * These used to be rendered by IpAddress itself, which meant a table of 50 rows
 * mounted 50 dialog roots, and opening one from inside a hover card nested a
 * Radix dialog inside a Radix popover — which stacked dialogs and left the page
 * unclickable when they unwound. Hoisting them here means exactly one of each
 * exists, mounted above the grid rather than inside a row.
 */
export function IpActionsProvider({ children }: { children: React.ReactNode }) {
  const [labellingIp, setLabellingIp] = useState<string | null>(null)
  const [reportIp, setReportIp] = useState<string | null>(null)
  const knownIps = useKnownIpMap()

  // These are reached from the IP hover card, which is often itself inside a
  // dialog (a request-details view, say). Close whatever is open first so the
  // label dialog replaces it rather than stacking on top of it.
  const labelIp = useCallback((ip: string) => {
    closeAllModals()
    setReportIp(null)
    setLabellingIp(ip)
  }, [])

  const showReport = useCallback((ip: string) => {
    closeAllModals()
    setLabellingIp(null)
    setReportIp(ip)
  }, [])

  // Stable identity: Modal keys its close registry on this function, so a new
  // one each render would add and remove the entry on every render.
  const handleLabelOpenChange = useCallback((open: boolean) => {
    if (!open) setLabellingIp(null)
  }, [])

  const value = useMemo(() => ({ labelIp, showReport }), [labelIp, showReport])

  const existing: KnownIpLabel | null = labellingIp ? knownIps[labellingIp] ?? null : null

  return (
    <IpActionsContext.Provider value={value}>
      {children}
      {labellingIp && (
        <KnownIpQuickAdd
          ip={labellingIp}
          existing={existing}
          open
          onOpenChange={handleLabelOpenChange}
        />
      )}
      {reportIp && <IpReport ip={reportIp} onClose={() => setReportIp(null)} />}
    </IpActionsContext.Provider>
  )
}

export default IpActionsProvider
