import { Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import type { EnergySensor } from '@/lib/types'

interface Props {
  sensors: Record<string, EnergySensor>
}

export default function EnergyPanel({ sensors }: Props) {
  const powerSensors = Object.entries(sensors).filter(
    ([, s]) => s.device_class === 'power',
  )
  const energySensors = Object.entries(sensors).filter(
    ([, s]) => s.device_class === 'energy',
  )

  const totalPower = powerSensors.reduce((sum, [, s]) => sum + s.value, 0)

  const formatName = (entityId: string) => {
    const name = entityId.includes('.') ? entityId.split('.').pop()! : entityId
    return name.replace(/_/g, ' ')
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Zap className="h-4 w-4 text-yellow-500" />
          エネルギー
          {totalPower > 0 && (
            <span className="ml-auto text-lg font-bold text-foreground">
              {totalPower.toFixed(0)}W
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current power readings */}
        {powerSensors.length > 0 && (
          <div className="grid gap-2 grid-cols-2 sm:grid-cols-3">
            {powerSensors.map(([id, s]) => (
              <div key={id} className="rounded-md bg-muted/50 p-2 text-center">
                <p className="text-xs text-muted-foreground truncate">{formatName(id)}</p>
                <p className="text-sm font-semibold">
                  {s.value.toFixed(0)}<span className="text-xs text-muted-foreground ml-0.5">{s.unit}</span>
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Cumulative energy readings */}
        {energySensors.length > 0 && (
          <div className="grid gap-2 grid-cols-2 sm:grid-cols-3">
            {energySensors.map(([id, s]) => (
              <div key={id} className="rounded-md bg-muted/50 p-2 text-center">
                <p className="text-xs text-muted-foreground truncate">{formatName(id)}</p>
                <p className="text-sm font-semibold">
                  {s.value.toFixed(1)}<span className="text-xs text-muted-foreground ml-0.5">{s.unit}</span>
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Historical power chart (total) */}
        {powerSensors.length > 0 && (
          <div>
            <TimeSeriesChart
              metric={`power.${formatName(powerSensors[0][0]).replace(/ /g, '_')}`}
              hours={24}
              label="電力消費 (24h)"
              color="#eab308"
              unit="W"
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
