'use client'

import { cn } from '@/lib/utils'
import { useEffect, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'

interface MarkdownRendererProps {
  html: string
  className?: string
}

export function MarkdownRenderer({ html, className }: MarkdownRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [lightboxAlt, setLightboxAlt] = useState('')

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleClick = (e: MouseEvent) => {
      const img = (e.target as HTMLElement).closest('img')
      if (img) {
        setLightboxSrc(img.src)
        setLightboxAlt(img.alt || '')
      }
    }

    container.addEventListener('click', handleClick)
    return () => container.removeEventListener('click', handleClick)
  }, [html])

  if (!html) {
    return <div className="text-muted-foreground">No content available</div>
  }
  return (
    <>
      <div
        ref={containerRef}
        className={cn(
          'prose prose-slate dark:prose-invert max-w-none',
          'prose-headings:text-foreground prose-headings:scroll-mt-20',
          'prose-h2:text-xl prose-h2:font-bold prose-h2:mt-8 prose-h2:mb-4',
          'prose-h3:text-lg prose-h3:font-semibold prose-h3:mt-6 prose-h3:mb-3',
          'prose-p:text-muted-foreground prose-p:leading-7',
          'prose-a:text-brand hover:prose-a:text-brand prose-a:underline prose-a:underline-offset-2',
          'prose-strong:text-foreground',
          'prose-code:text-brand prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono',
          'prose-pre:bg-muted prose-pre:text-foreground prose-pre:border prose-pre:border-border prose-pre:rounded-lg',
          'prose-img:rounded-lg prose-img:border prose-img:border-border prose-img:shadow-lg prose-img:cursor-pointer',
          'prose-table:text-sm',
          'prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-medium',
          'prose-td:border prose-td:border-border prose-td:px-3 prose-td:py-2',
          'prose-blockquote:border-l-4 prose-blockquote:border-border prose-blockquote:text-muted-foreground',
          'prose-li:text-muted-foreground',
          'prose-hr:border-border',
          className
        )}
        dangerouslySetInnerHTML={{ __html: html }}
      />

      <Dialog open={lightboxSrc !== null} onOpenChange={(open) => { if (!open) setLightboxSrc(null) }}>
        <DialogContent className="w-fit max-w-[90vw] p-2 sm:max-w-[90vw]">
          <DialogTitle className="sr-only">{lightboxAlt || 'Image'}</DialogTitle>
          {lightboxSrc && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={lightboxSrc}
              alt={lightboxAlt}
              className="max-h-[85vh] max-w-full rounded-lg object-contain"
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
