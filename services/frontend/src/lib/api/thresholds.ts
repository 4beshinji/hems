import { apiFetch } from '@/lib/api-client'
import type { ThresholdAdjustment, ThresholdDecisionInput, ThresholdDriftLog } from '@/lib/types'

export const fetchProposals = (status?: string): Promise<ThresholdDriftLog[]> => {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiFetch(`/thresholds/proposals${query}`)
}

export const decideProposal = (
  id: number,
  input: ThresholdDecisionInput,
): Promise<ThresholdDriftLog> =>
  apiFetch(`/thresholds/proposals/${id}/decide`, {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const fetchAdjustments = (): Promise<ThresholdAdjustment[]> =>
  apiFetch('/thresholds/adjustments')
