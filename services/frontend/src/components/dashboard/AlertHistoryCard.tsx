import { memo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { FeedbackButtons } from '@/components/feedback/FeedbackButtons'
import { fetchAlertHistory } from '@/lib/api'

const WINDOWS: { label: string; hours: number }[] = [
  { label: '24h', hours: 24 },
  { label: '7日', hours: 168 },
  { label: '30日', hours: 720 },
]

function formatTime(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const AlertHistoryCard = memo(function AlertHistoryCard() {
  const [hours, setHours] = useState(24)
  const { data } = useQuery({
    queryKey: ['alerts', hours],
    queryFn: () => fetchAlertHistory(hours),
    refetchInterval: 60_000,
  })

  const alerts = data ?? []
  if (alerts.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            アラート履歴
            <div className="ml-auto flex gap-1">
              {WINDOWS.map((w) => (
                <Button
                  key={w.hours}
                  variant={hours === w.hours ? 'default' : 'ghost'}
                  size="sm"
                  className="h-6 text-[10px] px-2"
                  onClick={() => setHours(w.hours)}
                >
                  {w.label}
                </Button>
              ))}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">アラートはありません</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          アラート履歴
          <span className="text-[10px] text-muted-foreground font-normal">({alerts.length})</span>
          <div className="ml-auto flex gap-1">
            {WINDOWS.map((w) => (
              <Button
                key={w.hours}
                variant={hours === w.hours ? 'default' : 'ghost'}
                size="sm"
                className="h-6 text-[10px] px-2"
                onClick={() => setHours(w.hours)}
              >
                {w.label}
              </Button>
            ))}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-72 overflow-y-auto">
        <ul className="space-y-1">
          {alerts.map((a) => (
            <li
              key={a.id}
              className="text-xs py-1 border-b border-border/50 last:border-b-0 flex gap-2"
            >
              <AlertCircle className="h-3 w-3 mt-0.5 text-amber-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-foreground line-clamp-2">{a.message}</p>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] text-muted-foreground">
                    {a.zone ? `${a.zone} · ` : ''}
                    {formatTime(a.created_at)}
                  </p>
                  <FeedbackButtons targetType="voice" targetId={String(a.id)} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
})

export default AlertHistoryCard
