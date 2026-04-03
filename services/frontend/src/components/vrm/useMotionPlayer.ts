import { useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { VRM } from '@pixiv/three-vrm'
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { useAudioAnalyser } from '@/audio'
import { getMotionMeta } from '@/lib/motion-registry'

export function useMotionPlayer(vrm: VRM | null) {
  const { currentMotionId } = useAudioAnalyser()
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)
  const currentActionRef = useRef<THREE.AnimationAction | null>(null)
  const loaderRef = useRef<GLTFLoader | null>(null)
  const isPlayingRef = useRef(false)
  const lastMotionIdRef = useRef<string | null>(null)
  const cacheRef = useRef(new Map<string, THREE.AnimationClip>())
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Initialize mixer when VRM loads
  useEffect(() => {
    if (!vrm) return
    const mixer = new THREE.AnimationMixer(vrm.scene)
    mixerRef.current = mixer
    return () => {
      mixer.stopAllAction()
      mixerRef.current = null
    }
  }, [vrm])

  // Initialize loader with VRMAnimation plugin
  useEffect(() => {
    const loader = new GLTFLoader()
    loader.register((parser) => new VRMAnimationLoaderPlugin(parser))
    loaderRef.current = loader
  }, [])

  // React to motion_id changes
  useEffect(() => {
    if (!vrm || !mixerRef.current || !currentMotionId) return
    if (currentMotionId === lastMotionIdRef.current) return

    lastMotionIdRef.current = currentMotionId
    const meta = getMotionMeta(currentMotionId)
    if (!meta) return

    const playMotion = (clip: THREE.AnimationClip) => {
      const mixer = mixerRef.current!
      const action = mixer.clipAction(clip)
      action.clampWhenFinished = true
      action.loop = THREE.LoopOnce

      // Crossfade from current action
      if (currentActionRef.current && currentActionRef.current.isRunning()) {
        currentActionRef.current.crossFadeTo(action, 0.3, true)
        action.reset().play()
      } else {
        action.reset().fadeIn(0.3).play()
      }

      currentActionRef.current = action
      isPlayingRef.current = true

      // After duration, fade out
      clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => {
        if (currentActionRef.current === action) {
          action.fadeOut(0.4)
          isPlayingRef.current = false
          currentActionRef.current = null
          lastMotionIdRef.current = null
        }
      }, meta.duration * 1000)
    }

    // Check cache
    const cached = cacheRef.current.get(currentMotionId)
    if (cached) {
      playMotion(cached)
      return
    }

    // Load .vrma file
    loaderRef.current?.load(
      meta.file,
      (gltf) => {
        const vrmAnimations = gltf.userData.vrmAnimations
        if (!vrmAnimations?.length || !vrm) return
        const clip = createVRMAnimationClip(vrmAnimations[0], vrm)
        cacheRef.current.set(currentMotionId, clip)
        playMotion(clip)
      },
      undefined,
      () => {
        console.warn(`Failed to load motion: ${currentMotionId}`)
      },
    )
  }, [vrm, currentMotionId])

  // Update mixer each frame
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

  return { isPlayingMotion: isPlayingRef.current }
}
