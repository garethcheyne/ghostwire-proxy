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
    <div className="flex -m-3 sm:-m-4 md:-m-6 h-[calc(100vh-3.5rem)]">
      {/* Docs sidebar */}
      <div className="hidden lg:block shrink-0 overflow-y-auto">
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
