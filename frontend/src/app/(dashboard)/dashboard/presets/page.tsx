'use client'

import { useState, useEffect } from 'react'
import {
  Sparkles,
  Shield,
  Globe,
  Gauge,
  AlertTriangle,
  Check,
  Loader2,
  ChevronDown,
  ChevronRight,
  Info,
  Trash2,
} from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface PresetSummary {
  id: string
  name: string
  description: string
  category: string
  severity: string
  tags: string[]
  version: string
  rule_count: number
  applied: boolean
}

interface PresetDetail {
  id: string
  name: string
  description: string
  category: string
  severity: string
  tags: string[]
  version: string
  author: string
  rules?: Array<{
    name: string
    description?: string
    notes?: string
    [key: string]: unknown
  }>
  thresholds?: Array<{
    name: string
    notes?: string
    [key: string]: unknown
  }>
}

interface ApplyResult {
  preset_id: string
  preset_name: string
  category: string
  items_created: number
  items: Array<{ type: string; name: string; id: string }>
}

const categoryConfig: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  waf: { label: 'WAF Rules', icon: Shield, color: 'text-red-400' },
  geoip: { label: 'GeoIP', icon: Globe, color: 'text-blue-400' },
  rate_limit: { label: 'Rate Limiting', icon: Gauge, color: 'text-yellow-400' },
  threat_response: { label: 'Threat Response', icon: AlertTriangle, color: 'text-purple-400' },
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-500 border-red-500/20',
  high: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
  medium: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  low: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
}

