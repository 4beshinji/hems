import { useRef, useCallback } from 'react'

export interface WanderState {
  x: number       // 0-1 screen position (left-right)
  y: number       // 0-1 screen position (top-bottom, 0=top)
  facing: 1 | -1  // 1 = right, -1 = left
  phase: 'idle' | 'walking'
}

const WALK_SPEED = 0.08   // fraction of screen per second
const IDLE_MIN = 3000
const IDLE_MAX = 8000
const MARGIN = 0.05       // stay away from edges

function randomTarget(): { x: number; y: number } {
  return {
    x: MARGIN + Math.random() * (1 - 2 * MARGIN),
    y: 0.55 + Math.random() * 0.35,  // bottom half of screen (0.55-0.90)
  }
}

function randomIdleDuration(): number {
  return IDLE_MIN + Math.random() * (IDLE_MAX - IDLE_MIN)
}

export function useWandering() {
  const state = useRef<WanderState>({
    x: 0.5 + (Math.random() - 0.5) * 0.3,
    y: 0.75,
    facing: 1,
    phase: 'idle',
  })

  const target = useRef(randomTarget())
  const idleUntil = useRef(performance.now() + randomIdleDuration())
  const lastUpdate = useRef(performance.now())

  const update = useCallback((): WanderState => {
    const now = performance.now()
    const dt = (now - lastUpdate.current) / 1000
    lastUpdate.current = now
    const s = state.current

    if (s.phase === 'idle') {
      if (now >= idleUntil.current) {
        target.current = randomTarget()
        s.phase = 'walking'
        const dx = target.current.x - s.x
        s.facing = dx >= 0 ? 1 : -1
      }
    }

    if (s.phase === 'walking') {
      const tx = target.current.x
      const ty = target.current.y
      const dx = tx - s.x
      const dy = ty - s.y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist < 0.01) {
        // Arrived
        s.x = tx
        s.y = ty
        s.phase = 'idle'
        idleUntil.current = now + randomIdleDuration()
      } else {
        const step = Math.min(WALK_SPEED * dt, dist)
        s.x += (dx / dist) * step
        s.y += (dy / dist) * step
        s.facing = dx >= 0 ? 1 : -1
      }
    }

    return { ...s }
  }, [])

  return { update, state }
}
