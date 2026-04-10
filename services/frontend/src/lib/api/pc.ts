import { apiFetch } from '@/lib/api-client'
import type { PCMetrics } from '@/lib/types'

export const fetchPC = (): Promise<PCMetrics> =>
  apiFetch('/pc/')
