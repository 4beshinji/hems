import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Camera, User, Activity, PersonStanding } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { fetchPerception } from '@/lib/api'
import { ZONE_LABELS, POSTURE_LABELS } from '@/lib/constants'
import { formatDuration } from '@/lib/formatters'
import { activityColor } from '@/lib/color-utils'
import type { PerceptionData } from '@/lib/types'

const PerceptionPanel = memo(function PerceptionPanel() {
  const { data } = useQuery<PerceptionData>({
    queryKey: ['perception'],
    queryFn: fetchPerception,
    refetchInterval: 5000,
  })

  if (!data || data.status === 'no_data' || !data.zones) return null

  const zones = Object.entries(data.zones)
  if (zones.length === 0) return null

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <Camera className="h-4 w-4 text-chart-purple" />
        Perception
      </h3>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {zones.map(([zoneId, z]) => (
          <Card key={zoneId}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{ZONE_LABELS[zoneId] || zoneId}</CardTitle>
                <span className="flex items-center gap-1 text-sm font-bold text-chart-purple">
                  <User className="h-4 w-4" />
                  {z.person_count}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                  <span className="flex items-center gap-1">
                    <Activity className="h-3 w-3" />
                    活動レベル
                  </span>
                  <span>{z.activity_level !== null ? (z.activity_level * 100).toFixed(0) : '—'}%</span>
                </div>
                <Progress
                  value={(z.activity_level ?? 0) * 100}
                  className="h-2"
                  indicatorClassName={activityColor(z.activity_level)}
                />
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <PersonStanding className="h-4 w-4" />
                  {POSTURE_LABELS[z.posture_status] || z.posture_status}
                </span>
                {z.posture_duration_sec > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {formatDuration(z.posture_duration_sec)}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
})

export default PerceptionPanel
