import { getNavigation } from '@/lib/docs'
import { DocsSidebar } from '@/components/docs/docs-sidebar'

export const dynamic = 'force-dynamic'

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const navigation = getNavigation()

  return (
    // Same viewport trap as the app shell: 100vh is the height with browser
    // chrome hidden, so on a phone this ran past the bottom of the screen and
    // the end of every doc page was unreachable. dvh tracks the visible height,
    // with the vh value kept as the fallback.
    <div className="flex -m-3 sm:-m-4 md:-m-6 h-[calc(100vh-3.5rem)] supports-[height:100dvh]:h-[calc(100dvh-3.5rem)]">
      {/* Docs sidebar */}
      <div className="hidden lg:block shrink-0 overflow-y-auto">
        <DocsSidebar navigation={navigation} />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Narrower gutters on a phone, and bottom padding so the last
            paragraph clears the fixed tab bar. */}
        <div className="max-w-4xl px-4 py-6 sm:px-6 sm:py-8 pb-[calc(64px+env(safe-area-inset-bottom)+1.5rem)] md:pb-8">
          {children}
        </div>
      </div>
    </div>
  )
}
