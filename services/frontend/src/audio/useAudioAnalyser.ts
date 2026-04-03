import { useCallback, useRef } from 'react'
import { useSyncExternalStore } from 'react'
import { audioAnalyser } from './AudioAnalyser'

export function useAudioAnalyser() {
  const snapshotRef = useRef(audioAnalyser.getSnapshot())

  const subscribe = useCallback((onStoreChange: () => void) => {
    return audioAnalyser.subscribe(() => {
      snapshotRef.current = audioAnalyser.getSnapshot()
      onStoreChange()
    })
  }, [])

  const getSnapshot = useCallback(() => snapshotRef.current, [])

  const state = useSyncExternalStore(subscribe, getSnapshot)

  return {
    isActive: state.isActive,
    currentTone: state.currentTone,
    currentMotionId: state.currentMotionId,
    getFrequencyData: audioAnalyser.getFrequencyData.bind(audioAnalyser),
  }
}
