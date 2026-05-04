import { memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Power, Lightbulb, Snowflake, Activity, CircleAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchDeviceActions } from '@/lib/api'

function actionIcon(action: string) {
  const a = action.toLowerCase()
  if (a.includes('brightness') || a.includes('light') || a === 'on' || a === 'off') return Lightbulb
  if (a.includes('temperature') || a.includes('climate')) return Snowflake
  if (a.includes('pulse') || a.includes('toggle')) return Activity
  return Power
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const ageMs = Date.now() - d.getTime()
  if (ageMs < 60_000) return `${Math.floor(ageMs / 1000)}秒前`
  if (ageMs < 3_600_000) return `${Math.floor(ageMs / 60_000)}分前`
  if (ageMs < 86_400_000) return `${Math.floor(ageMs / 3_600_000)}時間前`
  return d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const DeviceTimelineCard = memo(function DeviceTimelineCard() {
  const { data } = useQuery({
    queryKey: ['device-actions', 24],
    queryFn: () => fetchDeviceActions({ hours: 24, limit: 50 }),
    refetchInterval: 30_000,
  })

  const actions = data?.actions ?? []
  if (actions.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Power className="h-4 w-4 text-chart-blue" />
          デバイス操作履歴 (24h)
          <span className="text-[10px] text-muted-foreground font-normal ml-auto">
            {actions.length} 件
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-72 overflow-y-auto">
        <ul className="space-y-1">
          {actions.map((a) => {
            const Icon = actionIcon(a.action)
            return (
              <li key={a.id} className="flex items-center gap-2 text-xs py-1 border-b border-border/50 last:border-b-0">
                <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{a.device_id}</span>
                    {!a.success ? (
                      <Badge variant="destructive" className="text-[9px] px-1 py-0 gap-0.5">
                        <CircleAlert className="h-2.5 w-2.5" />
                        失敗
                      </Badge>
                    ) : null}
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    {a.action}
                    {a.params && Object.keys(a.params).length > 0
                      ? ` (${Object.entries(a.params).map(([k, v]) => `${k}=${v}`).join(', ')})`
                      : ''}
                    {a.source ? ` · ${a.source}` : ''}
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(a.timestamp)}</span>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
})

export default DeviceTimelineCard
