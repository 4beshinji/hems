/**
 * W5.4: Context Provider smoke tests.
 *
 * Each test verifies that:
 *  - The Provider renders without errors.
 *  - The corresponding use* hook returns the expected shape when called
 *    inside its Provider.
 *  - Calling the hook outside its Provider throws a descriptive error.
 */
import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { AudioProvider, useAudioContext } from '../AudioContext'
import { AvatarProvider, useAvatarContext } from '../AvatarContext'
import { SttProvider, useSttContext } from '../SttContext'
import { PowerProvider, usePowerContext } from '../PowerContext'
import { AppUiProvider, useAppUiContext } from '../AppUiContext'
import { QueryClientProvider } from '@tanstack/react-query'
import { createTestQueryClient } from '@/test/test-utils'

// ── AudioContext ──────────────────────────────────────────────────────────────

describe('AudioContext', () => {
  it('provides default values', () => {
    const { result } = renderHook(() => useAudioContext(), {
      wrapper: ({ children }) => <AudioProvider>{children}</AudioProvider>,
    })

    expect(result.current.audioEnabled).toBe(false)
    expect(typeof result.current.toggleAudio).toBe('function')
    expect(typeof result.current.enqueueAudio).toBe('function')
  })

  it('toggleAudio flips audioEnabled', () => {
    const { result } = renderHook(() => useAudioContext(), {
      wrapper: ({ children }) => <AudioProvider>{children}</AudioProvider>,
    })

    expect(result.current.audioEnabled).toBe(false)
    act(() => { result.current.toggleAudio() })
    expect(result.current.audioEnabled).toBe(true)
    act(() => { result.current.toggleAudio() })
    expect(result.current.audioEnabled).toBe(false)
  })

  it('throws when used outside provider', () => {
    expect(() =>
      renderHook(() => useAudioContext())
    ).toThrow('useAudioContext must be used within AudioProvider')
  })
})

// ── AvatarContext ─────────────────────────────────────────────────────────────

describe('AvatarContext', () => {
  it('provides avatarMode and cycle', () => {
    const { result } = renderHook(() => useAvatarContext(), {
      wrapper: ({ children }) => <AvatarProvider>{children}</AvatarProvider>,
    })

    // Default mode from use-avatar-mode (hidden for VRM, panel for PSD)
    expect(['hidden', 'panel', 'overlay']).toContain(result.current.avatarMode)
    expect(typeof result.current.cycleAvatarMode).toBe('function')
    expect(typeof result.current.hideAvatar).toBe('function')
  })

  it('hideAvatar sets mode to hidden', () => {
    const { result } = renderHook(() => useAvatarContext(), {
      wrapper: ({ children }) => <AvatarProvider>{children}</AvatarProvider>,
    })

    act(() => { result.current.hideAvatar() })
    expect(result.current.avatarMode).toBe('hidden')
  })

  it('throws when used outside provider', () => {
    expect(() =>
      renderHook(() => useAvatarContext())
    ).toThrow('useAvatarContext must be used within AvatarProvider')
  })
})

// ── SttContext ────────────────────────────────────────────────────────────────

describe('SttContext', () => {
  it('provides sttMode and related state', () => {
    const { result } = renderHook(() => useSttContext(), {
      wrapper: ({ children }) => <SttProvider>{children}</SttProvider>,
    })

    expect(['push-to-talk', 'auto', 'off']).toContain(result.current.sttMode)
    expect(typeof result.current.cycleSTTMode).toBe('function')
    expect(typeof result.current.sttLanguage).toBe('string')
    expect(typeof result.current.sttAutoSend).toBe('boolean')
    expect(typeof result.current.toggleSTTAutoSend).toBe('function')
  })

  it('toggleSTTAutoSend flips sttAutoSend', () => {
    const { result } = renderHook(() => useSttContext(), {
      wrapper: ({ children }) => <SttProvider>{children}</SttProvider>,
    })

    const before = result.current.sttAutoSend
    act(() => { result.current.toggleSTTAutoSend() })
    expect(result.current.sttAutoSend).toBe(!before)
  })

  it('throws when used outside provider', () => {
    expect(() =>
      renderHook(() => useSttContext())
    ).toThrow('useSttContext must be used within SttProvider')
  })
})

// ── PowerContext ──────────────────────────────────────────────────────────────

describe('PowerContext', () => {
  it('provides powerMode and cyclePowerMode', () => {
    const qc = createTestQueryClient()
    const { result } = renderHook(() => usePowerContext(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={qc}>
          <PowerProvider>{children}</PowerProvider>
        </QueryClientProvider>
      ),
    })

    expect(['normal', 'sleep', 'away']).toContain(result.current.powerMode)
    expect(typeof result.current.cyclePowerMode).toBe('function')
    expect(typeof result.current.powerModePending).toBe('boolean')
  })

  it('throws when used outside provider', () => {
    expect(() =>
      renderHook(() => usePowerContext())
    ).toThrow('usePowerContext must be used within PowerProvider')
  })
})

// ── AppUiContext ──────────────────────────────────────────────────────────────

describe('AppUiContext', () => {
  it('provides darkModePreference and character theme state', () => {
    const { result } = renderHook(() => useAppUiContext(), {
      wrapper: ({ children }) => <AppUiProvider>{children}</AppUiProvider>,
    })

    expect(['sensor', 'light', 'dark']).toContain(result.current.darkModePreference)
    expect(typeof result.current.cycleDarkMode).toBe('function')
    expect(typeof result.current.isSecretActive).toBe('boolean')
    expect(typeof result.current.cycleCharacterTheme).toBe('function')
    // Default: no secret theme active
    expect(result.current.isSecretActive).toBe(false)
    expect(result.current.activeConfig).toBeNull()
  })

  it('throws when used outside provider', () => {
    expect(() =>
      renderHook(() => useAppUiContext())
    ).toThrow('useAppUiContext must be used within AppUiProvider')
  })
})
