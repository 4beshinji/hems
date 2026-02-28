import { memo } from 'react'
import { Moon } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatSleepDuration } from '@/lib/formatters'
import type { BiometricData } from '@/lib/types'

interface Props {
  biometric: BiometricData
}

const SleepCard = memo(function SleepCard({ biometric }: Props) {
  const sleep = biometric.sleep
  if (!sleep || sleep.duration_minutes === 0) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Moon className="h-4 w-4 text-chart-purple" />
          睡眠
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-2xl font-bold text-chart-purple">
          {formatSleepDuration(sleep.duration_minutes)}
        </div>
        {sleep.quality_score > 0 && (
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">品質</span>
              <Progress
                value={sleep.quality_score}
                className="flex-1 h-1.5"
                indicatorClassName={
                  sleep.quality_score >= 70 ? 'bg-success' :
                  sleep.quality_score >= 50 ? 'bg-chart-yellow' : 'bg-destructive'
                }
              />
              <span className="text-xs font-medium text-foreground">{sleep.quality_score}</span>
            </div>
          </div>
        )}
        <div className="flex gap-3 text-xs text-muted-foreground">
          {sleep.deep_minutes > 0 && <span>深い {sleep.deep_minutes}m</span>}
          {sleep.rem_minutes > 0 && <span>REM {sleep.rem_minutes}m</span>}
          {sleep.light_minutes > 0 && <span>浅い {sleep.light_minutes}m</span>}
        </div>
      </CardContent>
    </Card>
  )
})

export default SleepCard
