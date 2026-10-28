import { ArrowDown, ArrowUp, type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

const toneText = {
  default: "",
  success: "text-green-600 dark:text-green-400",
  warning: "text-amber-700 dark:text-amber-400",
  danger: "text-red-600 dark:text-red-400",
  info: "text-sky-600 dark:text-sky-400",
} as const

/**
 * A summary number on a dashboard or list page. Every stat tile in every Ghostwire app is one of
 * these: a plain card, the label and icon on top, the number across the full width underneath.
 * Colour goes on the number (`tone`) only when it means something, never on the card.
 */
export function StatCard({
  title,
  value,
  icon: Icon,
  description,
  tone = "default",
  trend,
  trendValue,
  onClick,
  active,
  className,
}: {
  title: React.ReactNode
  value: React.ReactNode
  icon?: LucideIcon
  description?: React.ReactNode
  /** Colour for the number: success, warning, danger or info. */
  tone?: keyof typeof toneText
  trend?: "up" | "down" | null
  trendValue?: React.ReactNode
  /** Makes the tile a filter button (for example "show only critical"). */
  onClick?: () => void
  /** Marks the tile as the active filter. */
  active?: boolean
  className?: string
}) {
  const Comp = onClick ? "button" : "div"
  return (
    <Comp
      data-slot="stat-card"
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-pressed={onClick ? !!active : undefined}
      className={cn(
        "rounded-xl border bg-card p-4 text-left text-card-foreground sm:p-6",
        onClick && "transition-colors hover:bg-accent/50",
        active && "border-primary ring-1 ring-primary/30",
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-xs leading-tight font-medium text-muted-foreground sm:text-sm">
          {title}
        </p>
        {Icon && (
          <div className="shrink-0 rounded-lg bg-primary/10 p-1.5 sm:p-2.5">
            <Icon className="size-4 text-primary sm:size-5" />
          </div>
        )}
      </div>
      <p
        className={cn(
          "mt-1.5 text-xl leading-tight font-bold tabular-nums wrap-break-word sm:mt-2 sm:text-3xl",
          toneText[tone]
        )}
      >
        {value}
      </p>
      {description && (
        <p className="mt-1 text-xs leading-tight text-muted-foreground sm:text-sm">{description}</p>
      )}
      {trend && trendValue && (
        <div
          className={cn(
            "mt-2 flex items-center gap-1 text-xs sm:text-sm",
            trend === "up" ? toneText.success : toneText.danger
          )}
        >
          {trend === "up" ? <ArrowUp className="size-3 sm:size-4" /> : <ArrowDown className="size-3 sm:size-4" />}
          <span>{trendValue}</span>
        </div>
      )}
    </Comp>
  )
}
