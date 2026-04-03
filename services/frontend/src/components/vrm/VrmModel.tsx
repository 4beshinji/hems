import { useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import type { VRM } from '@pixiv/three-vrm'
import { useVrmLoader } from './useVrmLoader'
import { useMotionPlayer } from './useMotionPlayer'
import { useLipSync } from './useLipSync'
import { useIdleAnimations } from './useIdleAnimations'
import { useExpressionMapping } from './useExpressionMapping'

interface Props {
  modelPath: string
  onLoadError: () => void
}

export default function VrmModel({ modelPath, onLoadError }: Props) {
  const { vrm, error } = useVrmLoader(modelPath)
  const vrmRef = useRef<VRM | null>(null)
  const notifiedError = useRef(false)

  useEffect(() => {
    vrmRef.current = vrm
  }, [vrm])

  useEffect(() => {
    if (error && !notifiedError.current) {
      notifiedError.current = true
      onLoadError()
    }
  }, [error, onLoadError])

  const { isPlayingMotion } = useMotionPlayer(vrm)
  useLipSync(vrm)
  useIdleAnimations(vrm, isPlayingMotion)
  useExpressionMapping(vrm)

  useFrame((_, delta) => {
    if (vrmRef.current) {
      vrmRef.current.update(delta)
    }
  })

  if (!vrm) return null

  return <primitive object={vrm.scene} />
}
