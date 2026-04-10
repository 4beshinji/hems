import { apiFetch } from '@/lib/api-client'
import type { VoiceEvent } from '@/lib/types'

export const fetchVoiceEvents = (): Promise<VoiceEvent[]> =>
  apiFetch('/voice-events/recent')
