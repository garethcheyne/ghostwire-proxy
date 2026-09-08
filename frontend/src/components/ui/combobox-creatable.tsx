'use client'

import * as React from 'react'
import { Check, ChevronsUpDown, Plus, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export interface ComboboxOption {
  value: string
  /** Shown after the label, e.g. a count. */
  hint?: string
}

interface Props {
  value: string
  onChange: (value: string) => void
  options: ComboboxOption[]
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  /** Allow entering a value that isn't in the list. */
  allowCreate?: boolean
  className?: string
  id?: string
}

/**
 * A select you can also type a new value into.
 *
 * Radix's Select only picks from a fixed list, and a native <input list> renders
 * an unstyled browser dropdown that ignores the theme. This is the shadcn
 * combobox pattern — Popover + Command — with the ability to create a value that
 * isn't there yet, which is what a field like "group" needs: mostly you reuse an
 * existing group, occasionally you invent one.
 */
export function ComboboxCreatable({
  value,
  onChange,
  options,
  placeholder = 'Select…',
  searchPlaceholder = 'Search or type a new value…',
  emptyText = 'No matches',
  allowCreate = true,
  className,
  id,
}: Props) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState('')

  const trimmed = query.trim()
  const exists = options.some((o) => o.value.toLowerCase() === trimmed.toLowerCase())
  const canCreate = allowCreate && trimmed.length > 0 && !exists

  const commit = (next: string) => {
    onChange(next)
    setQuery('')
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-full justify-between font-normal', !value && 'text-muted-foreground', className)}
        >
          <span className="truncate">{value || placeholder}</span>
          <span className="flex items-center gap-1 shrink-0">
            {value && (
              // Clearing has to be reachable: a group is optional, and without
              // this the only way to unset it is to delete the record.
              <span
                role="button"
                tabIndex={-1}
                aria-label="Clear"
                onClick={(e) => { e.stopPropagation(); onChange('') }}
                className="rounded p-0.5 opacity-50 hover:opacity-100 hover:bg-muted"
              >
                <X className="h-3 w-3" />
              </span>
            )}
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput
            placeholder={searchPlaceholder}
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            <CommandEmpty>{canCreate ? null : emptyText}</CommandEmpty>
            {canCreate && (
              <CommandGroup>
                <CommandItem value={`__create__${trimmed}`} onSelect={() => commit(trimmed)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create &ldquo;{trimmed}&rdquo;
                </CommandItem>
              </CommandGroup>
            )}
            {options.length > 0 && (
              <CommandGroup>
                {options.map((o) => (
                  <CommandItem key={o.value} value={o.value} onSelect={() => commit(o.value)}>
                    <Check className={cn('mr-2 h-4 w-4', value === o.value ? 'opacity-100' : 'opacity-0')} />
                    <span className="truncate">{o.value}</span>
                    {o.hint && <span className="ml-auto text-xs text-muted-foreground">{o.hint}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

export default ComboboxCreatable
