import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchBrainStatus, setPowerMode } from '@/lib/api'
import type { PowerMode, BrainStatus } from '@/lib/types'

const CYCLE: PowerMode[] = ['normal', 'sleep', 'away']

export function usePowerMode() {
  const qc = useQueryClient()

  const query = useQuery<BrainStatus>({
    queryKey: ['brainStatus'],
    queryFn: fetchBrainStatus,
    refetchInterval: 15000,
    // Silently fail when brain is not yet running
    retry: false,
  })

  const mutation = useMutation({
    mutationFn: (mode: PowerMode) => setPowerMode(mode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['brainStatus'] }),
  })

  const mode: PowerMode = query.data?.mode ?? 'normal'

  const cycleMode = () => {
    const next = CYCLE[(CYCLE.indexOf(mode) + 1) % CYCLE.length]
    mutation.mutate(next)
  }

  return {
    mode,
    status: query.data,
    cycleMode,
    isPending: mutation.isPending,
  }
}
