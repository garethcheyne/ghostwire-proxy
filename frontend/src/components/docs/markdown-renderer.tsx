'use client'

import { cn } from '@/lib/utils'
import { useEffect, useRef, useState } from 'react'

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
          'prose prose-invert prose-slate max-w-none',
          'prose-headings:text-foreground prose-headings:scroll-mt-20',
          'prose-h2:text-xl prose-h2:font-bold prose-h2:mt-8 prose-h2:mb-4',
          'prose-h3:text-lg prose-h3:font-semibold prose-h3:mt-6 prose-h3:mb-3',
          'prose-p:text-muted-foreground prose-p:leading-7',
          'prose-a:text-cyan-400 hover:prose-a:text-cyan-300 prose-a:underline prose-a:underline-offset-2',
          'prose-strong:text-foreground',
          'prose-code:text-cyan-300 prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono',
          'prose-pre:bg-slate-900 prose-pre:border prose-pre:border-border prose-pre:rounded-lg',
          'prose-img:rounded-lg prose-img:border prose-img:border-border prose-img:shadow-lg prose-img:cursor-pointer prose-img:transition-transform prose-img:hover:scale-[1.02]',
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

      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm cursor-pointer"
          onClick={() => setLightboxSrc(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightboxSrc}
              alt={lightboxAlt}
              className="max-w-full max-h-[90vh] rounded-lg border border-border shadow-2xl object-contain"
            />
            <button
              className="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-slate-800 border border-border text-muted-foreground hover:text-foreground flex items-center justify-center text-sm"
              onClick={(e) => { e.stopPropagation(); setLightboxSrc(null) }}
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  )
}
