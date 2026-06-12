import { memo, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import { useZones } from '@/hooks/queries/use-zones'
import { ZONE_LABELS } from '@/lib/constants'

const WINDOWS: { label: string; hours: number }[] = [
  { label: '24h', hours: 24 },
  { label: '3日', hours: 72 },
  { label: '7日', hours: 168 },
]

const METRICS: { key: string; label: string; color: string; unit: string }[] = [
  { key: 'temperature', label: '温度', color: 'var(--chart-red)', unit: '°C' },
  { key: 'humidity', label: '湿度', color: 'var(--chart-blue)', unit: '%' },
  { key: 'co2', label: 'CO2', color: 'var(--muted-foreground)', unit: 'ppm' },
]

const EnvTrendCard = memo(function EnvTrendCard() {
  const [hours, setHours] = useState(72)
  const [zoneId, setZoneId] = useState<string | undefined>(undefined)
  const { data: zones } = useZones()

  const zoneOptions = zones ?? []

  // Default to first zone with data
  const effectiveZone = zoneId ?? zoneOptions[0]?.zone_id

  if (zoneOptions.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-chart-purple" />
          環境トレンド
          <div className="ml-auto flex gap-1">
            {WINDOWS.map((w) => (
              <Button
                key={w.hours}
                variant={hours === w.hours ? 'default' : 'ghost'}
                size="sm"
                className="h-6 text-[10px] px-2"
                onClick={() => setHours(w.hours)}
              >
                {w.label}
              </Button>
            ))}
          </div>
        </CardTitle>
        {zoneOptions.length > 1 ? (
          <div className="flex flex-wrap gap-1 mt-1">
            {zoneOptions.map((z) => (
              <Button
                key={z.zone_id}
                variant={effectiveZone === z.zone_id ? 'default' : 'outline'}
                size="sm"
                className="h-6 text-[10px] px-2"
                onClick={() => setZoneId(z.zone_id)}
              >
                {ZONE_LABELS[z.zone_id] ?? z.zone_id}
              </Button>
            ))}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {METRICS.map((m) => (
          <TimeSeriesChart
            key={m.key}
            metric={m.key}
            zone={effectiveZone}
            hours={hours}
            label={m.label}
            color={m.color}
            unit={m.unit}
          />
        ))}
      </CardContent>
    </Card>
  )
})

export default EnvTrendCard
