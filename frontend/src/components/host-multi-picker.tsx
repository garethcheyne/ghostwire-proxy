'use client'

import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

interface HostOption {
  id: string
  domain_names: string[]
}

/**
 * The "Apply to Host" picker on the security rule dialogs: nothing selected means every host
 * (a global rule); otherwise one or more proxy hosts.
 */
export function HostMultiPicker({
  hosts,
  value,
  onChange,
  id,
}: {
  hosts: HostOption[]
  value: string[]
  onChange: (ids: string[]) => void
  id?: string
}) {
  const [open, setOpen] = useState(false)

  const label =
    value.length === 0
      ? 'All Hosts (global)'
      : value.length === 1
        ? hosts.find(h => h.id === value[0])?.domain_names[0] || '1 host'
        : `${value.length} hosts selected`

  const toggle = (hostId: string) =>
    onChange(value.includes(hostId) ? value.filter(v => v !== hostId) : [...value, hostId])

  return (
    // modal: the picker sits inside a dialog, whose scroll lock would otherwise stop the list scrolling.
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          size="lg"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className="truncate">{label}</span>
          <ChevronDown className={cn('opacity-50 transition-transform', open && 'rotate-180')} />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput placeholder="Search hosts..." />
          <CommandList className="max-h-56">
            <CommandEmpty>No hosts found.</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="__all__ All Hosts (global)"
                data-checked={value.length === 0}
                onSelect={() => {
                  onChange([])
                  setOpen(false)
                }}
              >
                All Hosts (global)
              </CommandItem>
            </CommandGroup>
            {hosts.length > 0 && <CommandSeparator />}
            <CommandGroup>
              {hosts.map(h => (
                <CommandItem
                  key={h.id}
                  value={`${h.id} ${h.domain_names.join(' ')}`}
                  data-checked={value.includes(h.id)}
                  onSelect={() => toggle(h.id)}
                >
                  <span className="truncate">{h.domain_names[0]}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
