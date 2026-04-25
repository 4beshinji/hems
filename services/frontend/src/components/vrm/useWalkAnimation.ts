import { useRef, useEffect, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { VRM } from '@pixiv/three-vrm'
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import type { WalkPhase } from './VrmCanvas'

/**
 * User-specified walk animation file.
 * Place a .vrma file at this path to override procedural walk.
 */
const WALK_ANIM_PATH = '/models/motions/walk.vrma'

const FACING_LERP_SPEED = 8
const BLEND_IN_SPEED = 4
const BLEND_OUT_SPEED = 2

// Procedural fallback constants
const WALK_CYCLE_SPEED = 6
const UPPER_LEG_SWING = 0.4
const LOWER_LEG_BEND = 0.5
const UPPER_ARM_SWING = 0.15
const SPINE_SWAY = 0.02

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function useWalkAnimation(
  vrm: VRM | null,
  walkPhase?: WalkPhase,
  facing?: 1 | -1,
  faceCameraOverride?: boolean,
) {
  const currentFacingAngle = useRef(Math.PI)
  const walkWeight = useRef(0)
  const isWalking = walkPhase === 'walking'

  // --- .vrma walk animation ---
  const [hasCustomWalk, setHasCustomWalk] = useState(false)
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)
  const actionRef = useRef<THREE.AnimationAction | null>(null)
  const loaderRef = useRef<GLTFLoader | null>(null)
  const clipRef = useRef<THREE.AnimationClip | null>(null)
  const loadAttempted = useRef(false)

  // Init loader
  useEffect(() => {
    const loader = new GLTFLoader()
    loader.register((parser) => new VRMAnimationLoaderPlugin(parser))
    loaderRef.current = loader
  }, [])

  // Init mixer
  useEffect(() => {
    if (!vrm) return
    const mixer = new THREE.AnimationMixer(vrm.scene)
    mixerRef.current = mixer
    return () => {
      mixer.stopAllAction()
      mixerRef.current = null
    }
  }, [vrm])

  // Try to load custom walk.vrma
  useEffect(() => {
    if (!vrm || !loaderRef.current || loadAttempted.current) return
    loadAttempted.current = true

    loaderRef.current.load(
      WALK_ANIM_PATH,
      (gltf) => {
        const anims = gltf.userData.vrmAnimations
        if (!anims?.length) return
        clipRef.current = createVRMAnimationClip(anims[0], vrm)
        setHasCustomWalk(true)
      },
      undefined,
      () => {
        // File not found — use procedural fallback
        setHasCustomWalk(false)
      },
    )
  }, [vrm])

  // Play/stop custom walk animation based on phase
  useEffect(() => {
    if (!hasCustomWalk || !mixerRef.current || !clipRef.current) return

    if (isWalking) {
      // Start or resume
      if (!actionRef.current) {
        const action = mixerRef.current.clipAction(clipRef.current)
        action.loop = THREE.LoopRepeat
        action.reset().fadeIn(0.4).play()
        actionRef.current = action
      } else if (!actionRef.current.isRunning()) {
        actionRef.current.reset().fadeIn(0.4).play()
      }
    } else {
      // Fade out
      if (actionRef.current?.isRunning()) {
        actionRef.current.fadeOut(0.5)
        // Clear ref after fadeout completes so it can be re-created
        const action = actionRef.current
        setTimeout(() => {
          if (actionRef.current === action) {
            actionRef.current = null
          }
        }, 600)
      }
    }
  }, [isWalking, hasCustomWalk])

  // --- Procedural fallback state ---
  const elapsed = useRef(0)
  const restPose = useRef<Record<string, number>>({})
  const initialized = useRef(false)

  useFrame((_, delta) => {
    if (!vrm?.humanoid) return

    // --- Facing direction (always active) ---
    // ポーズ再生中はカメラ正面 (Math.PI) に向き直す
    if (faceCameraOverride) {
      const targetAngle = Math.PI
      currentFacingAngle.current += (targetAngle - currentFacingAngle.current) * Math.min(1, FACING_LERP_SPEED * delta)
      vrm.scene.rotation.y = currentFacingAngle.current
    } else if (facing != null) {
      const targetAngle = facing === -1 ? Math.PI * 0.65 : Math.PI * 1.35
      currentFacingAngle.current += (targetAngle - currentFacingAngle.current) * Math.min(1, FACING_LERP_SPEED * delta)
      vrm.scene.rotation.y = currentFacingAngle.current
    }

    // --- Custom walk: mixer update only ---
    if (hasCustomWalk) {
      mixerRef.current?.update(delta)
      return
    }

    // --- Procedural walk fallback ---
    const h = vrm.humanoid

    if (!initialized.current) {
      const bones = [
        'leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg',
        'leftUpperArm', 'rightUpperArm', 'spine',
      ] as const
      for (const name of bones) {
        const node = h.getNormalizedBoneNode(name)
        if (node) {
          restPose.current[`${name}_x`] = node.rotation.x
          restPose.current[`${name}_z`] = node.rotation.z
        }
      }
      initialized.current = true
    }

    const targetWeight = isWalking ? 1 : 0
    const blendSpeed = isWalking ? BLEND_IN_SPEED : BLEND_OUT_SPEED
    walkWeight.current += (targetWeight - walkWeight.current) * Math.min(1, blendSpeed * delta)

    if (walkWeight.current < 0.001) {
      walkWeight.current = 0
      elapsed.current = 0
      return
    }

    const w = walkWeight.current
    elapsed.current += delta
    const t = elapsed.current * WALK_CYCLE_SPEED
    const sin = Math.sin(t)
    const cos = Math.cos(t)
    const rest = restPose.current

    const leftUpperLeg = h.getNormalizedBoneNode('leftUpperLeg')
    const rightUpperLeg = h.getNormalizedBoneNode('rightUpperLeg')
    if (leftUpperLeg) leftUpperLeg.rotation.x = lerp(rest['leftUpperLeg_x'] ?? 0, sin * UPPER_LEG_SWING, w)
    if (rightUpperLeg) rightUpperLeg.rotation.x = lerp(rest['rightUpperLeg_x'] ?? 0, -sin * UPPER_LEG_SWING, w)

    const leftLowerLeg = h.getNormalizedBoneNode('leftLowerLeg')
    const rightLowerLeg = h.getNormalizedBoneNode('rightLowerLeg')
    if (leftLowerLeg) leftLowerLeg.rotation.x = lerp(rest['leftLowerLeg_x'] ?? 0, Math.max(0, -sin) * LOWER_LEG_BEND, w)
    if (rightLowerLeg) rightLowerLeg.rotation.x = lerp(rest['rightLowerLeg_x'] ?? 0, Math.max(0, sin) * LOWER_LEG_BEND, w)

    const leftUpperArm = h.getNormalizedBoneNode('leftUpperArm')
    const rightUpperArm = h.getNormalizedBoneNode('rightUpperArm')
    if (leftUpperArm) leftUpperArm.rotation.x = lerp(rest['leftUpperArm_x'] ?? 0, -sin * UPPER_ARM_SWING, w)
    if (rightUpperArm) rightUpperArm.rotation.x = lerp(rest['rightUpperArm_x'] ?? 0, sin * UPPER_ARM_SWING, w)

    const spine = h.getNormalizedBoneNode('spine')
    if (spine) spine.rotation.z = lerp(rest['spine_z'] ?? 0, cos * SPINE_SWAY, w)
  })

  return { isWalking: isWalking || walkWeight.current > 0.01 }
}
