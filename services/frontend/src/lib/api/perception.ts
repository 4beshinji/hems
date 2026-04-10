import { apiFetch } from '@/lib/api-client'
import type { PerceptionData } from '@/lib/types'

export const fetchPerception = (): Promise<PerceptionData> =>
  apiFetch('/perception/')
