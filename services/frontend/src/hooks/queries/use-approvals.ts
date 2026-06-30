import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchApprovals, decideApproval } from '@/lib/api/approvals'
import type { Approval, ApprovalDecisionRequest } from '@/lib/types'

export const APPROVALS_KEY = ['approvals'] as const

export const APPROVALS_REFETCH_INTERVAL = 3000

export function useApprovals(status?: string) {
  return useQuery<Approval[]>({
    queryKey: status ? [...APPROVALS_KEY, status] : APPROVALS_KEY,
    queryFn: () => fetchApprovals(status),
    refetchInterval: APPROVALS_REFETCH_INTERVAL,
    staleTime: APPROVALS_REFETCH_INTERVAL / 2,
    retry: false,
  })
}

export function useDecideApproval() {
  const queryClient = useQueryClient()
  return useMutation<Approval, Error, { id: string; decision: ApprovalDecisionRequest }>({
    mutationFn: ({ id, decision }) => decideApproval(id, decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: APPROVALS_KEY })
    },
  })
}
