import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Camera, AlertTriangle, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchPerception } from '@/lib/api'
import { ZONE_LABELS } from '@/lib/constants'
import type { PerceptionZone, SceneSnapshot } from '@/lib/types'

function formatAge(ts?: number | null): string {
  if (!ts) return ''
  const ageSec = Date.now() / 1000 - ts
  if (ageSec < 60) return `${Math.floor(ageSec)}秒前`
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)}分前`
  return `${Math.floor(ageSec / 3600)}時間前`
}

function HistoryRow({ snap }: { snap: SceneSnapshot }) {
  return (
    <div className="text-[11px] py-1 border-t border-border/50 first:border-t-0">
      <div className="flex items-center gap-1.5 text-muted-foreground mb-0.5">
        <Clock className="h-2.5 w-2.5" />
        <span>{formatAge(snap.timestamp)}</span>
        {snap.tier ? <span className="text-[10px] opacity-70">[{snap.tier}]</span> : null}
        {snap.anomalies?.length ? (
          <Badge variant="warning" className="ml-auto text-[9px] px-1 py-0">
            異常
          </Badge>
        ) : null}
      </div>
      <p className="text-foreground line-clamp-2 leading-snug">{snap.description || '(説明なし)'}</p>
      {snap.objects?.length ? (
        <p className="text-[10px] text-muted-foreground mt-0.5">
          物体: {snap.objects.slice(0, 6).join(', ')}
        </p>
      ) : null}
    </div>
  )
}

function ZoneVLM({ zoneId, zone }: { zoneId: string; zone: PerceptionZone }) {
  const label = ZONE_LABELS[zoneId] ?? zoneId
  const history = zone.vlm_history ?? []
  const recent = history.slice(-5).reverse()

  if (!zone.scene_description && recent.length === 0) return null

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">{label}</span>
        {zone.vlm_last_update ? (
          <span className="text-[10px] text-muted-foreground">
            {formatAge(zone.vlm_last_update)}
          </span>
        ) : null}
        {zone.scene_anomalies?.length ? (
          <Badge variant="warning" className="text-[10px] px-1.5 py-0 gap-1">
            <AlertTriangle className="h-2.5 w-2.5" />
            {zone.scene_anomalies.length}
          </Badge>
        ) : null}
      </div>

      {zone.scene_description ? (
        <p className="text-xs text-foreground bg-muted/30 p-2 rounded leading-snug">
          {zone.scene_description}
        </p>
      ) : null}

      {zone.scene_objects?.length ? (
        <div className="flex flex-wrap gap-1">
          {zone.scene_objects.slice(0, 8).map((obj) => (
            <Badge key={obj} variant="secondary" className="text-[10px] px-1.5 py-0 font-normal">
              {obj}
            </Badge>
          ))}
        </div>
      ) : null}

      {recent.length > 1 ? (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            履歴 ({recent.length})
          </summary>
          <div className="mt-1 space-y-0.5 max-h-48 overflow-y-auto pr-1">
            {recent.map((snap, i) => (
              <HistoryRow key={`${snap.timestamp}-${i}`} snap={snap} />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}

const VLMSceneCard = memo(function VLMSceneCard() {
  const { data: perception } = useQuery({
    queryKey: ['perception'],
    queryFn: fetchPerception,
    refetchInterval: 30_000,
  })

  const zones = perception?.zones ?? {}
  const vlmZones = Object.entries(zones).filter(
    ([, z]) => (z.scene_description?.length ?? 0) > 0 || (z.vlm_history?.length ?? 0) > 0,
  )

  if (vlmZones.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Camera className="h-4 w-4 text-chart-purple" />
          VLM シーン解析
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {vlmZones.map(([zoneId, zone]) => (
          <ZoneVLM key={zoneId} zoneId={zoneId} zone={zone} />
        ))}
      </CardContent>
    </Card>
  )
})

export default VLMSceneCard
