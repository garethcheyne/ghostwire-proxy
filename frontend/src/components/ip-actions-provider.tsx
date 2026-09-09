'use client'

import { createContext, useCallback, useContext, useMemo, useState } from 'react'

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

  const labelIp = useCallback((ip: string) => {
    setReportIp(null)          // never show both at once
    setLabellingIp(ip)
  }, [])

  const showReport = useCallback((ip: string) => {
    setLabellingIp(null)
    setReportIp(ip)
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
          onOpenChange={(open) => { if (!open) setLabellingIp(null) }}
        />
      )}
      {reportIp && <IpReport ip={reportIp} onClose={() => setReportIp(null)} />}
    </IpActionsContext.Provider>
  )
}

export default IpActionsProvider
