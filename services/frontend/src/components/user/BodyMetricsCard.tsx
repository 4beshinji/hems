import { memo } from 'react'
import { Thermometer, MonitorSmartphone } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import type { BiometricData } from '@/lib/types'

interface Props {
  biometric: BiometricData
}

const BodyMetricsCard = memo(function BodyMetricsCard({ biometric }: Props) {
  const bodyTemp = biometric.body_temperature
  const respRate = biometric.respiratory_rate
  const screenTime = biometric.screen_time

  if (!bodyTemp && !respRate && (!screenTime || screenTime.total_minutes === 0)) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Thermometer className="h-4 w-4 text-info" />
          身体指標
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {bodyTemp && (
          <div>
            <span className="text-xs text-muted-foreground">体温 </span>
            <span className={`text-lg font-bold ${
              bodyTemp.celsius > 37.5 ? 'text-destructive' :
              bodyTemp.celsius > 37.0 ? 'text-warning' : 'text-foreground'
            }`}>
              {bodyTemp.celsius.toFixed(1)}
              <span className="text-sm font-normal ml-0.5">°C</span>
            </span>
          </div>
        )}
        {respRate && (
          <div>
            <span className="text-xs text-muted-foreground">呼吸数 </span>
            <span className={`text-lg font-bold ${
              respRate.breaths_per_minute > 25 ? 'text-destructive' : 'text-foreground'
            }`}>
              {respRate.breaths_per_minute}
              <span className="text-sm font-normal ml-0.5">回/分</span>
            </span>
          </div>
        )}
        {screenTime && screenTime.total_minutes > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <MonitorSmartphone className="h-3.5 w-3.5" />
              スクリーンタイム
            </div>
            <span className={`text-lg font-bold ${
              screenTime.total_minutes > 180 ? 'text-destructive' :
              screenTime.total_minutes > 120 ? 'text-warning' : 'text-foreground'
            }`}>
              {Math.floor(screenTime.total_minutes / 60)}h{screenTime.total_minutes % 60}m
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

export default BodyMetricsCard
