import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/** The header every dashboard page starts with, so every Ghostwire app looks alike. */
export function PageHeader({
  icon: Icon,
  title,
  description,
  actions,
  children,
  backButton,
  className,
}: {
  /** The section's icon, the same one the sidebar shows for it. */
  icon: LucideIcon
  title: React.ReactNode
  description?: React.ReactNode
  /** Buttons and filters, right-aligned on wide screens and below the title on phones. */
  actions?: React.ReactNode
  /** Same as `actions`. */
  children?: React.ReactNode
  /** A back link, shown above the title row. */
  backButton?: React.ReactNode
  className?: string
}) {
  const content = actions ?? children
  return (
    <div data-slot="page-header" className={cn("space-y-2", className)}>
      {backButton}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
            <Icon className="size-5" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl">{title}</h1>
            {description && <div className="text-sm text-muted-foreground">{description}</div>}
          </div>
        </div>
        {content && <div className="flex flex-wrap items-center gap-2">{content}</div>}
      </div>
    </div>
  )
}
