import { memo } from 'react'
import { Thermometer, Droplets, Wind, Users, Gauge, Sun, Cloudy } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import { ZONE_LABELS } from '@/lib/constants'
import { formatAge } from '@/lib/formatters'
import { co2Level, co2Width, tempColor } from '@/lib/color-utils'
import type { ZoneData } from '@/lib/types'

interface Props {
  zone: ZoneData
}

const ZoneEnvironmentCard = memo(function ZoneEnvironmentCard({ zone }: Props) {
  const env = zone.environment
  const co2Info = co2Level(env.co2)
  const label = ZONE_LABELS[zone.zone_id] || zone.zone_id
  const age = formatAge(env.last_update)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{label}</CardTitle>
          <div className="flex items-center gap-1.5">
            {zone.occupancy.count > 0 && (
              <Badge variant="success" className="gap-0.5">
                <Users className="h-3 w-3" />
                {zone.occupancy.count}
              </Badge>
            )}
            {age && <span className="text-xs text-muted-foreground">{age}</span>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {env.temperature != null && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Thermometer className="h-4 w-4 text-chart-red" />
              温度
            </span>
            <span className={`font-mono font-bold ${tempColor(env.temperature)}`}>
              {env.temperature.toFixed(1)}°C
            </span>
          </div>
        )}

        {env.humidity != null && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Droplets className="h-4 w-4 text-chart-blue" />
              湿度
            </span>
            <span className="font-mono font-bold text-foreground">
              {env.humidity.toFixed(0)}%
            </span>
          </div>
        )}

        {env.co2 != null && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Wind className="h-4 w-4 text-muted-foreground" />
                CO2
              </span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono font-bold text-foreground">
                  {Math.round(env.co2)}ppm
                </span>
                {co2Info.label && (
                  <Badge
                    variant={env.co2 < 800 ? 'success' : env.co2 < 1000 ? 'warning' : 'destructive'}
                  >
                    {co2Info.label}
                  </Badge>
                )}
              </span>
            </div>
            <Progress
              value={co2Width(env.co2)}
              className="h-1.5"
              indicatorClassName={co2Info.color}
            />
          </div>
        )}

        {env.pressure != null && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Gauge className="h-4 w-4 text-chart-purple" />
              気圧
            </span>
            <span className="font-mono font-bold text-foreground">
              {env.pressure.toFixed(0)}hPa
            </span>
          </div>
        )}

        {env.light != null && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Sun className="h-4 w-4 text-chart-yellow" />
              照度
            </span>
            <span className="font-mono font-bold text-foreground">
              {env.light.toFixed(0)}lux
            </span>
          </div>
        )}

        {env.voc != null && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Cloudy className="h-4 w-4 text-info" />
              VOC
            </span>
            <span className="font-mono font-bold text-foreground">
              {env.voc.toFixed(0)}
            </span>
          </div>
        )}

        {/* Sparklines */}
        <div className="mt-2 space-y-1">
          <TimeSeriesChart metric="temperature" zone={zone.zone_id} hours={6} color="var(--chart-red)" compact />
          <TimeSeriesChart metric="co2" zone={zone.zone_id} hours={6} color="var(--muted-foreground)" compact />
          <TimeSeriesChart metric="humidity" zone={zone.zone_id} hours={6} color="var(--chart-blue)" compact />
        </div>
      </CardContent>
    </Card>
  )
})

export default ZoneEnvironmentCard
