import { memo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Newspaper, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchNews } from '@/lib/api'
import type { NewsData } from '@/lib/types'

function formatTime(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return ''
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function isRecent(ts?: number, withinSec = 3600): boolean {
  if (!ts) return false
  return Date.now() / 1000 - ts < withinSec
}

const NewsBanner = memo(function NewsBanner() {
  const { data } = useQuery<NewsData>({
    queryKey: ['news'],
    queryFn: fetchNews,
    refetchInterval: 5 * 60_000,
    staleTime: 60_000,
  })
  const [dailyExpanded, setDailyExpanded] = useState(false)

  if (!data || data.status === 'no_data') return null

  const urgent = (data.urgent_articles || []).filter((a) => isRecent(a.timestamp, 7200))
  const dailyChunks = data.daily_chunks || []
  const hasContent = urgent.length > 0 || dailyChunks.length > 0
  if (!hasContent) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-chart-blue" />
          ニュース
          {urgent.length > 0 ? (
            <span className="text-xs text-amber-600 dark:text-amber-400 font-normal">
              速報 {urgent.length} 件
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {urgent.length > 0 ? (
          <div className="space-y-1.5">
            {urgent.slice(0, 5).map((a, i) => (
              <div key={i} className="flex items-start gap-2 p-2 rounded-md bg-amber-50 dark:bg-amber-950/30">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 text-amber-600 dark:text-amber-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{a.title || '(無題)'}</p>
                  {a.summary ? (
                    <p className="text-[11px] text-muted-foreground line-clamp-2">{a.summary}</p>
                  ) : null}
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {a.source ? `${a.source} ` : ''}
                    {formatTime(a.timestamp)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {dailyChunks.length > 0 ? (
          <div className="border-t pt-2">
            <button
              type="button"
              onClick={() => setDailyExpanded((v) => !v)}
              className="flex items-center justify-between w-full text-xs text-muted-foreground hover:text-foreground"
            >
              <span>
                日次サマリ ({dailyChunks.length}項目)
                {data.daily_timestamp ? ` ・ ${formatTime(data.daily_timestamp)}` : ''}
              </span>
              {dailyExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
            {dailyExpanded ? (
              <div className="mt-2 space-y-1.5 max-h-72 overflow-y-auto">
                {dailyChunks.map((c, i) => (
                  <p key={i} className="text-[11px] text-foreground leading-relaxed">
                    {c}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
})

export default NewsBanner
