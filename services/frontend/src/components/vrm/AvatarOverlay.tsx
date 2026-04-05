import { lazy, Suspense, useState, useEffect, useRef } from 'react'
import { useWandering, type WanderState } from './useWandering'

const VrmCanvas = lazy(() => import('./VrmCanvas'))

interface Props {
  onClose?: () => void
}

const AVATAR_W = 420
const AVATAR_H = 840

export default function AvatarOverlay(_props: Props) {
  const { update } = useWandering()
  const [pos, setPos] = useState<WanderState>({ x: 0.5, y: 0.75, facing: 1, phase: 'idle' })
  const rafRef = useRef(0)

  useEffect(() => {
    const tick = () => {
      setPos(update())
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [update])

  const left = `calc(${pos.x * 100}% - ${AVATAR_W / 2}px)`
  const top = `calc(${pos.y * 100}% - ${AVATAR_H / 2}px)`

  return (
    <div className="fixed inset-0 z-50 pointer-events-none overflow-hidden">
      <div
        className="absolute"
        style={{ left, top, width: AVATAR_W, height: AVATAR_H }}
      >
        <div className="w-full h-full">
          <Suspense fallback={null}>
            <VrmCanvas
              className="w-full h-full"
              walkPhase={pos.phase}
              facing={pos.facing}
            />
          </Suspense>
        </div>
      </div>
    </div>
  )
}