export default function PresetsPage() {
  const [presets, setPresets] = useState<PresetSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedPreset, setExpandedPreset] = useState<string | null>(null)
  const [presetDetail, setPresetDetail] = useState<PresetDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [applying, setApplying] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, ApplyResult>>({})
  const [filter, setFilter] = useState<string | null>(null)

  useEffect(() => {
    fetchPresets()
  }, [])

  const fetchPresets = async () => {
    try {
      const { data } = await api.get('/api/presets/')
      setPresets(data)
    } catch (err) {
      console.error('Failed to fetch presets:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleExpand = async (presetId: string) => {
    if (expandedPreset === presetId) {
      setExpandedPreset(null)
      setPresetDetail(null)
      return
    }

    setExpandedPreset(presetId)
    setDetailLoading(true)
    try {
      const { data } = await api.get(`/api/presets/${presetId}`)
      setPresetDetail(data)
    } catch (err) {
      console.error('Failed to fetch preset detail:', err)
    } finally {
      setDetailLoading(false)
    }
  }

  const applyPreset = async (presetId: string) => {
    setApplying(presetId)
    try {
      const { data } = await api.post(`/api/presets/${presetId}/apply`)
      setResults((prev) => ({ ...prev, [presetId]: data }))
      // Update the preset's applied status
      setPresets((prev) => prev.map((p) => p.id === presetId ? { ...p, applied: true } : p))
    } catch (err) {
      console.error('Failed to apply preset:', err)
    } finally {
      setApplying(null)
    }
  }

  const removePreset = async (presetId: string) => {
    setRemoving(presetId)
    try {
      await api.delete(`/api/presets/${presetId}/remove`)
      setResults((prev) => {
        const updated = { ...prev }
        delete updated[presetId]
        return updated
      })
      setPresets((prev) => prev.map((p) => p.id === presetId ? { ...p, applied: false } : p))
    } catch (err) {
      console.error('Failed to remove preset:', err)
    } finally {
      setRemoving(null)
    }
  }

  const categories = ['waf', 'geoip', 'rate_limit', 'threat_response']
  const filtered = filter ? presets.filter((p) => p.category === filter) : presets

  // Group by category
  const grouped = categories.reduce(
    (acc, cat) => {
      const items = filtered.filter((p) => p.category === cat)
      if (items.length > 0) acc[cat] = items
      return acc
    },
    {} as Record<string, PresetSummary[]>,
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Sparkles className="h-8 w-8 text-cyan-400" />
          Security Presets
        </h1>
        <p className="text-slate-400 mt-1">
          Best-practice security templates. Preview rules before applying — presets are additive and never remove existing rules.
        </p>
      </div>

      {/* Category Filters */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={!filter ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter(null)}
          className={!filter ? 'bg-cyan-600 hover:bg-cyan-700' : ''}
        >
          All
        </Button>
        {categories.map((cat) => {
          const config = categoryConfig[cat]
          const Icon = config.icon
          return (
            <Button
              key={cat}
              variant={filter === cat ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter(filter === cat ? null : cat)}
              className={filter === cat ? 'bg-cyan-600 hover:bg-cyan-700' : ''}
            >
              <Icon className={`h-4 w-4 mr-1 ${config.color}`} />
              {config.label}
            </Button>
          )
        })}
      </div>

      {/* Preset Groups */}
      {Object.entries(grouped).map(([category, items]) => {
        const config = categoryConfig[category]
        const CatIcon = config.icon
        return (
          <div key={category} className="space-y-3">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <CatIcon className={`h-5 w-5 ${config.color}`} />
              {config.label}
            </h2>

            <div className="grid gap-3">
              {items.map((preset) => {
                const isExpanded = expandedPreset === preset.id
                const isApplied = preset.applied || !!results[preset.id]
                const isApplying = applying === preset.id
                const isRemoving = removing === preset.id

                return (
                  <div
                    key={preset.id}
                    className="border border-slate-700 rounded-lg bg-slate-800/50 overflow-hidden"
                  >
                    {/* Preset Header */}
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800/80 transition-colors"
                      onClick={() => toggleExpand(preset.id)}
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-white">{preset.name}</span>
                            <Badge
                              variant="outline"
                              className={severityColors[preset.severity] || ''}
                            >
                              {preset.severity}
                            </Badge>
                            {preset.tags.includes('recommended') && (
                              <Badge className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
                                recommended
                              </Badge>
                            )}
                            {isApplied && (
                              <Badge className="bg-green-500/10 text-green-400 border-green-500/20">
                                <Check className="h-3 w-3 mr-1" />
                                Applied
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-slate-400 mt-0.5 truncate">
                            {preset.description}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 ml-4">
                        <span className="text-sm text-slate-500">
                          {preset.rule_count} {preset.rule_count === 1 ? 'rule' : 'rules'}
                        </span>
                        {isApplied ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={isRemoving}
                            onClick={(e) => {
                              e.stopPropagation()
                              removePreset(preset.id)
                            }}
                            className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                          >
                            {isRemoving ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <>
                                <Trash2 className="h-4 w-4 mr-1" />
                                Remove
                              </>
                            )}
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            disabled={isApplying}
                            onClick={(e) => {
                              e.stopPropagation()
                              applyPreset(preset.id)
                            }}
                            className="bg-cyan-600 hover:bg-cyan-700"
                          >
                            {isApplying ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <>
                                <Sparkles className="h-4 w-4 mr-1" />
                                Apply
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Expanded Detail */}
                    {isExpanded && (
                      <div className="border-t border-slate-700 bg-slate-900/50 p-4">
                        {detailLoading ? (
                          <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-5 w-5 animate-spin text-cyan-500" />
                          </div>
                        ) : presetDetail ? (
                          <div className="space-y-3">
                            <p className="text-sm text-slate-300">{presetDetail.description}</p>

                            <div className="text-xs text-slate-500 flex items-center gap-4">
                              <span>Version {presetDetail.version}</span>
                              <span>by {presetDetail.author}</span>
                            </div>

                            {/* Rules Preview */}
                            <div className="space-y-2 mt-3">
                              <h4 className="text-sm font-medium text-slate-300">
                                {presetDetail.rules ? 'Rules' : 'Thresholds'} that will be created:
                              </h4>
                              {(presetDetail.rules || presetDetail.thresholds || []).map(
                                (rule, idx) => (
                                  <div
                                    key={idx}
                                    className="flex items-start gap-2 pl-4 py-1.5 border-l-2 border-slate-700"
                                  >
                                    <Info className="h-3.5 w-3.5 text-slate-500 mt-0.5 shrink-0" />
                                    <div className="text-sm">
                                      <span className="text-slate-200">{rule.name}</span>
                                      {(rule.description || rule.notes) && (
                                        <p className="text-slate-500 text-xs mt-0.5">
                                          {String(rule.description || rule.notes)}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                ),
                              )}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {presets.length === 0 && (
        <div className="text-center text-slate-500 py-12">
          No presets available.
        </div>
      )}
    </div>
  )
}
