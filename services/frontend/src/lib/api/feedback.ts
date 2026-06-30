import { apiFetch } from '@/lib/api-client'
import type { AgentFeedback, AgentFeedbackStats, SubmitFeedbackInput } from '@/lib/types'

export const submitFeedback = (input: SubmitFeedbackInput): Promise<AgentFeedback> =>
  apiFetch('/feedback/', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const fetchFeedbackStats = (
  targetType?: string,
  targetId?: string,
): Promise<AgentFeedbackStats> => {
  const params = new URLSearchParams()
  if (targetType) params.set('target_type', targetType)
  if (targetId) params.set('target_id', targetId)
  const query = params.toString()
  return apiFetch(`/feedback/stats${query ? `?${query}` : ''}`)
}
