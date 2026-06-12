import { useState, useMemo, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { TASKS_KEY } from '@/hooks/queries/use-tasks'
import { toast } from 'sonner'
import { Plus, X, Clock, MapPin, Lock, RefreshCw, Calendar, ChevronLeft, ChevronRight } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import CreateTaskModal from '@/components/tasks/CreateTaskModal'
import { fetchTimelineToday, fetchTimelineDay, dismissTask, completeTask } from '@/lib/api'
import { formatTime, formatTimeRange, formatDuration } from '@/lib/formatters'
import { TIMELINE_KIND_LABELS, TIMELINE_KIND_COLORS } from '@/lib/constants'
import { cn } from '@/lib/utils'
import type { ScheduledBlock, TimelineSlotKind } from '@/lib/types'

const HOUR_HEIGHT_PX = 56
const START_HOUR = 6
const END_HOUR = 26 // shows up to 02:00 next day
const WEEK_DAYS = 7

function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}

const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土']

function minutesSinceDayStart(iso: string, dayStartMs: number): number {
  const t = new Date(iso).getTime()
  return Math.max(0, (t - dayStartMs) / 60000)
}

function formatHourLabel(hour: number): string {
  const actual = hour % 24
  return `${String(actual).padStart(2, '0')}:00`
}

