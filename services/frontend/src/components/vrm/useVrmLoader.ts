import { useState, useEffect, useRef } from 'react'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin } from '@pixiv/three-vrm'
import type { VRM } from '@pixiv/three-vrm'

export function useVrmLoader(path: string) {
  const [vrm, setVrm] = useState<VRM | null>(null)
  const [error, setError] = useState<boolean>(false)
  const loaderRef = useRef<GLTFLoader | null>(null)

  useEffect(() => {
    if (!loaderRef.current) {
      loaderRef.current = new GLTFLoader()
      loaderRef.current.register((parser) => new VRMLoaderPlugin(parser))
    }

    setVrm(null)
    setError(false)

    loaderRef.current.load(
      path,
      (gltf) => {
        const vrmData = gltf.userData.vrm as VRM | undefined
        if (vrmData) {
          vrmData.scene.rotation.y = Math.PI
          setVrm(vrmData)
        } else {
          setError(true)
        }
      },
      undefined,
      () => setError(true),
    )

    return () => { setVrm(null) }
  }, [path])

  return { vrm, error }
}
