import { Suspense, useState, useCallback } from 'react'
import { Canvas } from '@react-three/fiber'
import VrmModel from './VrmModel'
import AvatarPlaceholder from './AvatarPlaceholder'

interface Props {
  className?: string
  modelPath?: string
}

const DEFAULT_MODEL = '/models/avatar.vrm'

export default function VrmCanvas({ className, modelPath }: Props) {
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
        camera={{ position: [0, 1.35, 0.8], fov: 30 }}
        dpr={[1, 1.5]}
        gl={{ alpha: true, antialias: true, powerPreference: 'default' }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.7} />
        <directionalLight position={[1, 2, 2]} intensity={0.8} />
        <Suspense fallback={null}>
          <VrmModel modelPath={path} onLoadError={handleLoadError} />
        </Suspense>
      </Canvas>
    </div>
  )
}
