import { useState, useEffect, useRef } from 'react'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import type { VRM } from '@pixiv/three-vrm'

/** Dispose all three.js GPU resources held by a VRM scene. */
function disposeVrm(vrm: VRM): void {
  VRMUtils.deepDispose(vrm.scene)
}

export function useVrmLoader(path: string) {
  const [vrm, setVrm] = useState<VRM | null>(null)
  const [error, setError] = useState<boolean>(false)
  const loaderRef = useRef<GLTFLoader | null>(null)
  // Keep a ref to the currently mounted VRM so the cleanup closure can dispose
  // it without relying on React functional state updaters (which may not run
  // reliably during unmount in concurrent/strict mode).
  const vrmRef = useRef<VRM | null>(null)

  useEffect(() => {
    if (!loaderRef.current) {
      loaderRef.current = new GLTFLoader()
      loaderRef.current.register((parser) => new VRMLoaderPlugin(parser))
    }

    // Cancelled flag: if path changes while a load is in flight, ignore the
    // stale result instead of calling setVrm on an already-cleaned-up effect.
    let cancelled = false

    // Dispose any previously loaded VRM before starting the new load.
    if (vrmRef.current) {
      disposeVrm(vrmRef.current)
      vrmRef.current = null
    }
    setVrm(null)
    setError(false)

    loaderRef.current.load(
      path,
      (gltf) => {
        if (cancelled) {
          // Load finished after path changed — dispose immediately without
          // ever mounting the VRM so no resources leak.
          const stale = gltf.userData.vrm as VRM | undefined
          if (stale) disposeVrm(stale)
          return
        }
        const vrmData = gltf.userData.vrm as VRM | undefined
        if (vrmData) {
          vrmData.scene.rotation.y = Math.PI
          vrmRef.current = vrmData
          setVrm(vrmData)
        } else {
          setError(true)
        }
      },
      undefined,
      () => {
        if (!cancelled) setError(true)
      },
    )

    return () => {
      cancelled = true
      // Dispose on unmount or before the next path's effect runs.
      if (vrmRef.current) {
        disposeVrm(vrmRef.current)
        vrmRef.current = null
      }
      setVrm(null)
    }
  }, [path])

  return { vrm, error }
}
