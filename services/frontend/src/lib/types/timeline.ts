// ─── Timeline ────────────────────────────────────────────────────────────────
export type TimelineSlotKind =
  | 'calendar'
  | 'task'
  | 'routine_wake'
  | 'commute_out'
  | 'commute_in'
  | 'focus_free'
  | 'sleep'
  | 'prep'

export interface ScheduledBlock {
  id: number
  date: string
  start_ts: string
  end_ts: string
  kind: TimelineSlotKind
  ref_task_id?: number | null
  ref_calendar_event_id?: string | null
  title: string
  location?: string | null
  is_locked: boolean
  travel_buffer_minutes: number
  generated_at?: string | null
}

export interface TimelineData {
  date: string
  blocks: ScheduledBlock[]
  generated_at?: string | null
}
