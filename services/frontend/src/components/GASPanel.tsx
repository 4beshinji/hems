import { Calendar, CheckSquare, Mail, Clock } from 'lucide-react'
import type { GASData } from '../api'

interface Props {
  gas: GASData | null
}

function formatTime(isoStr: string): string {
  if (!isoStr || !isoStr.includes('T')) return isoStr
  return isoStr.split('T')[1]?.substring(0, 5) ?? isoStr
}

function isEventSoon(startStr: string): boolean {
  try {
    const start = new Date(startStr).getTime()
    const now = Date.now()
    return start > now && start - now < 600000 // within 10 min
  } catch {
    return false
  }
}

export default function GASPanel({ gas }: Props) {
  if (!gas || gas.status === 'no_data') return null

  const events = gas.calendar_events ?? []
  const tasks = gas.tasks_due ?? []
  const freeSlots = gas.free_slots ?? []
  const overdueCount = gas.overdue_count ?? 0
  const inboxUnread = gas.gmail_inbox_unread ?? 0

  return (
    <div className="bg-white rounded-xl elevation-2 p-5 mt-4">
      <h3 className="font-semibold text-gray-800 flex items-center gap-2 mb-3">
        <Calendar className="w-5 h-5 text-blue-500" />
        Google
      </h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Calendar events */}
        <div className="px-3 py-2 rounded-lg bg-gray-50">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <span className="text-sm font-medium text-gray-700">
              {gas.calendar_event_count ?? events.length} 件の予定
            </span>
          </div>
          <div className="space-y-0.5">
            {events.slice(0, 4).map((ev, i) => (
              <p
                key={ev.id || i}
                className={`text-xs truncate ${
                  isEventSoon(ev.start)
                    ? 'text-red-600 font-medium'
                    : 'text-gray-500'
                }`}
              >
                {ev.is_all_day ? '終日' : formatTime(ev.start)} {ev.title}
              </p>
            ))}
            {events.length === 0 && (
              <p className="text-xs text-gray-400">予定なし</p>
            )}
          </div>
        </div>

        {/* Tasks */}
        <div className="px-3 py-2 rounded-lg bg-gray-50">
          <div className="flex items-center gap-2 mb-1">
            <CheckSquare className="w-4 h-4 text-green-500 flex-shrink-0" />
            <span className="text-sm font-medium text-gray-700">
              {tasks.length} タスク
              {overdueCount > 0 && (
                <span className="text-red-500 ml-1">({overdueCount} 期限切れ)</span>
              )}
            </span>
          </div>
          <div className="space-y-0.5">
            {tasks.slice(0, 4).map((t, i) => (
              <p
                key={i}
                className={`text-xs truncate ${
                  t.is_overdue ? 'text-red-600 font-medium' : 'text-gray-500'
                }`}
              >
                {t.is_overdue ? '!' : '-'} {t.title}
              </p>
            ))}
            {tasks.length === 0 && (
              <p className="text-xs text-gray-400">タスクなし</p>
            )}
          </div>
        </div>

        {/* Gmail */}
        <div className="px-3 py-2 rounded-lg bg-gray-50">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span className="text-sm font-medium text-gray-700">Gmail</span>
          </div>
          <div className="mt-1">
            <span
              className={`text-2xl font-bold ${
                inboxUnread >= 20
                  ? 'text-red-600'
                  : inboxUnread >= 10
                    ? 'text-amber-600'
                    : 'text-gray-700'
              }`}
            >
              {inboxUnread}
            </span>
            <span className="text-xs text-gray-500 ml-1">未読</span>
          </div>
        </div>

        {/* Free slots */}
        <div className="px-3 py-2 rounded-lg bg-gray-50">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-purple-500 flex-shrink-0" />
            <span className="text-sm font-medium text-gray-700">空き時間</span>
          </div>
          <div className="space-y-0.5">
            {freeSlots.slice(0, 3).map((s, i) => (
              <p key={i} className="text-xs text-gray-500">
                {formatTime(s.start)}-{formatTime(s.end)} ({s.duration_minutes}分)
              </p>
            ))}
            {freeSlots.length === 0 && (
              <p className="text-xs text-gray-400">空きなし</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
