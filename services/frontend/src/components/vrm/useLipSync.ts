import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { VRM } from '@pixiv/three-vrm'
import { useAudioAnalyser } from '@/audio'

const VOWELS = ['aa', 'ih', 'ou', 'ee', 'oh'] as const
const LERP_SPEED = 0.3
const DECAY_SPEED = 0.15

// Frequency bin ranges for each vowel (based on 128 bins, ~172Hz per bin at 44100Hz)
// aa: F1 ~700-1000Hz (bins 4-6)
// ih: F1 ~300Hz + F2 ~2200-2600Hz (bins 2 + 13-15)
// ou: F1 ~300Hz + F2 ~800-1000Hz (bins 2 + 5-6)
// ee: F1 ~300Hz + F2 ~2300-2800Hz (bins 2 + 13-16)
// oh: F1 ~500Hz + F2 ~900-1100Hz (bins 3-4 + 5-7)
function analyzeVowels(data: Uint8Array): number[] {
  if (data.length === 0) return [0, 0, 0, 0, 0]

  const norm = (start: number, end: number) => {
    let sum = 0
    for (let i = start; i < Math.min(end, data.length); i++) sum += data[i]
    return sum / (end - start) / 255
  }

  const low = norm(2, 4)    // ~340-680Hz
  const midLow = norm(4, 7)  // ~680-1190Hz
  const mid = norm(5, 8)     // ~850-1360Hz
  const high = norm(13, 17)  // ~2210-2890Hz
  const total = norm(2, 20)  // overall speech energy

  if (total < 0.05) return [0, 0, 0, 0, 0]

  const aa = Math.min(1, midLow * 2.5)
  const ih = Math.min(1, (low + high) * 1.2)
  const ou = Math.min(1, (low + mid * 0.5) * 1.8)
  const ee = Math.min(1, (low * 0.5 + high * 1.5) * 1.5)
  const oh = Math.min(1, (midLow * 0.8 + mid * 0.8) * 1.5)

  // Normalize so strongest vowel dominates
  const max = Math.max(aa, ih, ou, ee, oh, 0.01)
  return [aa / max, ih / max, ou / max, ee / max, oh / max].map(v => v * total * 3)
}

export function useLipSync(vrm: VRM | null) {
  const { isActive, getFrequencyData } = useAudioAnalyser()
  const prevWeights = useRef([0, 0, 0, 0, 0])

  useFrame(() => {
    if (!vrm?.expressionManager) return

    const data = getFrequencyData()
    const targets = isActive ? analyzeVowels(data) : [0, 0, 0, 0, 0]
    const speed = isActive ? LERP_SPEED : DECAY_SPEED

    for (let i = 0; i < VOWELS.length; i++) {
      const prev = prevWeights.current[i]
      const next = prev + (targets[i] - prev) * speed
      prevWeights.current[i] = next
      vrm.expressionManager.setValue(VOWELS[i], Math.min(1, Math.max(0, next)))
    }
  })
}
