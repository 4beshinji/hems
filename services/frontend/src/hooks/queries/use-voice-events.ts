import { useQuery } from '@tanstack/react-query'
import { fetchVoiceEvents } from '@/lib/api/voice-events'
import type { VoiceEvent } from '@/lib/types'

export const VOICE_EVENTS_KEY = ['voiceEvents'] as const

export function useVoiceEvents() {
  return useQuery<VoiceEvent[]>({
    queryKey: VOICE_EVENTS_KEY,
    queryFn: fetchVoiceEvents,
    refetchInterval: 10000,
    retry: false,
  })
}
