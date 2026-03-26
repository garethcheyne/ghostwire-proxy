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
    <div className="flex min-h-0 -m-3 sm:-m-4 md:-m-6">
      {/* Docs sidebar */}
      <div className="hidden lg:block shrink-0">
        <DocsSidebar navigation={navigation} />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl px-6 py-8">
          {children}
        </div>
      </div>
    </div>
  )
}
