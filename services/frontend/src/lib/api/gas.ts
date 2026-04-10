import { apiFetch } from '@/lib/api-client'
import type { GASData } from '@/lib/types'

export const fetchGAS = (): Promise<GASData> =>
  apiFetch('/gas/')
