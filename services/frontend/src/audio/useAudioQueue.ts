import { useEffect, useSyncExternalStore } from 'react'
import { audioQueue, AudioPriority } from './AudioQueue'

export function useAudioQueue(enabled: boolean) {
  const isEnabled = useSyncExternalStore(audioQueue.subscribe, audioQueue.getSnapshot)
  useEffect(() => { audioQueue.setEnabled(enabled) }, [enabled])
  return { enqueue: audioQueue.enqueue, clear: audioQueue.clear, isEnabled, AudioPriority } as const
}
