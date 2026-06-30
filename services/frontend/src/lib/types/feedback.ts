export type FeedbackTargetType =
  | 'task'
  | 'voice'
  | 'device_action'
  | 'approval'
  | 'scene'
  | 'rule'

export type FeedbackType =
  | 'explicit_up'
  | 'explicit_down'
  | 'cancel'
  | 'rerun'
  | 'snooze'
  | 'dismiss'
  | 'complete'
  | 'implicit_override'

export interface AgentFeedback {
  id: number
  target_type: FeedbackTargetType
  target_id: string
  feedback_type: FeedbackType
  channel: string
  payload: Record<string, unknown>
  context: Record<string, unknown>
  user_id: string | null
  recorded_at: string
}

export interface AgentFeedbackStats {
  target_type?: string
  target_id?: string
  total: number
  positive: number
  negative: number
  reruns: number
  cancels: number
}

export interface SubmitFeedbackInput {
  target_type: FeedbackTargetType
  target_id: string
  feedback_type: FeedbackType
  channel?: string
  payload?: Record<string, unknown>
  context?: Record<string, unknown>
  user_id?: string
}
