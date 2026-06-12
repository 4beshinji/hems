// ─── Tasks ────────────────────────────────────────────────────────────────────
export type PreferredTimeSlot =
  | 'morning'
  | 'afternoon'
  | 'evening'
  | 'deep_night'
  | 'anytime'

export type TaskProposalStatus = 'proposed' | 'dismissed' | null

export interface TaskData {
  id: number
  title: string
  description?: string | null
  location?: string | null
  is_completed: boolean
  is_queued: boolean
  urgency: number
  zone?: string | null
  estimated_duration: number
  task_type?: string[] | null
  announcement_audio_url?: string | null
  announcement_text?: string | null
  completion_audio_url?: string | null
  completion_text?: string | null
  assigned_to?: number | null
  accepted_at?: string | null
  dispatched_at?: string | null
  created_at?: string | null
  completed_at?: string | null
  expires_at?: string | null
  last_reminded_at?: string | null
  report_status?: string | null
  completion_note?: string | null
  cognitive_load?: number | null
  preferred_time_slot?: PreferredTimeSlot | null
  deadline?: string | null
  source?: string | null
  source_ref?: string | null
  confidence?: number | null
  proposal_status?: TaskProposalStatus
  dismissed_at?: string | null
  dismiss_reason?: string | null
  locked_start?: string | null
}

export interface TaskCreatePayload {
  title: string
  description?: string
  location?: string
  urgency?: number
  zone?: string
  estimated_duration?: number
  task_type?: string[]
  cognitive_load?: number
  preferred_time_slot?: PreferredTimeSlot
  deadline?: string
  source?: string
  source_ref?: string
}
