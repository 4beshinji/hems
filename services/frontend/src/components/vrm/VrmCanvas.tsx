import { Suspense, useState, useCallback, useEffect, useRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import VrmModel from './VrmModel'
import AvatarPlaceholder from './AvatarPlaceholder'

export type WalkPhase = 'idle' | 'walking'
export type CameraPreset = 'fullbody' | 'bust'

const CAMERA_PRESETS: Record<CameraPreset, {
  position: [number, number, number]
  lookAt: [number, number, number]
  fov: number
}> = {
  fullbody: { position: [0, 1.1, 3.5], lookAt: [0, 0.8, 0], fov: 30 },
  bust:     { position: [0, 1.5, 0.8], lookAt: [0, 1.4, 0], fov: 32 },
}

/**
 * @param fovScale  - FOV multiplier (canvas is fovScale× taller than anchor)
 * @param viewOffsetY - vertical pixel offset to shift avatar from canvas center to anchor center
 */
function CameraSetup({ preset, fovScale = 1, viewOffsetY = 0 }: {
  preset: CameraPreset; fovScale?: number; viewOffsetY?: number
}) {
  const { camera, gl } = useThree()
  useEffect(() => {
    const cfg = CAMERA_PRESETS[preset]
    const cam = camera as THREE.PerspectiveCamera
    cam.position.set(...cfg.position)
    cam.lookAt(new THREE.Vector3(...cfg.lookAt))
    cam.fov = cfg.fov * fovScale

    if (viewOffsetY !== 0) {
      const w = gl.domElement.clientWidth
      const h = gl.domElement.clientHeight
      cam.setViewOffset(w, h, 0, viewOffsetY, w, h)
    } else {
      cam.clearViewOffset()
    }
    cam.updateProjectionMatrix()
  }, [camera, gl, preset, fovScale, viewOffsetY])
  return null
}

interface Props {
  className?: string
  modelPath?: string
  walkPhase?: WalkPhase
  facing?: 1 | -1
  cameraPreset?: CameraPreset
  fovScale?: number
  viewOffsetY?: number
}

const DEFAULT_MODEL = '/models/avatar.vrm'

export default function VrmCanvas({
  className, modelPath, walkPhase, facing,
  cameraPreset = 'fullbody', fovScale, viewOffsetY,
}: Props) {
  const [usePlaceholder, setUsePlaceholder] = useState(false)
  const path = modelPath || DEFAULT_MODEL

  const handleLoadError = useCallback(() => {
    setUsePlaceholder(true)
  }, [])

  if (usePlaceholder) {
    return <AvatarPlaceholder className={className} />
  }

  return (
    <div className={className}>
      <Canvas
        camera={{ near: 0.01 }}
        dpr={[1, 1.5]}
        gl={{ alpha: true, antialias: true, powerPreference: 'default' }}
        style={{ background: 'transparent' }}
      >
        <CameraSetup preset={cameraPreset} fovScale={fovScale} viewOffsetY={viewOffsetY} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[1, 2, 2]} intensity={0.8} />
        <Suspense fallback={null}>
          <VrmModel
            modelPath={path}
            onLoadError={handleLoadError}
            walkPhase={walkPhase}
            facing={facing}
          />
        </Suspense>
      </Canvas>
    </div>
  )
}
