'use client'

import { useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { cn } from '@/lib/utils'

export interface MultiOption {
  value: string
  label: string
  hint?: string
}

interface MultiSelectProps {
  label: string
  options: MultiOption[]
  selected: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  /** Lets the user add a value that isn't in the list (e.g. an exact status code). */
  allowCustom?: (value: string) => boolean
  className?: string
}

/** A filter dropdown with checkboxes: shadcn Popover + Command. */
export function MultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = 'Search…',
  allowCustom,
  className,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  const known = new Set(options.map((o) => o.value))
  const custom = query.trim()
  const canAddCustom = Boolean(allowCustom && custom && !known.has(custom) && allowCustom(custom))
  const selectedLabel =
    selected.length === 1
      ? (options.find((o) => o.value === selected[0])?.label ?? selected[0])
      : `${selected.length} selected`

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn('h-9 justify-between gap-2 text-sm font-normal', selected.length && 'border-primary/50', className)}
        >
          <span className="truncate">
            <span className="text-muted-foreground">{label}</span>
            {selected.length > 0 && <span className="ml-1.5 font-medium">{selectedLabel}</span>}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command>
          <CommandInput placeholder={placeholder} value={query} onValueChange={setQuery} />
          <CommandList>
            <CommandEmpty>{canAddCustom ? null : 'Nothing matches.'}</CommandEmpty>
            {canAddCustom && (
              <CommandGroup>
                <CommandItem
                  value={`add:${custom}`}
                  onSelect={() => {
                    onChange([...selected, custom])
                    setQuery('')
                  }}
                >
                  Add “{custom}”
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {[...selected.filter((v) => !known.has(v)).map((v): MultiOption => ({ value: v, label: v })), ...options].map(
                (o) => (
                  <CommandItem key={o.value} value={`${o.label} ${o.value}`} onSelect={() => toggle(o.value)}>
                    <Checkbox checked={selected.includes(o.value)} className="mr-2" tabIndex={-1} />
                    <span className="truncate">{o.label}</span>
                    {o.hint && (
                      <Badge variant="secondary" className="ml-auto shrink-0 font-normal">
                        {o.hint}
                      </Badge>
                    )}
                  </CommandItem>
                )
              )}
            </CommandGroup>
            {selected.length > 0 && (
              <CommandGroup>
                <CommandItem value="__clear" onSelect={() => onChange([])} className="text-muted-foreground">
                  <X className="mr-2" />
                  Clear selection
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
