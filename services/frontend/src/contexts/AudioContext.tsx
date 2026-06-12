import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react'
import { useAudioQueue, AudioPriority } from '@/audio'

interface AudioContextValue {
  audioEnabled: boolean
  isEnabled: boolean
  enqueueAudio: (url: string, priority: AudioPriority, tone?: string, motionId?: string) => void
  toggleAudio: () => void
}

const AudioContext = createContext<AudioContextValue | null>(null)

export function AudioProvider({ children }: { children: ReactNode }) {
  const [audioEnabled, setAudioEnabled] = useState(false)
  const { enqueue, isEnabled } = useAudioQueue(audioEnabled)

  const toggleAudio = useCallback(() => setAudioEnabled(v => !v), [])

  const value = useMemo<AudioContextValue>(
    () => ({ audioEnabled, isEnabled, enqueueAudio: enqueue, toggleAudio }),
    [audioEnabled, isEnabled, enqueue, toggleAudio],
  )

  return <AudioContext.Provider value={value}>{children}</AudioContext.Provider>
}

export function useAudioContext(): AudioContextValue {
  const ctx = useContext(AudioContext)
  if (!ctx) throw new Error('useAudioContext must be used within AudioProvider')
  return ctx
}
