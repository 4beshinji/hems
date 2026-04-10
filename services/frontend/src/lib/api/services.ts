import { apiFetch } from '@/lib/api-client'
import type { ServicesData } from '@/lib/types'

export const fetchServices = (): Promise<ServicesData> =>
  apiFetch('/services/')
