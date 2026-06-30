import { useMutation, useQueryClient } from '@tanstack/react-query'
import { submitFeedback } from '@/lib/api/feedback'
import type { SubmitFeedbackInput, AgentFeedback } from '@/lib/types'

export function useSubmitFeedback() {
  const queryClient = useQueryClient()
  return useMutation<AgentFeedback, Error, SubmitFeedbackInput>({
    mutationFn: submitFeedback,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedbackStats'] })
    },
  })
}
