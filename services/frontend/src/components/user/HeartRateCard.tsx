import { memo } from 'react'
import { Heart } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import { hrZoneColors, hrZoneLabels } from '@/lib/color-utils'
import type { BiometricData } from '@/lib/types'

interface Props {
  biometric: BiometricData
}

const HeartRateCard = memo(function HeartRateCard({ biometric }: Props) {
  const hr = biometric.heart_rate
  const spo2 = biometric.spo2
  const hrv = biometric.hrv

  if (!hr) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Heart className="h-4 w-4 text-chart-red" />
          心拍数
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className={`text-2xl font-bold ${hrZoneColors[hr.zone] || 'text-foreground'}`}>
          {hr.bpm}
          <span className="text-sm font-normal ml-1">bpm</span>
        </div>
        <div className="text-xs text-muted-foreground">
          {hrZoneLabels[hr.zone] || hr.zone}
          {hr.resting_bpm != null && ` / 安静時${hr.resting_bpm}bpm`}
        </div>
        {spo2 && (
          <div className="text-xs text-muted-foreground">
            SpO2: <span className={spo2.percent < 95 ? 'text-destructive font-bold' : ''}>{spo2.percent}%</span>
          </div>
        )}
        {hrv && (
          <div className="text-xs text-muted-foreground">
            HRV: <span className={hrv.rmssd_ms < 20 ? 'text-destructive font-bold' : hrv.rmssd_ms < 40 ? 'text-warning' : ''}>{hrv.rmssd_ms}ms</span>
          </div>
        )}
        <TimeSeriesChart metric="heart_rate.bpm" hours={24} color="var(--chart-red)" compact />
      </CardContent>
    </Card>
  )
})

export default HeartRateCard
