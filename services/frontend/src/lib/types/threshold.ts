export interface ThresholdDriftLog {
  id: number
  metric_key: string
  detector: string
  detected_at: string
  old_value: number | null
  proposed_value: number | null
  reason: string | null
  status: 'proposed' | 'approved' | 'rejected' | 'auto_applied'
  context_json: Record<string, unknown>
}

export interface ThresholdAdjustment {
  id: number
  metric_key: string
  base_value: number
  offset: number
  applied_at: string
  approved_by: string | null
  drift_log_id: number | null
}

export interface ThresholdDecisionInput {
  decision: 'approve' | 'reject' | 'auto_apply'
  reviewer_id?: string
  reason?: string
}
