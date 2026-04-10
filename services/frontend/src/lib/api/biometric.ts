import { apiFetch } from '@/lib/api-client'
import type { BiometricData } from '@/lib/types'

export const fetchBiometric = (): Promise<BiometricData> =>
  apiFetch('/biometric/')
