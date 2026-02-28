import { memo } from 'react'
import { Footprints } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import TimeSeriesChart from '@/components/shared/TimeSeriesChart'
import type { BiometricData } from '@/lib/types'

interface Props {
  biometric: BiometricData
}

const ActivityCard = memo(function ActivityCard({ biometric }: Props) {
  const activity = biometric.activity
  if (!activity || activity.steps === 0) return null

  const stepsProgress = Math.min((activity.steps / (activity.steps_goal || 10000)) * 100, 100)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Footprints className="h-4 w-4 text-chart-green" />
          歩数
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="text-2xl font-bold text-chart-green">
          {activity.steps.toLocaleString()}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <Progress
              value={stepsProgress}
              className="flex-1 h-1.5"
              indicatorClassName={stepsProgress >= 100 ? 'bg-success' : 'bg-chart-blue'}
            />
            <span className="text-xs text-muted-foreground">{Math.round(stepsProgress)}%</span>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          目標 {(activity.steps_goal || 10000).toLocaleString()}歩
          {activity.calories > 0 && ` / ${activity.calories}kcal`}
        </div>
        <TimeSeriesChart metric="activity.steps" hours={168} color="var(--chart-green)" compact />
      </CardContent>
    </Card>
  )
})

export default ActivityCard
