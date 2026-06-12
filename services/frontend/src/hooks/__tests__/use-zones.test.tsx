import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { makeQueryWrapper } from '@/test/test-utils'
import { useZones } from '@/hooks/queries/use-zones'
import { zoneFixtures } from '@/test/handlers'

describe('useZones', () => {
  it('fetches and returns zone list', async () => {
    const { result } = renderHook(() => useZones(), {
      wrapper: makeQueryWrapper(),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(zoneFixtures.length)
    expect(result.current.data?.[0].zone_id).toBe('living')
    expect(result.current.data?.[0].environment.temperature).toBe(24.5)
    expect(result.current.data?.[0].occupancy.count).toBe(1)
  })

  it('returns bedroom zone with zero occupancy', async () => {
    const { result } = renderHook(() => useZones(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const bedroom = result.current.data?.find((z) => z.zone_id === 'bedroom')
    expect(bedroom).toBeDefined()
    expect(bedroom?.occupancy.count).toBe(0)
  })

  it('enters error state on server failure', async () => {
    server.use(
      http.get('/api/zones/', () =>
        new HttpResponse('Internal Server Error', { status: 500 })
      )
    )

    const { result } = renderHook(() => useZones(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })
})
