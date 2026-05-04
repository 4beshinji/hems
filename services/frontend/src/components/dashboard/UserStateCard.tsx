import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Eye, EyeOff, Activity, Moon, Coffee, MonitorSmartphone, Heart, Camera, DoorOpen, Footprints, Thermometer, Wind } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchPerception, fetchBiometric } from '@/lib/api'
import { ZONE_LABELS } from '@/lib/constants'
import type { InferenceSource, PerceptionZone, BiometricData } from '@/lib/types'

const SOURCE_LABEL: Record<InferenceSource, string> = {
  camera: 'カメラ',
  presence_sensor: '人感センサー',
  motion: 'モーション',
  pc_activity: 'PC作業',
  biometric: '生体',
  none: 'なし',
}

const SOURCE_ICON: Record<InferenceSource, React.ComponentType<{ className?: string }>> = {
  camera: Camera,
  presence_sensor: DoorOpen,
  motion: Footprints,
  pc_activity: MonitorSmartphone,
  biometric: Heart,
  none: EyeOff,
}

const POSTURE_LABEL: Record<string, string> = {
  standing: '立位',
  sitting: '座位',
  lying: '横臥',
  walking: '歩行',
  unknown: '—',
}

const ACTIVITY_LABEL: Record<string, string> = {
  idle: '静止',
  low: '微動',
  moderate: '活動',
  high: '激しい',
  unknown: '—',
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const m = Math.floor(seconds / 60)
  if (m < 1) return `${Math.floor(seconds)}秒`
  if (m < 60) return `${m}分`
  const h = Math.floor(m / 60)
  return `${h}時間${m % 60}分`
}

/**
 * Derive a human-readable user state label from perception + biometric data.
 * Order of precedence reflects what the brain actually uses.
 */
function deriveStateLabel(zone: PerceptionZone | undefined, bio: BiometricData | undefined): {
  label: string
  tone: 'default' | 'info' | 'warning' | 'secondary'
} {
  // Sleep takes priority (biometric)
  const sleepStage = bio?.sleep?.stage
  if (sleepStage && ['light', 'deep', 'rem'].includes(sleepStage)) {
    return { label: '就寝中', tone: 'info' }
  }

  if (!zone || !zone.inferred_occupied) {
    return { label: '不在', tone: 'secondary' }
  }

  // Posture-based
  if (zone.posture === 'lying') return { label: '横になっている', tone: 'info' }
  if (zone.posture === 'walking') return { label: '移動中', tone: 'default' }

  // PC work
  const sources = zone.inference_sources ?? []
  if (sources.includes('pc_activity') && (zone.posture === 'sitting' || !zone.posture)) {
    return { label: '作業中', tone: 'default' }
  }

  // Activity intensity
  if (zone.activity_class === 'high' || zone.activity_class === 'moderate') {
    return { label: '活動中', tone: 'default' }
  }

  if (zone.posture === 'sitting') {
    return { label: '在室・着席', tone: 'default' }
  }
  if (zone.posture === 'standing') {
    return { label: '在室・立位', tone: 'default' }
  }

  return { label: '在室', tone: 'default' }
}