export default function TimelinePanel() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState<ScheduledBlock | null>(null)
  const [nowMs, setNowMs] = useState(Date.now())
  const [dayOffset, setDayOffset] = useState(0) // 0 = today

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const selectedDate = useMemo(() => addDays(today, dayOffset), [today, dayOffset])
  const selectedDateStr = useMemo(() => toDateStr(selectedDate), [selectedDate])
  const isToday = dayOffset === 0

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['timeline', selectedDateStr],
    queryFn: () => isToday ? fetchTimelineToday() : fetchTimelineDay(selectedDateStr),
    refetchInterval: isToday ? 30000 : 120000,
  })

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 60000)
    return () => clearInterval(id)
  }, [])

  const dayStartMs = useMemo(() => {
    const d = selectedDate
    return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0).getTime()
  }, [selectedDate])

  const hours = useMemo(() => {
    const arr: number[] = []
    for (let h = START_HOUR; h <= END_HOUR; h++) arr.push(h)
    return arr
  }, [])
  const totalHeightPx = (END_HOUR - START_HOUR) * HOUR_HEIGHT_PX
  const blocks = data?.blocks ?? []
  const nowOffsetPx = useMemo(() => {
    if (!isToday) return null
    const diffMin = (nowMs - dayStartMs) / 60000
    const rangeMinStart = START_HOUR * 60
    const rangeMinEnd = END_HOUR * 60
    if (diffMin < rangeMinStart || diffMin > rangeMinEnd) return null
    return ((diffMin - rangeMinStart) / 60) * HOUR_HEIGHT_PX
  }, [nowMs, dayStartMs, isToday])

  const goToday = useCallback(() => setDayOffset(0), [])

  // Week day tabs
  const weekDays = useMemo(() => {
    return Array.from({ length: WEEK_DAYS }, (_, i) => {
      const d = addDays(today, i)
      return {
        offset: i,
        date: d,
        dateStr: toDateStr(d),
        dayNum: d.getDate(),
        weekday: WEEKDAY_LABELS[d.getDay()],
        isWeekend: d.getDay() === 0 || d.getDay() === 6,
      }
    })
  }, [today])

  return (
    <Card className="h-full flex flex-col min-h-0">
      <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-primary" />
          <span className="text-xs font-normal text-muted-foreground">
            {blocks.length}ブロック
          </span>
        </CardTitle>
        <div className="flex gap-1">
          {!isToday && (
            <Button variant="ghost" size="sm" onClick={goToday} className="h-7 text-xs px-2">
              今日
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={async () => {
              await refetch()
              toast.info('更新しました')
            }}
            aria-label="更新"
            className="h-8 w-8"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />追加
          </Button>
        </div>
      </CardHeader>

      {/* Week day tabs */}
      <div className="flex items-center px-3 pb-2 gap-0.5">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={dayOffset <= 0}
          onClick={() => setDayOffset(Math.max(0, dayOffset - 1))}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <div className="flex flex-1 gap-0.5 justify-center">
          {weekDays.map((d) => (
            <button
              key={d.offset}
              onClick={() => setDayOffset(d.offset)}
              className={cn(
                'flex flex-col items-center rounded-md px-1.5 py-1 text-[10px] leading-tight transition-colors min-w-[2rem]',
                d.offset === dayOffset
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-muted',
                d.isWeekend && d.offset !== dayOffset && 'text-muted-foreground',
              )}
            >
              <span className="font-medium">{d.weekday}</span>
              <span className={cn('text-xs', d.offset === 0 && d.offset !== dayOffset && 'text-primary font-bold')}>
                {d.dayNum}
              </span>
            </button>
          ))}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={dayOffset >= WEEK_DAYS - 1}
          onClick={() => setDayOffset(Math.min(WEEK_DAYS - 1, dayOffset + 1))}
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>

      <CardContent className="flex-1 min-h-0 overflow-y-auto p-0">
        {isLoading ? (
          <div className="p-8 text-center text-muted-foreground">読み込み中...</div>
        ) : blocks.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            {isToday
              ? '今日のスケジュールはまだ生成されていません'
              : `${selectedDate.getMonth() + 1}/${selectedDate.getDate()} のスケジュールはまだありません`}
          </div>
        ) : (
          <div className="relative" style={{ height: `${totalHeightPx}px` }}>
            {/* Hour grid */}
            <div className="absolute inset-0">
              {hours.map((h) => {
                const offset = (h - START_HOUR) * HOUR_HEIGHT_PX
                return (
                  <div
                    key={h}
                    className="absolute left-0 right-0 border-t border-border/50"
                    style={{ top: `${offset}px`, height: `${HOUR_HEIGHT_PX}px` }}
                  >
                    <span className="absolute -top-2 left-2 text-[10px] text-muted-foreground font-mono">
                      {formatHourLabel(h)}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Current time line (today only) */}
            {nowOffsetPx !== null && (
              <div
                className="absolute left-16 right-2 z-10 pointer-events-none"
                style={{ top: `${nowOffsetPx}px` }}
              >
                <div className="h-0.5 bg-red-500/80 relative">
                  <div className="absolute -left-2 -top-1 h-2 w-2 rounded-full bg-red-500" />
                  <span className="absolute -top-4 right-0 text-[10px] font-mono text-red-500">
                    {formatTime(new Date(nowMs).toISOString())}
                  </span>
                </div>
              </div>
            )}

            {/* Blocks */}
            <div className="absolute inset-0 pl-16 pr-2 py-1">
              {blocks.map((b) => {
                const startMin = minutesSinceDayStart(b.start_ts, dayStartMs)
                const endMin = minutesSinceDayStart(b.end_ts, dayStartMs)
                const rangeStart = START_HOUR * 60
                if (endMin <= rangeStart) return null
                const top = Math.max(0, (startMin - rangeStart) / 60) * HOUR_HEIGHT_PX
                const durationMin = Math.max(5, endMin - Math.max(startMin, rangeStart))
                const height = Math.max(18, (durationMin / 60) * HOUR_HEIGHT_PX - 2)
                const colorClass = TIMELINE_KIND_COLORS[b.kind] ?? 'bg-gray-500/20 border-gray-500/60'
                return (
                  <button
                    key={b.id}
                    onClick={() => setSelected(b)}
                    className={cn(
                      'absolute left-0 right-0 rounded-md border-l-4 px-2 py-1 text-left text-xs transition-all hover:shadow-md hover:z-20',
                      colorClass,
                      b.is_locked && 'ring-1 ring-offset-1 ring-offset-background',
                    )}
                    style={{ top: `${top}px`, height: `${height}px` }}
                  >
                    <div className="flex items-center gap-1 font-medium truncate">
                      {b.is_locked && <Lock className="h-2.5 w-2.5 shrink-0" />}
                      <span className="truncate">{b.title}</span>
                    </div>
                    <div className="text-[10px] opacity-70 truncate">
                      {formatTimeRange(b.start_ts, b.end_ts)}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>

      <CreateTaskModal open={createOpen} onOpenChange={setCreateOpen} />

      <BlockDetailDialog
        block={selected}
        onClose={() => setSelected(null)}
        onDismiss={async (id) => {
          try {
            await dismissTask(id)
            toast.success('タスクを却下しました')
            setSelected(null)
            queryClient.invalidateQueries({ queryKey: ['timeline'] })
            queryClient.invalidateQueries({ queryKey: TASKS_KEY })
          } catch {
            toast.error('却下に失敗しました')
          }
        }}
        onComplete={async (id) => {
          try {
            await completeTask(id, 'no_issue', '')
            toast.success('タスク完了')
            setSelected(null)
            queryClient.invalidateQueries({ queryKey: ['timeline'] })
            queryClient.invalidateQueries({ queryKey: TASKS_KEY })
          } catch {
            toast.error('完了に失敗しました')
          }
        }}
      />
    </Card>
  )
}

function BlockDetailDialog({
  block,
  onClose,
  onDismiss,
  onComplete,
}: {
  block: ScheduledBlock | null
  onClose: () => void
  onDismiss: (id: number) => void
  onComplete: (id: number) => void
}) {
  if (!block) return null
  const kindLabel = TIMELINE_KIND_LABELS[block.kind as TimelineSlotKind] ?? block.kind
  const isTask = block.kind === 'task' && block.ref_task_id != null

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Badge variant="secondary">{kindLabel}</Badge>
            <span className="truncate">{block.title}</span>
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock className="h-4 w-4" />
            {formatTimeRange(block.start_ts, block.end_ts)}
            <span className="text-xs opacity-70">
              ({formatDuration(
                Math.round((new Date(block.end_ts).getTime() - new Date(block.start_ts).getTime()) / 60000),
              )})
            </span>
          </div>
          {block.location && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="h-4 w-4" />{block.location}
            </div>
          )}
          {block.travel_buffer_minutes > 0 && (
            <div className="text-xs text-muted-foreground">
              移動時間: {block.travel_buffer_minutes}分
            </div>
          )}
          {block.is_locked && (
            <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
              <Lock className="h-3 w-3" />固定ブロック
            </div>
          )}
        </div>
        <DialogFooter className="gap-2">
          {isTask && (
            <>
              <Button variant="outline" onClick={() => onDismiss(block.ref_task_id!)}>
                <X className="h-4 w-4" />却下
              </Button>
              <Button onClick={() => onComplete(block.ref_task_id!)}>完了</Button>
            </>
          )}
          {!isTask && <Button variant="outline" onClick={onClose}>閉じる</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
