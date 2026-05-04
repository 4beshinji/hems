import { useRef, useEffect, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { VRM } from '@pixiv/three-vrm'
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { getMotionMeta } from '@/lib/motion-registry'
import type { WalkPhase } from './VrmCanvas'

// Idle motions to randomly play while standing still
const IDLE_MOTION_IDS = [
  'look_around', 'relax', 'sleepy', 'thinking_pose', 'model_pose',
]

const IDLE_MOTION_MIN_INTERVAL = 8000   // ms before next idle motion
const IDLE_MOTION_MAX_INTERVAL = 18000

function randomInterval(): number {
  return IDLE_MOTION_MIN_INTERVAL + Math.random() * (IDLE_MOTION_MAX_INTERVAL - IDLE_MOTION_MIN_INTERVAL)
}

function randomIdleMotion(): string {
  return IDLE_MOTION_IDS[Math.floor(Math.random() * IDLE_MOTION_IDS.length)]
}

export function useIdleMotionPlayer(
  vrm: VRM | null,
  walkPhase?: WalkPhase,
) {
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)
  const currentActionRef = useRef<THREE.AnimationAction | null>(null)
  const loaderRef = useRef<GLTFLoader | null>(null)
  const cacheRef = useRef(new Map<string, THREE.AnimationClip>())
  const nextIdleAt = useRef(performance.now() + randomInterval())
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [isPlayingIdleMotion, setIsPlayingIdleMotion] = useState(false)
  const isPlayingRef = useRef(false)

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

  // Init loader
  useEffect(() => {
    const loader = new GLTFLoader()
    loader.register((parser) => new VRMAnimationLoaderPlugin(parser))
    loaderRef.current = loader
  }, [])

  // Trigger idle motions periodically when not walking
  useEffect(() => {
    if (!vrm || !mixerRef.current) return

    const check = setInterval(() => {
      if (walkPhase === 'walking' || isPlayingRef.current) return
      if (performance.now() < nextIdleAt.current) return
      // mark in both ref (for setInterval guard) and state (for downstream effects)

      const motionId = randomIdleMotion()
      const meta = getMotionMeta(motionId)
      if (!meta) return

      const playClip = (clip: THREE.AnimationClip) => {
        const mixer = mixerRef.current!
        const action = mixer.clipAction(clip)
        action.clampWhenFinished = true
        action.loop = THREE.LoopOnce

        if (currentActionRef.current?.isRunning()) {
          currentActionRef.current.crossFadeTo(action, 0.5, true)
          action.reset().play()
        } else {
          action.reset().fadeIn(0.5).play()
        }

        currentActionRef.current = action
        isPlayingRef.current = true
        setIsPlayingIdleMotion(true)

        clearTimeout(timeoutRef.current)
        timeoutRef.current = setTimeout(() => {
          if (currentActionRef.current === action) {
            action.fadeOut(0.5)
            isPlayingRef.current = false
            setIsPlayingIdleMotion(false)
            currentActionRef.current = null
          }
          nextIdleAt.current = performance.now() + randomInterval()
        }, meta.duration * 1000)
      }

      const cached = cacheRef.current.get(motionId)
      if (cached) {
        playClip(cached)
        return
      }

      loaderRef.current?.load(
        meta.file,
        (gltf) => {
          const vrmAnimations = gltf.userData.vrmAnimations
          if (!vrmAnimations?.length || !vrm) return
          const clip = createVRMAnimationClip(vrmAnimations[0], vrm)
          cacheRef.current.set(motionId, clip)
          playClip(clip)
        },
        undefined,
        () => console.warn(`Failed to load idle motion: ${motionId}`),
      )
    }, 1000)

    return () => clearInterval(check)
  }, [vrm, walkPhase])

  // Stop motion when walking starts
  useEffect(() => {
    if (walkPhase === 'walking' && currentActionRef.current?.isRunning()) {
      currentActionRef.current.fadeOut(0.3)
      isPlayingRef.current = false
      setIsPlayingIdleMotion(false)
      currentActionRef.current = null
      clearTimeout(timeoutRef.current)
    }
  }, [walkPhase])

  // Update mixer
  useFrame((_, delta) => {
    mixerRef.current?.update(delta)
  })

  // Cleanup
  useEffect(() => {
    return () => {
      clearTimeout(timeoutRef.current)
      cacheRef.current.clear()
    }
  }, [])

  return { isPlayingIdleMotion }
}
