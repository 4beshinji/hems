import { useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import type { VRM } from '@pixiv/three-vrm'
import { useVrmLoader } from './useVrmLoader'
import { useMotionPlayer } from './useMotionPlayer'
import { useLipSync } from './useLipSync'
import { useIdleAnimations } from './useIdleAnimations'
import { useExpressionMapping } from './useExpressionMapping'
import { useWalkAnimation } from './useWalkAnimation'
import { useIdleMotionPlayer } from './useIdleMotionPlayer'
import type { WalkPhase } from './VrmCanvas'

/** Apply a natural rest pose (arms down) to a T-pose VRM */
function applyRestPose(vrm: VRM) {
  const humanoid = vrm.humanoid
  if (!humanoid) return

  // Rotate upper arms down (~70 deg toward body)
  const leftUpper = humanoid.getNormalizedBoneNode('leftUpperArm')
  const rightUpper = humanoid.getNormalizedBoneNode('rightUpperArm')
  if (leftUpper) leftUpper.rotation.z = 1.2
  if (rightUpper) rightUpper.rotation.z = -1.2

  // Slight bend in lower arms
  const leftLower = humanoid.getNormalizedBoneNode('leftLowerArm')
  const rightLower = humanoid.getNormalizedBoneNode('rightLowerArm')
  if (leftLower) leftLower.rotation.z = 0.08
  if (rightLower) rightLower.rotation.z = -0.08
}

interface Props {
  modelPath: string
  onLoadError: () => void
  walkPhase?: WalkPhase
  facing?: 1 | -1
}

export default function VrmModel({ modelPath, onLoadError, walkPhase, facing }: Props) {
  const { vrm, error } = useVrmLoader(modelPath)
  const vrmRef = useRef<VRM | null>(null)
  const notifiedError = useRef(false)

  useEffect(() => {
    vrmRef.current = vrm
    if (vrm) applyRestPose(vrm)
  }, [vrm])

  useEffect(() => {
    if (error && !notifiedError.current) {
      notifiedError.current = true
      onLoadError()
    }
  }, [error, onLoadError])

  const { isPlayingMotion } = useMotionPlayer(vrm)
  const { isWalking } = useWalkAnimation(vrm, walkPhase, facing)
  const { isPlayingIdleMotion } = useIdleMotionPlayer(vrm, walkPhase)
  useLipSync(vrm)
  useIdleAnimations(vrm, isPlayingMotion || isWalking || isPlayingIdleMotion)
  useExpressionMapping(vrm)

  useFrame((_, delta) => {
    if (vrmRef.current) {
      vrmRef.current.update(delta)
    }
  })

  if (!vrm) return null

  return <primitive object={vrm.scene} />
}