const UserStateCard = memo(function UserStateCard() {
  const { data: perception } = useQuery({
    queryKey: ['perception'],
    queryFn: fetchPerception,
    refetchInterval: 5000,
  })
  const { data: bio } = useQuery({
    queryKey: ['biometric'],
    queryFn: fetchBiometric,
    refetchInterval: 10000,
  })

  const zones = perception?.zones ?? {}
  const zoneEntries = Object.entries(zones)

  // Pick the zone with strongest signal (any inferred presence wins)
  const primary = zoneEntries.find(([, z]) => z.inferred_occupied) ?? zoneEntries[0]
  const [primaryZoneId, primaryZone] = primary ?? [undefined, undefined]

  const state = deriveStateLabel(primaryZone, bio)
  const sources = primaryZone?.inference_sources ?? []
  const occupied = primaryZone?.inferred_occupied ?? false

  const hr = bio?.heart_rate?.bpm
  const stress = bio?.stress?.score ?? bio?.stress?.level
  const fatigue = bio?.fatigue?.score
  const bodyTemp = bio?.body_temperature?.celsius
  const respRate = bio?.respiratory_rate?.breaths_per_minute

  const postureDuration = primaryZone?.posture_duration_sec ?? 0
  const postureLabel = primaryZone?.posture ? POSTURE_LABEL[primaryZone.posture] ?? primaryZone.posture : null
  const activityLabel = primaryZone?.activity_class
    ? ACTIVITY_LABEL[primaryZone.activity_class] ?? primaryZone.activity_class
    : null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {occupied ? (
            <Eye className="h-4 w-4 text-primary" />
          ) : (
            <EyeOff className="h-4 w-4 text-muted-foreground" />
          )}
          <span>ユーザー認識状態</span>
          {primaryZoneId && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 ml-auto font-normal">
              {ZONE_LABELS[primaryZoneId] ?? primaryZoneId}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pb-3 space-y-2">
        {zoneEntries.length === 0 ? (
          <p className="text-xs text-muted-foreground">認識データなし</p>
        ) : (
          <>
            {/* Primary state line */}
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-semibold">{state.label}</span>
              {postureLabel && postureLabel !== '—' && (
                <span className="text-xs text-muted-foreground">
                  {postureLabel}
                  {postureDuration > 30 && ` ${formatDuration(postureDuration)}`}
                </span>
              )}
            </div>

            {/* Inference sources */}
            <div className="flex flex-wrap gap-1">
              {sources.length === 0 && (
                <span className="text-[10px] text-muted-foreground">推定ソース: なし</span>
              )}
              {sources.map((src) => {
                const Icon = SOURCE_ICON[src] ?? Activity
                return (
                  <Badge key={src} variant="secondary" className="text-[10px] px-1.5 py-0 gap-1 font-normal">
                    <Icon className="h-2.5 w-2.5" />
                    {SOURCE_LABEL[src] ?? src}
                  </Badge>
                )
              })}
            </div>

            {/* Secondary indicators */}
            {(hr != null || activityLabel || stress != null || fatigue != null || bodyTemp != null || respRate != null) && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] pt-1 border-t border-border">
                {hr != null && (
                  <div className="flex items-center gap-1">
                    <Heart className="h-3 w-3 text-chart-red" />
                    <span className="text-muted-foreground">HR</span>
                    <span className="ml-auto font-medium">{hr} bpm</span>
                  </div>
                )}
                {activityLabel && activityLabel !== '—' && (
                  <div className="flex items-center gap-1">
                    <Activity className="h-3 w-3 text-chart-blue" />
                    <span className="text-muted-foreground">動き</span>
                    <span className="ml-auto font-medium">{activityLabel}</span>
                  </div>
                )}
                {stress != null && (
                  <div className="flex items-center gap-1">
                    <Coffee className="h-3 w-3 text-chart-yellow" />
                    <span className="text-muted-foreground">ストレス</span>
                    <span className="ml-auto font-medium">{stress}</span>
                  </div>
                )}
                {fatigue != null && (
                  <div className="flex items-center gap-1">
                    <Moon className="h-3 w-3 text-chart-purple" />
                    <span className="text-muted-foreground">疲労</span>
                    <span className="ml-auto font-medium">{fatigue}</span>
                  </div>
                )}
                {bodyTemp != null && (
                  <div className="flex items-center gap-1">
                    <Thermometer className="h-3 w-3 text-chart-orange" />
                    <span className="text-muted-foreground">体温</span>
                    <span className="ml-auto font-medium">{bodyTemp.toFixed(1)}°C</span>
                  </div>
                )}
                {respRate != null && (
                  <div className="flex items-center gap-1">
                    <Wind className="h-3 w-3 text-chart-blue" />
                    <span className="text-muted-foreground">呼吸</span>
                    <span className="ml-auto font-medium">{respRate}/分</span>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
})

export default UserStateCard
