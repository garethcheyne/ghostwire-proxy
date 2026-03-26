import { getDocPage } from '@/lib/docs'
import { MarkdownRenderer } from '@/components/docs/markdown-renderer'
import { notFound } from 'next/navigation'

export const dynamic = 'force-dynamic'

interface DocsPageProps {
  params: Promise<{ slug: string[] }>
}

export default async function DocsSlugPage({ params }: DocsPageProps) {
  const { slug } = await params
  const page = getDocPage(slug)
  if (!page) return notFound()

  return (
    <div>
      {/* Title */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground">{page.title}</h1>
        {page.excerpt && (
          <p className="text-lg text-muted-foreground mt-2">{page.excerpt}</p>
        )}
      </div>

      {/* Content */}
      <MarkdownRenderer html={page.html} />
    </div>
  )
}
