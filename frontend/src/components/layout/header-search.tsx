'use client'

import { useState, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search,
  Globe,
  Shield,
  ShieldAlert,
  Lock,
  Loader2,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import api from '@/lib/api'
import { cn } from '@/lib/utils'

/** Global search in the top header (hosts, IPs, threats, certificates). Wide screens only. */
export function HeaderSearch() {
  const router = useRouter()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const searchRef = useRef<HTMLDivElement>(null)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSearchResults([])
      setSearchOpen(false)
      return
    }
    setSearchLoading(true)
    try {
      const response = await api.get('/api/search', { params: { q } })
      setSearchResults(response.data.results || [])
      setSearchOpen(true)
      setSelectedIndex(-1)
    } catch {
      setSearchResults([])
    } finally {
      setSearchLoading(false)
    }
  }, [])

  const handleSearchChange = (value: string) => {
    setSearchQuery(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => doSearch(value), 300)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setSearchOpen(false)
      return
    }
    if (!searchOpen || searchResults.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => Math.min(prev + 1, searchResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault()
      const item = searchResults[selectedIndex]
      if (item?.url) {
        router.push(item.url)
        setSearchOpen(false)
        setSearchQuery('')
      }
    }
  }

  const typeIcon = (type: string) => {
    switch (type) {
      case 'host': return <Globe className="h-4 w-4 text-blue-600 dark:text-blue-400" />
      case 'threat': return <ShieldAlert className="h-4 w-4 text-red-600 dark:text-red-400" />
      case 'blocklist': return <Shield className="h-4 w-4 text-orange-700 dark:text-orange-400" />
      case 'certificate': return <Lock className="h-4 w-4 text-green-600 dark:text-green-400" />
      default: return <Search className="h-4 w-4 text-muted-foreground" />
    }
  }

  const showResults = searchResults.length > 0
  const showNoResults = searchResults.length === 0 && searchQuery.length >= 2 && !searchLoading

  // The results list is a Popover anchored to the input. Focus stays in the input (typing and the
  // arrow keys keep working there), and a click on the input itself doesn't count as "outside".
  return (
    <div className="hidden lg:flex">
      <Popover open={searchOpen && (showResults || showNoResults)} onOpenChange={setSearchOpen}>
        <PopoverAnchor asChild>
          <div className="relative" ref={searchRef}>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            {searchLoading && (
              <Loader2 className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground animate-spin" />
            )}
            <Input
              type="search"
              placeholder="Search hosts, IPs..."
              aria-label="Search hosts, IPs, threats and certificates"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              onFocus={() => { if (searchResults.length > 0) setSearchOpen(true) }}
              className="h-9 w-48 bg-muted/50 pl-9 pr-4 xl:w-72"
            />
          </div>
        </PopoverAnchor>
        <PopoverContent
          align="start"
          className="max-h-80 w-80 gap-0 overflow-y-auto p-1 xl:w-96"
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => {
            if (searchRef.current?.contains(e.target as Node)) e.preventDefault()
          }}
        >
          {showResults ? (
            <div role="listbox" aria-label="Search results">
              {searchResults.map((item, idx) => (
                <button
                  key={`${item.type}-${item.id}`}
                  type="button"
                  role="option"
                  aria-selected={idx === selectedIndex}
                  className={cn(
                    'flex w-full items-start gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent',
                    idx === selectedIndex && 'bg-accent'
                  )}
                  onClick={() => {
                    router.push(item.url)
                    setSearchOpen(false)
                    setSearchQuery('')
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <span className="mt-0.5 shrink-0">{typeIcon(item.type)}</span>
                  <div className="min-w-0">
                    <p className="font-medium truncate">{item.title}</p>
                    <p className="text-xs text-muted-foreground truncate">{item.subtitle}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="p-3 text-center text-sm text-muted-foreground">
              No results found for &ldquo;{searchQuery}&rdquo;
            </p>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}
