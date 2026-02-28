import { memo } from 'react'
import { Calendar, CheckSquare, Mail, Clock } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { formatTime } from '@/lib/formatters'
import { isEventSoon } from '@/lib/color-utils'
import type { GASData } from '@/lib/types'

interface Props {
  gas: GASData | null
}

const GASPanel = memo(function GASPanel({ gas }: Props) {
  if (!gas || gas.status === 'no_data') return null

  const events = gas.calendar_events ?? []
  const tasks = gas.tasks_due ?? []
  const freeSlots = gas.free_slots ?? []
  const overdueCount = gas.overdue_count ?? 0
  const inboxUnread = gas.gmail_inbox_unread ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-chart-blue" />
          Google Services
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="calendar">
          <TabsList className="w-full">
            <TabsTrigger value="calendar" className="flex-1">
              <Calendar className="h-3.5 w-3.5 mr-1" />
              予定
            </TabsTrigger>
            <TabsTrigger value="tasks" className="flex-1">
              <CheckSquare className="h-3.5 w-3.5 mr-1" />
              タスク
              {overdueCount > 0 && <Badge variant="destructive" className="ml-1 text-[9px] px-1 py-0">{overdueCount}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="gmail" className="flex-1">
              <Mail className="h-3.5 w-3.5 mr-1" />
              Gmail
              {inboxUnread > 0 && <Badge variant="info" className="ml-1 text-[9px] px-1 py-0">{inboxUnread}</Badge>}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="calendar" className="space-y-1">
            {events.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">予定なし</p>
            ) : (
              events.slice(0, 6).map((ev, i) => (
                <p
                  key={ev.id || i}
                  className={`text-xs py-1 truncate ${isEventSoon(ev.start) ? 'text-destructive font-medium' : 'text-foreground'}`}
                >
                  <span className="text-muted-foreground mr-2">
                    {ev.is_all_day ? '終日' : formatTime(ev.start)}
                  </span>
                  {ev.title}
                </p>
              ))
            )}
            {/* Free Slots */}
            {freeSlots.length > 0 && (
              <div className="pt-2 border-t border-border">
                <p className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                  <Clock className="h-3 w-3" />
                  空き時間
                </p>
                {freeSlots.slice(0, 3).map((s, i) => (
                  <p key={i} className="text-xs text-foreground">
                    {formatTime(s.start)}-{formatTime(s.end)} ({s.duration_minutes}分)
                  </p>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="tasks" className="space-y-1">
            {tasks.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">タスクなし</p>
            ) : (
              tasks.slice(0, 6).map((t, i) => (
                <p
                  key={i}
                  className={`text-xs py-1 truncate ${t.is_overdue ? 'text-destructive font-medium' : 'text-foreground'}`}
                >
                  {t.is_overdue ? '!' : '-'} {t.title}
                </p>
              ))
            )}
          </TabsContent>

          <TabsContent value="gmail">
            <div className="flex items-center justify-center py-4">
              <div className="text-center">
                <span className={`text-3xl font-bold ${
                  inboxUnread >= 20 ? 'text-destructive' :
                  inboxUnread >= 10 ? 'text-warning' :
                  'text-foreground'
                }`}>
                  {inboxUnread}
                </span>
                <p className="text-xs text-muted-foreground mt-1">未読</p>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
})

export default GASPanel
