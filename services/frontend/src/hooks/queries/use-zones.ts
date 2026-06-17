import { useQuery } from '@tanstack/react-query'
import { fetchZones } from '@/lib/api/zones'
import type { ZoneData } from '@/lib/types'

export const ZONES_KEY = ['zones'] as const

/**
 * 共有 zones フック。
 * 最短 refetchInterval = 5000ms (devices/page が要求する最短値)
 * layout=10000 / usePsdEventDriven=10000 / EnvTrendCard=30000 も
 * 同じ queryKey を共有するため、TanStack は最短 5000ms を採用する。
 * ここで一元管理することで意図を明示し、分散設定の矛盾を解消する。
 *
 * staleTime は refetchInterval 未満にしておくことで、interval 発火時に
 * データが確実に stale になり、意図した間隔でポーリングが継続する。
 */
export const ZONES_REFETCH_INTERVAL = 5000

export function useZones() {
  return useQuery<ZoneData[]>({
    queryKey: ZONES_KEY,
    queryFn: fetchZones,
    refetchInterval: ZONES_REFETCH_INTERVAL,
    staleTime: ZONES_REFETCH_INTERVAL / 2,
    retry: false,
  })
}
