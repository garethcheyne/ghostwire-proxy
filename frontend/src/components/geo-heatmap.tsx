'use client'

import { useEffect, useState } from 'react'
import { Globe } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import api from '@/lib/api'

interface GeoData {
  country_code: string
  country_name: string
  count: number
}

// Country centroids (lat, lng) for the most common countries
const COUNTRY_COORDS: Record<string, [number, number]> = {
  AF:[33,65],AL:[41,20],DZ:[28,3],AD:[42.5,1.5],AO:[-12.5,18.5],AG:[17.05,-61.8],
  AR:[-34,-64],AM:[40,45],AU:[-27,133],AT:[47.3,13.3],AZ:[40.5,47.5],BS:[24.25,-76],
  BH:[26,50.5],BD:[24,90],BB:[13.2,-59.5],BY:[53,28],BE:[50.8,4],BZ:[17.2,-88.7],
  BJ:[9.5,2.2],BT:[27.5,90.5],BO:[-17,-65],BA:[44,18],BW:[-22,24],BR:[-10,-55],
  BN:[4.5,114.7],BG:[43,25],BF:[13,-2],BI:[-3.5,30],KH:[13,105],CM:[6,12],
  CA:[60,-95],CV:[16,-24],CF:[7,21],TD:[15,19],CL:[-30,-71],CN:[35,105],
  CO:[4,-72],KM:[-12.2,44.2],CG:[-1,15],CD:[-3,23],CR:[10,-84],CI:[8,-5],
  HR:[45.2,15.5],CU:[21.5,-80],CY:[35,33],CZ:[49.8,15.5],DK:[56,10],
  DJ:[11.5,43],DM:[15.4,-61.4],DO:[19,-70.7],EC:[-2,-77.5],EG:[27,30],
  SV:[13.8,-88.9],GQ:[2,10],ER:[15,39],EE:[59,26],ET:[8,38],FJ:[-18,175],
  FI:[64,26],FR:[46,2],GA:[-1,11.7],GM:[13.5,-16.5],GE:[42,43.5],DE:[51,9],
  GH:[8,-2],GR:[39,22],GD:[12.1,-61.7],GT:[15.5,-90.2],GN:[11,-10],GW:[12,-15],
  GY:[5,-59],HT:[19,-72.4],HN:[15,-86.5],HU:[47,20],IS:[65,-18],IN:[20,77],
  ID:[-5,120],IR:[32,53],IQ:[33,44],IE:[53,-8],IL:[31.5,34.8],IT:[42.8,12.8],
  JM:[18.2,-77.5],JP:[36,138],JO:[31,36],KZ:[48,68],KE:[1,38],KI:[1.4,173],
  KP:[40,127],KR:[37,127.5],KW:[29.5,45.7],KG:[41,75],LA:[18,105],LV:[57,25],
  LB:[33.8,35.8],LS:[-29.5,28.5],LR:[6.5,-9.5],LY:[25,17],LI:[47.2,9.5],
  LT:[56,24],LU:[49.7,6.2],MK:[41.5,22],MG:[-20,47],MW:[-13.5,34],MY:[2.5,112.5],
  MV:[3.2,73],ML:[17,-4],MT:[35.9,14.4],MH:[9,168],MR:[20,-12],MU:[-20.3,57.6],
  MX:[23,-102],FM:[6.9,158.2],MD:[47,29],MC:[43.7,7.4],MN:[46,105],ME:[42.5,19.3],
  MA:[32,-5],MZ:[-18.2,35],MM:[22,98],NA:[-22,17],NR:[-0.5,166.9],NP:[28,84],
  NL:[52.5,5.7],NZ:[-41,174],NI:[13,-85],NE:[16,8],NG:[10,8],NO:[62,10],
  OM:[21,57],PK:[30,70],PW:[7.5,134.5],PA:[9,-80],PG:[-6,147],PY:[-23,-58],
  PE:[-10,-76],PH:[13,122],PL:[52,20],PT:[39.5,-8],QA:[25.5,51.2],RO:[46,25],
  RU:[60,100],RW:[-2,30],KN:[17.3,-62.7],LC:[13.9,-61],VC:[13.2,-61.2],
  WS:[-13.6,-172.3],SM:[43.8,12.4],ST:[1,7],SA:[25,45],SN:[14,-14],RS:[44,21],
  SC:[-4.7,55.5],SL:[8.5,-11.5],SG:[1.4,103.8],SK:[48.7,19.5],SI:[46.1,14.8],
  SB:[-8,159],SO:[10,49],ZA:[-29,24],SS:[7,30],ES:[40,-4],LK:[7,81],
  SD:[15,30],SR:[4,-56],SZ:[-26.5,31.5],SE:[62,15],CH:[47,8],SY:[35,38],
  TW:[23.5,121],TJ:[39,71],TZ:[-6,35],TH:[15,100],TL:[-8.8,126],TG:[8,1.2],
  TO:[-20,-175],TT:[11,-61],TN:[34,9],TR:[39,35],TM:[40,60],TV:[-8,178],
  UG:[1,32],UA:[49,32],AE:[24,54],GB:[54,-2],US:[38,-97],UY:[-33,-56],
  UZ:[41,64],VU:[-16,167],VE:[8,-66],VN:[16,106],YE:[15,48],ZM:[-15,30],
  ZW:[-20,30],XK:[42.6,21],HK:[22.3,114.2],MO:[22.2,113.5],PS:[32,35.2],
}

