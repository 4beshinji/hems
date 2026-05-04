import { memo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, ChevronUp, X } from 'lucide-react'
import { fetchWeather } from '@/lib/api'
import type { WeatherAlert, WeatherData } from '@/lib/types'

const SEVERE = new Set(['warning', 'severe', 'extreme', 'critical'])
const CRITICAL = new Set(['extreme', 'critical'])

function severityRank(s: string): number {
  const v = (s || '').toLowerCase()
  if (CRITICAL.has(v)) return 2
  if (SEVERE.has(v)) return 1
  return 0
}

function severityLabel(s: string): string {
  const v = (s || '').toLowerCase()
  if (v === 'critical' || v === 'extreme') return '緊急'
  if (v === 'warning' || v === 'severe') return '警報'
  if (v === 'advisory' || v === 'moderate') return '注意報'
  if (v === 'watch' || v === 'minor') return '情報'
  return '注意'
}

function isAlertActive(alert: WeatherAlert): boolean {
  if (!alert.expires_at) return true
  const expiry = Date.parse(alert.expires_at)
  if (isNaN(expiry)) return true
  return expiry > Date.now()
}

function alertKey(alert: WeatherAlert): string {
  return `${alert.title}|${alert.area}|${alert.issued_at}`
}

const WeatherAlertBanner = memo(function WeatherAlertBanner() {
  const { data } = useQuery<WeatherData>({
    queryKey: ['weather'],
    queryFn: fetchWeather,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const [collapsed, setCollapsed] = useState(false)
  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(new Set())

  const alerts = (data?.alerts ?? [])
    .filter(isAlertActive)
    .filter((a) => SEVERE.has((a.severity || '').toLowerCase()))
    .filter((a) => !dismissedKeys.has(alertKey(a)))
    .sort((a, b) => severityRank(b.severity) - severityRank(a.severity))

  if (alerts.length === 0) return null

  const hasCritical = alerts.some((a) => CRITICAL.has((a.severity || '').toLowerCase()))
  const top = alerts[0]
  const rest = alerts.slice(1)

  const baseColor = hasCritical
    ? 'bg-red-600/95 text-white border-red-700'
    : 'bg-amber-500/95 text-amber-950 border-amber-600'

  return (
    <div
      className={`sticky top-0 z-30 border-b shadow-sm ${baseColor}`}
      role="alert"
      aria-live={hasCritical ? 'assertive' : 'polite'}
    >
      <div className="flex items-start gap-2 px-3 py-2">
        <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-xs uppercase tracking-wide">
              {severityLabel(top.severity)}
            </span>
            <span className="font-semibold truncate">{top.title}</span>
            {top.area ? (
              <span className="text-xs opacity-80">（{top.area}）</span>
            ) : null}
          </div>
          {!collapsed && top.description ? (
            <p className="text-xs mt-1 opacity-90 line-clamp-3">{top.description}</p>
          ) : null}
          {!collapsed && rest.length > 0 ? (
            <ul className="mt-2 space-y-0.5 text-xs">
              {rest.map((a) => (
                <li key={alertKey(a)} className="flex items-center gap-2">
                  <span className="font-bold uppercase opacity-80">
                    {severityLabel(a.severity)}
                  </span>
                  <span className="truncate">{a.title}</span>
                  {a.area ? <span className="opacity-70">（{a.area}）</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {collapsed && rest.length > 0 ? (
            <p className="text-xs mt-1 opacity-80">他 {rest.length} 件の警報</p>
          ) : null}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="p-1 rounded hover:bg-black/10"
            aria-label={collapsed ? '展開' : '折り畳み'}
          >
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </button>
          {!hasCritical ? (
            <button
              type="button"
              onClick={() =>
                setDismissedKeys((prev) => {
                  const next = new Set(prev)
                  alerts.forEach((a) => next.add(alertKey(a)))
                  return next
                })
              }
              className="p-1 rounded hover:bg-black/10"
              aria-label="閉じる"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
})

export default WeatherAlertBanner
