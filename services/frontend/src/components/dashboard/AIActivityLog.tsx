import { memo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare, Brain, ChevronRight, AlertCircle, CheckCircle2, XCircle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchBrainStatus } from '@/lib/api'
import { useVoiceEvents } from '@/hooks/queries/use-voice-events'
import { ZONE_LABELS } from '@/lib/constants'
import type { VoiceEvent, BrainCycleSummary } from '@/lib/types'

const TONE_VARIANTS: Record<string, 'secondary' | 'info' | 'warning' | 'destructive'> = {
  neutral: 'secondary',
  caring: 'info',
  humorous: 'warning',
  alert: 'destructive',
}

const CYCLE_MODE_LABEL: Record<string, string> = {
  llm: 'LLM',
  rule_low_power_idle: 'ルール (低消費・無発火)',
  rule_low_power_throttled: 'ルール (LLM抑制)',
  rule_vlm_swap: 'ルール (VLM占有中)',
  rule_gpu_busy: 'ルール (GPU高負荷)',
}

function formatTime(ts?: number | string | null): string {
  if (!ts) return ''
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
  return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function CycleBlock({ cycle }: { cycle: BrainCycleSummary }) {
  const [expanded, setExpanded] = useState(false)
  const modeLabel = CYCLE_MODE_LABEL[cycle.mode] ?? cycle.mode
  const isLLM = cycle.mode === 'llm'
  const hasActivity = cycle.total_tool_calls > 0 || cycle.trigger_events.length > 0
  const triggerSummary = cycle.trigger_events.slice(0, 3).map((e) => e.event).join(', ')

  return (
    <div className="border-b border-border last:border-0 py-2">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 text-left hover:bg-muted/30 -mx-2 px-2 py-1 rounded transition-colors"
      >
        <Brain className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${isLLM ? 'text-primary' : 'text-muted-foreground'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-muted-foreground font-mono">{formatTime(cycle.timestamp)}</span>
            <Badge variant={isLLM ? 'default' : 'secondary'} className="text-[9px] px-1 py-0 leading-tight">
              {modeLabel}
            </Badge>
            {cycle.iterations > 0 && (
              <span className="text-[10px] text-muted-foreground">{cycle.iterations}反復</span>
            )}
            {cycle.total_tool_calls > 0 && (
              <span className="text-[10px] text-muted-foreground">{cycle.total_tool_calls}ツール</span>
            )}
            <span className="text-[10px] text-muted-foreground ml-auto">{cycle.elapsed.toFixed(1)}s</span>
          </div>
          {hasActivity ? (
            <p className="text-xs text-foreground mt-0.5 truncate">
              {triggerSummary && (
                <span className="text-muted-foreground">トリガ: {triggerSummary}</span>
              )}
              {triggerSummary && cycle.tool_calls.length > 0 && <span className="mx-1">→</span>}
              {cycle.tool_calls.length > 0 && (
                <span>{cycle.tool_calls.map((t) => t.tool).join(', ')}</span>
              )}
              {!triggerSummary && cycle.tool_calls.length === 0 && (
                <span className="text-muted-foreground italic">アクションなし</span>
              )}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground mt-0.5 italic">何も検出されず</p>
          )}
        </div>
        <ChevronRight
          className={`h-3 w-3 mt-1 shrink-0 text-muted-foreground transition-transform ${
            expanded ? 'rotate-90' : ''
          }`}
        />
      </button>

      {expanded && (
        <div className="ml-6 mt-1 space-y-1.5">
          {cycle.trigger_events.length > 0 && (
            <div>
              <p className="text-[10px] uppercase text-muted-foreground tracking-wide mb-0.5">トリガイベント</p>
              <div className="flex flex-wrap gap-1">
                {cycle.trigger_events.map((ev, i) => (
                  <Badge
                    key={i}
                    variant={ev.severity >= 2 ? 'destructive' : ev.severity >= 1 ? 'warning' : 'outline'}
                    className="text-[9px] px-1 py-0 gap-0.5 font-normal"
                  >
                    <AlertCircle className="h-2.5 w-2.5" />
                    {ev.event}
                    <span className="text-[8px] opacity-70">({ev.zone})</span>
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {cycle.tool_calls.length > 0 && (
            <div>
              <p className="text-[10px] uppercase text-muted-foreground tracking-wide mb-0.5">ツール呼び出し</p>
              <div className="space-y-0.5">
                {cycle.tool_calls.map((tc, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px]">
                    {tc.success ? (
                      <CheckCircle2 className="h-3 w-3 text-chart-green mt-0.5 shrink-0" />
                    ) : (
                      <XCircle className="h-3 w-3 text-destructive mt-0.5 shrink-0" />
                    )}
                    <span className="font-mono text-foreground">{tc.tool}</span>
                    {tc.summary && <span className="text-muted-foreground truncate">— {tc.summary}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function VoiceEventRow({ event }: { event: VoiceEvent }) {
  const variant = TONE_VARIANTS[event.tone] ?? 'secondary'
  return (
    <div className="flex gap-3 py-2 border-b border-border last:border-0">
      <span className="text-[11px] text-muted-foreground font-mono shrink-0 pt-0.5 w-16">
        {formatTime(event.created_at)}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <MessageSquare className="h-3 w-3 text-muted-foreground" />
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
  const { data: events } = useVoiceEvents()
  const { data: brain } = useQuery({
    queryKey: ['brainStatus'],
    queryFn: fetchBrainStatus,
    refetchInterval: 5000,
  })

  const cycle = brain?.last_cycle
  const hasContent = (events && events.length > 0) || cycle

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          AI Activity Log
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0">
        <div className="h-full overflow-y-auto">
          {!hasContent ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              まだ活動はありません
            </p>
          ) : (
            <>
              {cycle && <CycleBlock cycle={cycle} />}
              {events?.map((ev) => <VoiceEventRow key={ev.id} event={ev} />)}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
})

export default AIActivityLog