function MapContent({ data, threatData }: { data: GeoData[]; threatData: GeoData[] }) {
  const [L, setL] = useState<typeof import('leaflet') | null>(null)
  const [RL, setRL] = useState<typeof import('react-leaflet') | null>(null)

  useEffect(() => {
    // Dynamic import to avoid SSR issues
    Promise.all([
      import('leaflet'),
      import('react-leaflet'),
    ]).then(([leaflet, reactLeaflet]) => {
      setL(leaflet)
      setRL(reactLeaflet)
    })
  }, [])

  if (!L || !RL) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Loading map...
      </div>
    )
  }

  const { MapContainer, TileLayer, CircleMarker, Tooltip } = RL
  const maxCount = Math.max(...data.map(d => d.count), 1)
  const maxThreatCount = Math.max(...threatData.map(d => d.count), 1)

  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      minZoom={2}
      maxZoom={6}
      style={{ height: '100%', width: '100%', borderRadius: '0.75rem' }}
      scrollWheelZoom={true}
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {/* Traffic circles (cyan) */}
      {data.map((item) => {
        const coords = COUNTRY_COORDS[item.country_code]
        if (!coords) return null
        const intensity = item.count / maxCount
        const radius = Math.max(6, Math.min(35, 6 + intensity * 29))
        return (
          <CircleMarker
            key={`traffic-${item.country_code}`}
            center={coords}
            radius={radius}
            pathOptions={{
              fillColor: `rgba(6, 182, 212, ${0.3 + intensity * 0.5})`,
              color: 'rgb(6, 182, 212)',
              weight: 1,
              fillOpacity: 0.3 + intensity * 0.5,
            }}
          >
            <Tooltip sticky>
              <div className="text-sm font-medium">
                {countryFlag(item.country_code)} {item.country_name}
              </div>
              <div className="text-xs text-muted-foreground">
                {item.count.toLocaleString()} requests
              </div>
            </Tooltip>
          </CircleMarker>
        )
      })}
      {/* Threat circles (red) */}
      {threatData.map((item) => {
        const coords = COUNTRY_COORDS[item.country_code]
        if (!coords) return null
        const intensity = item.count / maxThreatCount
        const radius = Math.max(5, Math.min(30, 5 + intensity * 25))
        // Offset slightly so both circles are visible
        const offsetCoords: [number, number] = [coords[0] + 1.5, coords[1] + 1.5]
        return (
          <CircleMarker
            key={`threat-${item.country_code}`}
            center={offsetCoords}
            radius={radius}
            pathOptions={{
              fillColor: `rgba(239, 68, 68, ${0.4 + intensity * 0.5})`,
              color: 'rgb(239, 68, 68)',
              weight: 1.5,
              fillOpacity: 0.4 + intensity * 0.5,
            }}
          >
            <Tooltip sticky>
              <div className="text-sm font-medium">
                {countryFlag(item.country_code)} {item.country_name}
              </div>
              <div className="text-xs" style={{ color: 'rgb(239, 68, 68)' }}>
                {item.count.toLocaleString()} threats
              </div>
            </Tooltip>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}

function countryFlag(code: string): string {
  if (!code || code.length !== 2) return ''
  const codePoints = code.toUpperCase().split('').map(c => 127397 + c.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}

export default function GeoHeatmap({
  proxyHostId,
  days = 30,
  showThreats = false,
}: {
  proxyHostId?: string
  days?: number
  showThreats?: boolean
}) {
  const [data, setData] = useState<GeoData[]>([])
  const [threatData, setThreatData] = useState<GeoData[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const params = new URLSearchParams()
    params.set('days', String(days))
    if (proxyHostId) params.set('proxy_host_id', proxyHostId)

    const fetches: Promise<void>[] = [
      api.get(`/api/traffic/geo/heatmap?${params}`)
        .then(res => setData(res.data))
        .catch(err => console.error('Failed to load geo data:', err)),
    ]

    if (showThreats) {
      fetches.push(
        api.get(`/api/waf/threats/geo?days=${days}`)
          .then(res => setThreatData(res.data))
          .catch(err => console.error('Failed to load threat geo data:', err))
      )
    }

    Promise.all(fetches).finally(() => setIsLoading(false))
  }, [proxyHostId, days, showThreats])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[400px] text-muted-foreground text-sm">
        Loading geographic data...
      </div>
    )
  }

  if (data.length === 0 && threatData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[400px] text-muted-foreground">
        <Globe className="h-12 w-12 mb-3 opacity-30" />
        <p className="text-sm">No geographic data available yet</p>
        <p className="text-xs mt-1">Traffic country data will appear as requests come in</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="h-[400px] rounded-xl overflow-hidden border border-border relative">
        <MapContent data={data} threatData={threatData} />
        {/* Legend */}
        {threatData.length > 0 && (
          <div className="absolute bottom-3 left-3 z-[1000] flex gap-3 rounded-lg bg-card/90 backdrop-blur border border-border px-3 py-2 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: 'rgb(6, 182, 212)' }} />
              Traffic
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: 'rgb(239, 68, 68)' }} />
              Threats
            </div>
          </div>
        )}
      </div>
      {/* Top countries list */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {data.slice(0, 12).map((item) => (
          <div
            key={item.country_code}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2"
          >
            <span className="text-lg">{countryFlag(item.country_code)}</span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium truncate">{item.country_name}</p>
              <p className="text-xs text-cyan-400">{item.count.toLocaleString()} requests</p>
            </div>
          </div>
        ))}
      </div>
      {/* Threat countries list */}
      {threatData.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-red-400 mb-2">Threat Origins</h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {threatData.slice(0, 12).map((item) => (
              <div
                key={item.country_code}
                className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2"
              >
                <span className="text-lg">{countryFlag(item.country_code)}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium truncate">{item.country_name}</p>
                  <p className="text-xs text-red-400">{item.count.toLocaleString()} threats</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
