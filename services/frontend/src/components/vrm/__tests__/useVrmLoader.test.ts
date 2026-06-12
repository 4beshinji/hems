/**
 * W5.3 — VRM resource-disposal tests
 *
 * Three.js WebGL APIs are not available in jsdom.  We mock GLTFLoader to
 * return a fake GLTF synchronously, and mock VRMUtils.deepDispose to spy on
 * calls.  Tests verify that unmounting or changing the model path causes
 * deepDispose to be called on the previously-loaded VRM scene.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// ── Module mocks ──────────────────────────────────────────────────────────────
// vi.mock factories are hoisted above imports, so they cannot reference
// variables defined outside them.  We expose state via module-level objects
// that are mutated by each test through module imports.

vi.mock('three/examples/jsm/loaders/GLTFLoader.js', () => {
  // Shared mutable config that tests override per-call via __setNextScene
  const state: { nextScene: object | null } = { nextScene: null }

  const loaderInstance = {
    register: vi.fn(),
    load: vi.fn((_path: string, onLoad: (g: unknown) => void) => {
      if (state.nextScene !== null) {
        onLoad({ userData: { vrm: { scene: state.nextScene } } })
      }
    }),
  }

  function GLTFLoader(this: typeof loaderInstance) {
    return loaderInstance
  }

  return { GLTFLoader, __loaderInstance: loaderInstance, __state: state }
})

vi.mock('@pixiv/three-vrm', () => ({
  VRMLoaderPlugin: vi.fn(),
  VRMUtils: { deepDispose: vi.fn() },
}))

// ── Imports after mocks ────────────────────────────────────────────────────────
import { useVrmLoader } from '../useVrmLoader'
import * as GltfModule from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMUtils } from '@pixiv/three-vrm'

// Cast to access the internal test helpers exposed by the mock
const gltfMock = GltfModule as unknown as {
  __loaderInstance: {
    register: Mock
    load: Mock
  }
  __state: { nextScene: object | null }
}

const deepDispose = VRMUtils.deepDispose as Mock

function makeScene() {
  return { rotation: { y: 0 }, traverse: vi.fn() }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useVrmLoader – W5.3 resource disposal', () => {
  beforeEach(() => {
    deepDispose.mockClear()
    gltfMock.__loaderInstance.load.mockClear()
    gltfMock.__loaderInstance.register.mockClear()
    gltfMock.__state.nextScene = null
  })

  it('loads a VRM and sets scene.rotation.y = Math.PI', () => {
    const scene = makeScene()
    gltfMock.__state.nextScene = scene

    const { result } = renderHook(() => useVrmLoader('/model.vrm'))

    expect(result.current.vrm).not.toBeNull()
    expect(scene.rotation.y).toBe(Math.PI)
    expect(result.current.error).toBe(false)
  })

  it('calls VRMUtils.deepDispose on the scene when the hook unmounts', () => {
    const scene = makeScene()
    gltfMock.__state.nextScene = scene

    const { result, unmount } = renderHook(() => useVrmLoader('/model.vrm'))

    expect(result.current.vrm).not.toBeNull()
    expect(deepDispose).not.toHaveBeenCalled()

    act(() => { unmount() })

    expect(deepDispose).toHaveBeenCalledTimes(1)
    expect(deepDispose).toHaveBeenCalledWith(scene)
  })

  it('disposes the old VRM and loads the new one when path changes', () => {
    const sceneA = makeScene()
    const sceneB = makeScene()
    let callCount = 0

    gltfMock.__loaderInstance.load.mockImplementation(
      (_path: string, onLoad: (g: unknown) => void) => {
        callCount++
        onLoad({ userData: { vrm: { scene: callCount === 1 ? sceneA : sceneB } } })
      },
    )

    const { result, rerender } = renderHook(
      ({ path }: { path: string }) => useVrmLoader(path),
      { initialProps: { path: '/model-a.vrm' } },
    )

    expect(result.current.vrm?.scene).toBe(sceneA)
    expect(deepDispose).not.toHaveBeenCalled()

    // Path change: cleanup of the first effect fires, disposing sceneA
    act(() => { rerender({ path: '/model-b.vrm' }) })

    expect(deepDispose).toHaveBeenCalledWith(sceneA)
    expect(result.current.vrm?.scene).toBe(sceneB)
  })

  it('sets error=true when gltf has no vrm data, without calling deepDispose', () => {
    gltfMock.__loaderInstance.load.mockImplementationOnce(
      (_path: string, onLoad: (g: unknown) => void) => {
        onLoad({ userData: {} }) // no .vrm key
      },
    )

    const { result } = renderHook(() => useVrmLoader('/bad.vrm'))

    expect(result.current.vrm).toBeNull()
    expect(result.current.error).toBe(true)
    expect(deepDispose).not.toHaveBeenCalled()
  })

  it('sets error=true on load failure, without calling deepDispose', () => {
    gltfMock.__loaderInstance.load.mockImplementationOnce(
      (_p: string, _onLoad: unknown, _onProgress: unknown, onError: () => void) => {
        onError()
      },
    )

    const { result } = renderHook(() => useVrmLoader('/missing.vrm'))

    expect(result.current.error).toBe(true)
    expect(deepDispose).not.toHaveBeenCalled()
  })
})
