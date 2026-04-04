import { lazy, Suspense, useRef, useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { User } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'

const VrmCanvas = lazy(() => import('./VrmCanvas'))

export default function AvatarPanel() {
  const anchorRef = useRef<HTMLDivElement>(null)
  const [style, setStyle] = useState<React.CSSProperties>({ display: 'none' })
  const [fovScale, setFovScale] = useState(1)
  const [viewOffsetY, setViewOffsetY] = useState(0)

  useEffect(() => {
    const el = anchorRef.current
    if (!el) return

    const update = () => {
      const rect = el.getBoundingClientRect()

      // Bottom edge fixed to anchor bottom, extend upward
      const mulW = 3
      const mulH = 4
      const canvasW = rect.width * mulW
      const canvasH = rect.height * mulH
      const cx = rect.left + rect.width / 2
      const bottom = rect.bottom

      setStyle({
        position: 'fixed',
        left: cx - canvasW / 2,
        top: bottom - canvasH,
        width: canvasW,
        height: canvasH,
        pointerEvents: 'none',
        zIndex: 5,
      })
      setFovScale(mulH)
      // Canvas center is above anchor center by (mulH-1)/2 * anchorH pixels.
      // Shift view downward so avatar renders at anchor position.
      setViewOffsetY(-(mulH - 1) / 2 * rect.height)
    }

    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    window.addEventListener('scroll', update, { passive: true, capture: true })
    window.addEventListener('resize', update, { passive: true })

    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', update, true)
      window.removeEventListener('resize', update)
    }
  }, [])

  return (
    <>
      <Card className="flex flex-col">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <User className="h-4 w-4 text-primary" />
            Avatar
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 min-h-0">
          <div ref={anchorRef} className="w-full aspect-[3/4]" />
        </CardContent>
      </Card>

      <div style={style}>
        <Suspense fallback={<Skeleton className="w-full h-full" />}>
          <VrmCanvas className="w-full h-full" cameraPreset="bust" fovScale={fovScale} viewOffsetY={viewOffsetY} />
        </Suspense>
      </div>
    </>
  )
}
