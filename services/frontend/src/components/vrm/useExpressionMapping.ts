import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { VRM } from '@pixiv/three-vrm'
import { useAudioAnalyser } from '@/audio'

interface ExpressionTarget {
  name: string
  weight: number
}

// VRM 0.x emotion presets only: happy/angry/sad/relaxed (no `surprised`).
const TONE_MAP: Record<string, ExpressionTarget> = {
  neutral:  { name: 'relaxed', weight: 0.0 },
  caring:   { name: 'happy',   weight: 0.4 },
  humorous: { name: 'happy',   weight: 0.7 },
  alert:    { name: 'angry',   weight: 0.4 },
}

const ONSET_SPEED = 0.08  // ~300ms to reach target
const DECAY_SPEED = 0.04  // ~500ms to return to neutral

export function useExpressionMapping(vrm: VRM | null) {
  const { isActive, currentTone } = useAudioAnalyser()
  const currentWeights = useRef<Record<string, number>>({})
  const prevExpression = useRef<string | null>(null)

  useFrame(() => {
    if (!vrm?.expressionManager) return

    // Determine target
    const tone = (isActive && currentTone) ? currentTone : 'neutral'
    const target = TONE_MAP[tone] || TONE_MAP.neutral

    // If expression changed, we need to decay the old one
    if (prevExpression.current && prevExpression.current !== target.name) {
      const oldWeight = currentWeights.current[prevExpression.current] || 0
      if (oldWeight > 0.01) {
        const newWeight = oldWeight * (1 - DECAY_SPEED)
        currentWeights.current[prevExpression.current] = newWeight
        vrm.expressionManager.setValue(prevExpression.current, newWeight)
      } else {
        currentWeights.current[prevExpression.current] = 0
        vrm.expressionManager.setValue(prevExpression.current, 0)
        prevExpression.current = target.name
      }
    } else {
      prevExpression.current = target.name
    }

    // Animate toward target
    if (target.weight > 0) {
      const current = currentWeights.current[target.name] || 0
      const speed = isActive ? ONSET_SPEED : DECAY_SPEED
      const next = current + (target.weight - current) * speed
      currentWeights.current[target.name] = next
      vrm.expressionManager.setValue(target.name, Math.min(1, Math.max(0, next)))
    }
  })
}
