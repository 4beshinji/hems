import { useQuery } from '@tanstack/react-query'
import { fetchVoiceEvents } from '@/lib/api/voice-events'
import type { VoiceEvent } from '@/lib/types'

export const VOICE_EVENTS_KEY = ['voiceEvents'] as const

/**
 * 共有 voiceEvents フック。
 * 最短 refetchInterval = 3000ms (layout/ChatPanel/AIActivityLog が要求する最短値)
 * TanStack Query は同一 queryKey で複数コンポーネントが呼んでも
 * 実 HTTP は 1 系統のみ。interval は最短値が採用される。
 * ここで一元管理することで意図を明示する。
 */
export const VOICE_EVENTS_REFETCH_INTERVAL = 3000

export function useVoiceEvents(options?: { enabled?: boolean }) {
  return useQuery<VoiceEvent[]>({
    queryKey: VOICE_EVENTS_KEY,
    queryFn: fetchVoiceEvents,
    refetchInterval: VOICE_EVENTS_REFETCH_INTERVAL,
    staleTime: VOICE_EVENTS_REFETCH_INTERVAL,
    retry: false,
    enabled: options?.enabled,
  })
}
