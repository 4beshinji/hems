import { memo } from 'react'
import { Brain } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import { stressCategoryColors, stressCategoryLabels } from '@/lib/color-utils'
import type { BiometricData } from '@/lib/types'

interface Props {
  biometric: BiometricData
}

const StressCard = memo(function StressCard({ biometric }: Props) {
  const stress = biometric.stress
  const fatigue = biometric.fatigue
  if (!stress && !fatigue) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Brain className="h-4 w-4 text-warning" />
          ストレス / 疲労
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {stress && (
          <div>
            <span className={`text-lg font-bold ${stressCategoryColors[stress.category] || 'text-foreground'}`}>
              {stressCategoryLabels[stress.category] || stress.category}
            </span>
            <span className="text-sm text-muted-foreground ml-1">({stress.level})</span>
          </div>
        )}
        {fatigue && fatigue.score > 0 && (
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">疲労度</span>
              <Progress
                value={fatigue.score}
                className="flex-1 h-1.5"
                indicatorClassName={
                  fatigue.score > 70 ? 'bg-destructive' :
                  fatigue.score > 40 ? 'bg-chart-yellow' : 'bg-success'
                }
              />
              <span className="text-xs font-medium text-foreground">{fatigue.score}</span>
            </div>
          </div>
        )}
        <TimeSeriesChart metric="stress.level" hours={24} color="var(--warning)" compact />
      </CardContent>
    </Card>
  )
})

export default StressCard
