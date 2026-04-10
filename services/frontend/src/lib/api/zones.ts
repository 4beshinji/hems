import { apiFetch } from '@/lib/api-client'
import type { ZoneData } from '@/lib/types'

export const fetchZones = (): Promise<ZoneData[]> =>
  apiFetch('/zones/')
