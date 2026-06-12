import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { makeQueryWrapper } from '@/test/test-utils'
import { useVoiceEvents } from '@/hooks/queries/use-voice-events'
import { voiceEventFixtures } from '@/test/handlers'

describe('useVoiceEvents', () => {
  it('returns data on success', async () => {
    const { result } = renderHook(() => useVoiceEvents(), {
      wrapper: makeQueryWrapper(),
    })

    // Initial loading state
    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(voiceEventFixtures.length)
    expect(result.current.data?.[0].id).toBe(1)
    expect(result.current.data?.[0].message).toBe('おはようございます')
  })

  it('enters error state on server failure', async () => {
    server.use(
      http.get('/api/voice-events/recent', () =>
        new HttpResponse('Service Unavailable', { status: 503 })
      )
    )

    const { result } = renderHook(() => useVoiceEvents(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })

  it('is not loading after data arrives', async () => {
    const { result } = renderHook(() => useVoiceEvents(), {
      wrapper: makeQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.isLoading).toBe(false)
  })
})
