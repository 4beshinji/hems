import { apiFetch } from '@/lib/api-client'
import type { Approval, ApprovalDecisionRequest } from '@/lib/types'

export const fetchApprovals = (status?: string): Promise<Approval[]> =>
  apiFetch('/approvals/' + (status ? `?status=${encodeURIComponent(status)}` : ''))

export const fetchApproval = (id: string): Promise<Approval> =>
  apiFetch(`/approvals/${id}`)

export const decideApproval = (
  id: string,
  decision: ApprovalDecisionRequest
): Promise<Approval> =>
  apiFetch(`/approvals/${id}/decide`, {
    method: 'POST',
    body: JSON.stringify(decision),
  })

export const cleanupExpiredApprovals = (): Promise<{ expired_count: number }> =>
  apiFetch('/approvals/cleanup/expired', { method: 'POST' })
