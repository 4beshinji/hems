export type ApprovalStatus =
  | 'proposed'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'modified'
  | 'expired'
  | 'rolled_back'

export type ApprovalDecision = 'approve' | 'reject' | 'modify'
export type RiskTier = 'safe' | 'low' | 'medium' | 'high' | 'critical'
export type Reversibility = 'reversible' | 'compensatable' | 'irreversible'

export interface Approval {
  id: string
  thread_id: string | null
  rule_id: number | null
  action_type: string
  risk_tier: RiskTier
  reversibility: Reversibility
  confidence: number | null
  proposed_payload: Record<string, unknown>
  context: Record<string, unknown>
  status: ApprovalStatus
  reviewer_id: string | null
  decision: ApprovalDecision | null
  decision_reason: string | null
  requested_at: string | null
  decided_at: string | null
  expires_at: string | null
  executed_at: string | null
  rollback_plan: Record<string, unknown> | null
  rollback_status: string | null
  audit_log: unknown[]
}

export interface ApprovalDecisionRequest {
  decision: ApprovalDecision
  reason?: string | null
  reviewer_id?: string | null
  modified_payload?: Record<string, unknown> | null
}

export interface ActionSnapshot {
  id: number
  approval_id: string
  entity_type: string
  entity_id: string
  before_state: Record<string, unknown>
  after_state: Record<string, unknown> | null
  captured_at: string | null
}
