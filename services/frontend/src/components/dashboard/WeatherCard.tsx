import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CloudRain, Cloud, Sun, CloudSnow, CloudFog, Wind, Droplets, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchWeather } from '@/lib/api'
import type { WeatherData, WeatherForecast } from '@/lib/types'

const SEVERE = new Set(['warning', 'severe', 'extreme', 'critical'])

function conditionIcon(condition: string) {
  const c = (condition || '').toLowerCase()
  if (c.includes('rain') || c.includes('雨')) return CloudRain
  if (c.includes('snow') || c.includes('雪')) return CloudSnow
  if (c.includes('fog') || c.includes('霧')) return CloudFog
  if (c.includes('cloud') || c.includes('曇')) return Cloud
  return Sun
}

function formatTime(dt: string): string {
  const d = new Date(dt)
  if (isNaN(d.getTime())) return dt.slice(11, 16) || dt
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function ForecastRow({ f }: { f: WeatherForecast }) {
  const Icon = conditionIcon(f.condition)
  return (
    <div className="flex items-center gap-2 text-xs py-1">
      <span className="w-12 text-muted-foreground">{formatTime(f.datetime)}</span>
      <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <span className="text-foreground tabular-nums">{Math.round(f.temperature)}°C</span>
      {f.precipitation_probability > 0 ? (
        <span className="ml-auto text-blue-500 tabular-nums">{f.precipitation_probability}%</span>
      ) : null}
    </div>
  )
}

const WeatherCard = memo(function WeatherCard() {
  const { data } = useQuery<WeatherData>({
    queryKey: ['weather'],
    queryFn: fetchWeather,
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  })

  if (!data || data.status === 'no_data' || !data.current) {
    return null
  }

  const { current, forecast = [], alerts = [] } = data
  const Icon = conditionIcon(current.condition)
  const severeAlerts = (alerts || []).filter((a) => SEVERE.has((a.severity || '').toLowerCase()))
  const next6 = (forecast || []).slice(0, 6)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Icon className="h-4 w-4 text-chart-blue" />
          <span>天気</span>
          {current.condition ? (
            <span className="text-xs text-muted-foreground font-normal">{current.condition}</span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-baseline gap-3">
          <span className="text-3xl font-semibold tabular-nums">
            {Math.round(current.temperature)}°
          </span>
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Droplets className="h-3 w-3" />
            {Math.round(current.humidity)}%
          </span>
          {current.wind_speed > 0 ? (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Wind className="h-3 w-3" />
              {current.wind_speed.toFixed(1)}m/s
            </span>
          ) : null}
        </div>

        {next6.length > 0 ? (
          <div className="border-t pt-1">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">次の予報</p>
            {next6.map((f, i) => (
              <ForecastRow key={`${f.datetime}-${i}`} f={f} />
            ))}
          </div>
        ) : null}

        {severeAlerts.length > 0 ? (
          <div className="border-t pt-1">
            <p className="text-[10px] text-amber-600 dark:text-amber-400 uppercase tracking-wide mb-1 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              気象警報 ({severeAlerts.length})
            </p>
            {severeAlerts.slice(0, 3).map((a, i) => (
              <p key={i} className="text-xs text-amber-700 dark:text-amber-300 truncate">
                {a.title}
                {a.area ? `（${a.area}）` : ''}
              </p>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
})

export default WeatherCard
