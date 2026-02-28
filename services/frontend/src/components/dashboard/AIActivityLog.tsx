import { useRef, useEffect, useState, memo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchVoiceEvents } from '@/lib/api'
import { ZONE_LABELS } from '@/lib/constants'
import type { VoiceEvent } from '@/lib/types'

const TONE_VARIANTS: Record<string, 'secondary' | 'info' | 'warning' | 'destructive'> = {
  neutral: 'secondary',
  caring: 'info',
  humorous: 'warning',
  alert: 'destructive',
}

function EventRow({ event }: { event: VoiceEvent }) {
  const variant = TONE_VARIANTS[event.tone] ?? 'secondary'
  const time = event.created_at
    ? new Date(event.created_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : ''

  return (
    <div className="flex gap-3 py-2.5 border-b border-border last:border-0">
      <span className="text-[11px] text-muted-foreground font-mono shrink-0 pt-0.5 w-16">
        {time}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {event.character_name && (
            <span className="text-xs font-medium text-primary">{event.character_name}</span>
          )}
          <Badge variant={variant} className="text-[10px] px-1.5 py-0">
            {event.tone}
          </Badge>
          {event.zone && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {ZONE_LABELS[event.zone] ?? event.zone}
            </Badge>
          )}
        </div>
        <p className="text-sm text-foreground">{event.message}</p>
      </div>
    </div>
  )
}

const AIActivityLog = memo(function AIActivityLog() {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  const { data: events } = useQuery({
    queryKey: ['voiceEvents'],
    queryFn: fetchVoiceEvents,
    refetchInterval: 3000,
  })

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events, autoScroll])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  return (
    <Card className="flex flex-col h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-primary" />
          AI Activity Log
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-full max-h-[500px] overflow-y-auto"
        >
          {!events || events.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              まだ発話はありません
            </p>
          ) : (
            events.map((ev) => <EventRow key={ev.id} event={ev} />)
          )}
        </div>
      </CardContent>
    </Card>
  )
})

export default AIActivityLog
