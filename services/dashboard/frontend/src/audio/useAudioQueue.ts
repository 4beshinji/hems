import { useEffect, useSyncExternalStore } from 'react';
import { audioQueue, AudioPriority } from './AudioQueue';

export function useAudioQueue(enabled: boolean) {
  const isEnabled = useSyncExternalStore(
    audioQueue.subscribe,
    audioQueue.getSnapshot,
  );

  // Sync the React-controlled enabled flag into the singleton
  useEffect(() => {
    audioQueue.setEnabled(enabled);
  }, [enabled]);

  return {
    enqueue: audioQueue.enqueue,
    enqueueFromApi: audioQueue.enqueueFromApi,
    clear: audioQueue.clear,
    isEnabled,
    AudioPriority,
  } as const;
}
