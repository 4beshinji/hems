import { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWandering, type WanderState } from './useWandering'

const VrmCanvas = lazy(() => import('./VrmCanvas'))

interface Props {
  onClose: () => void
}

const AVATAR_W = 420
const AVATAR_H = 840

export default function AvatarOverlay({ onClose }: Props) {
  const { update } = useWandering()
  const [pos, setPos] = useState<WanderState>({ x: 0.5, y: 0.75, facing: 1, phase: 'idle' })
  const rafRef = useRef(0)
  const [hovered, setHovered] = useState(false)

  useEffect(() => {
    const tick = () => {
      setPos(update())
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [update])

  const handleMouseEnter = useCallback(() => setHovered(true), [])
  const handleMouseLeave = useCallback(() => setHovered(false), [])

  const left = `calc(${pos.x * 100}% - ${AVATAR_W / 2}px)`
  const top = `calc(${pos.y * 100}% - ${AVATAR_H / 2}px)`

  return (
    <div className="fixed inset-0 z-50 pointer-events-none overflow-hidden">
      <div
        className="absolute"
        style={{
          left,
          top,
          width: AVATAR_W,
          height: AVATAR_H,
          pointerEvents: 'auto',
        }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Close button — visible on hover */}
        <div
          className="absolute -top-2 right-0 z-10 transition-opacity duration-200"
          style={{ opacity: hovered ? 1 : 0 }}
        >
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-6 w-6 bg-black/40 hover:bg-black/60 text-white rounded-full"
            aria-label="アバターを閉じる"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
        {/* Avatar with walk bounce */}
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
