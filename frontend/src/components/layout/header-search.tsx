'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search,
  Globe,
  Shield,
  ShieldAlert,
  Lock,
  Loader2,
} from 'lucide-react'
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

  // Close search dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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

  return (
    <div className="hidden lg:flex">
      <div className="relative" ref={searchRef}>
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        {searchLoading && (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground animate-spin" />
        )}
        <input
          type="search"
          placeholder="Search hosts, IPs..."
          value={searchQuery}
          onChange={(e) => handleSearchChange(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          onFocus={() => { if (searchResults.length > 0) setSearchOpen(true) }}
          className="h-9 w-48 xl:w-72 rounded-md border bg-muted/50 pl-9 pr-4 text-sm outline-hidden placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
        />
        {searchOpen && searchResults.length > 0 && (
          <div className="absolute top-full left-0 mt-1 w-80 xl:w-96 rounded-md border bg-popover shadow-lg z-50 max-h-80 overflow-y-auto">
            {searchResults.map((item, idx) => (
              <button
                key={`${item.type}-${item.id}`}
                className={cn(
                  'flex items-start gap-3 w-full px-3 py-2 text-left text-sm hover:bg-accent transition-colors',
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
        )}
        {searchOpen && searchResults.length === 0 && searchQuery.length >= 2 && !searchLoading && (
          <div className="absolute top-full left-0 mt-1 w-80 xl:w-96 rounded-md border bg-popover shadow-lg z-50 p-4 text-center text-sm text-muted-foreground">
            No results found for &ldquo;{searchQuery}&rdquo;
          </div>
        )}
      </div>
    </div>
  )
}
