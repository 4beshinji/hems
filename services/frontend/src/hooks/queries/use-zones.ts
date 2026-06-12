import { useQuery } from '@tanstack/react-query'
import { fetchZones } from '@/lib/api/zones'
import type { ZoneData } from '@/lib/types'

export const ZONES_KEY = ['zones'] as const

export function useZones() {
  return useQuery<ZoneData[]>({
    queryKey: ZONES_KEY,
    queryFn: fetchZones,
    refetchInterval: 30000,
    retry: false,
  })
}
