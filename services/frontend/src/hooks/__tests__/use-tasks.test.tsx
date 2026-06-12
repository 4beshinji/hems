import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { makeQueryWrapper } from '@/test/test-utils'
import { useTasks, useTaskStats } from '@/hooks/queries/use-tasks'
import { taskFixtures, statsFixture } from '@/test/handlers'

describe('useTasks', () => {
  it('fetches and returns task list', async () => {
    const { result } = renderHook(() => useTasks(), {
      wrapper: makeQueryWrapper(),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(taskFixtures.length)
    expect(result.current.data?.[0].title).toBe('洗濯を干す')
    expect(result.current.data?.[0].is_completed).toBe(false)
    expect(result.current.data?.[1].is_completed).toBe(true)
  })

  it('enters error state on 500', async () => {
    server.use(
      http.get('/api/tasks/', () =>
        new HttpResponse('Internal Server Error', { status: 500 })
      )
    )

    const { result } = renderHook(() => useTasks(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })
})

describe('useTaskStats', () => {
  it('fetches task statistics', async () => {
    const { result } = renderHook(() => useTaskStats(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.tasks_completed).toBe(statsFixture.tasks_completed)
    expect(result.current.data?.tasks_active).toBe(statsFixture.tasks_active)
    expect(result.current.data?.tasks_queued).toBe(statsFixture.tasks_queued)
    expect(result.current.data?.tasks_completed_last_hour).toBe(statsFixture.tasks_completed_last_hour)
  })

  it('enters error state on server error', async () => {
    server.use(
      http.get('/api/tasks/stats', () =>
        new HttpResponse('Service Unavailable', { status: 503 })
      )
    )

    const { result } = renderHook(() => useTaskStats(), {
      wrapper: makeQueryWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
