import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { VRM } from '@pixiv/three-vrm'

const BLINK_CLOSE_MS = 60
const BLINK_HOLD_MS = 80
const BLINK_OPEN_MS = 80

type BlinkState = 'idle' | 'closing' | 'closed' | 'opening'

const reducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function useIdleAnimations(vrm: VRM | null, isPlayingMotion = false) {
  const blinkState = useRef<BlinkState>('idle')
  const blinkTimer = useRef(0)
  const nextBlinkAt = useRef(randomBlinkDelay())
  const blinkValue = useRef(0)
  const elapsed = useRef(0)

  // Store initial bone positions/rotations to avoid drift
  const initialized = useRef(false)
  const spineBaseY = useRef(0)
  const headBaseX = useRef(0)
  const headBaseY = useRef(0)

  useFrame((_, delta) => {
    if (!vrm) return
    elapsed.current += delta

    // Initialize base values once
    if (!initialized.current) {
      const spine = vrm.humanoid?.getNormalizedBoneNode('spine')
      const head = vrm.humanoid?.getNormalizedBoneNode('head')
      if (spine) spineBaseY.current = spine.position.y
      if (head) {
        headBaseX.current = head.rotation.x
        headBaseY.current = head.rotation.y
      }
      initialized.current = true
    }

    // --- Blink ---
    blinkTimer.current += delta * 1000
    const em = vrm.expressionManager

    switch (blinkState.current) {
      case 'idle':
        if (blinkTimer.current >= nextBlinkAt.current) {
          blinkState.current = 'closing'
          blinkTimer.current = 0
        }
        break
      case 'closing': {
        const t = Math.min(1, blinkTimer.current / BLINK_CLOSE_MS)
        blinkValue.current = t
        if (t >= 1) { blinkState.current = 'closed'; blinkTimer.current = 0 }
        break
      }
      case 'closed':
        blinkValue.current = 1
        if (blinkTimer.current >= BLINK_HOLD_MS) {
          blinkState.current = 'opening'
          blinkTimer.current = 0
        }
        break
      case 'opening': {
        const t = Math.min(1, blinkTimer.current / BLINK_OPEN_MS)
        blinkValue.current = 1 - t
        if (t >= 1) {
          blinkState.current = 'idle'
          blinkTimer.current = 0
          nextBlinkAt.current = randomBlinkDelay()
          blinkValue.current = 0
        }
        break
      }
    }

    if (em) {
      em.setValue('blink', blinkValue.current)
    }

    if (reducedMotion || isPlayingMotion) return

    // --- Breathing ---
    const spine = vrm.humanoid?.getNormalizedBoneNode('spine')
    if (spine) {
      spine.position.y = spineBaseY.current + Math.sin(elapsed.current * 1.5) * 0.002
    }

    // --- Micro head movement ---
    const head = vrm.humanoid?.getNormalizedBoneNode('head')
    if (head) {
      head.rotation.x = headBaseX.current + Math.sin(elapsed.current * 0.9) * 0.015
      head.rotation.y = headBaseY.current + Math.sin(elapsed.current * 0.57) * 0.02
    }
  })
}

function randomBlinkDelay(): number {
  return 2000 + Math.random() * 4000
}
