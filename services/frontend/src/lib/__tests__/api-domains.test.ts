/**
 * Tests for domain-specific API modules:
 *   src/lib/api/voice-events.ts
 *   src/lib/api/tasks.ts
 *   src/lib/api/zones.ts
 *
 * MSW intercepts the real fetch so these tests verify:
 * - correct endpoint paths
 * - response shaping (types)
 * - error propagation via ApiError
 */
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import {
  voiceEventFixtures,
  taskFixtures,
  zoneFixtures,
  statsFixture,
} from '@/test/handlers'
import { fetchVoiceEvents } from '@/lib/api/voice-events'
import { fetchTasks, fetchStats, completeTask } from '@/lib/api/tasks'
import { fetchZones } from '@/lib/api/zones'
import { ApiError } from '@/lib/api-client'

// ─── Voice Events ─────────────────────────────────────────────────────────────

describe('fetchVoiceEvents', () => {
  it('fetches from /api/voice-events/recent and returns array', async () => {
    const events = await fetchVoiceEvents()
    expect(events).toHaveLength(voiceEventFixtures.length)
    expect(events[0].id).toBe(1)
    expect(events[0].message).toBe('おはようございます')
    expect(events[0].tone).toBe('friendly')
  })

  it('returns all fields including optional ones', async () => {
    const events = await fetchVoiceEvents()
    const first = events[0]
    expect(first.character_name).toBe('ena')
    expect(first.zone).toBe('living')
    expect(first.created_at).toBeTruthy()
  })

  it('throws ApiError on server error', async () => {
    server.use(
      http.get('/api/voice-events/recent', () =>
        new HttpResponse('Service Unavailable', { status: 503 })
      )
    )
    await expect(fetchVoiceEvents()).rejects.toBeInstanceOf(ApiError)
  })
})

// ─── Tasks ────────────────────────────────────────────────────────────────────

describe('fetchTasks', () => {
  it('fetches from /api/tasks/ and returns array', async () => {
    const tasks = await fetchTasks()
    expect(tasks).toHaveLength(taskFixtures.length)
    expect(tasks[0].title).toBe('洗濯を干す')
    expect(tasks[0].is_completed).toBe(false)
    expect(tasks[1].is_completed).toBe(true)
  })

  it('throws ApiError on 401', async () => {
    server.use(
      http.get('/api/tasks/', () =>
        new HttpResponse('Unauthorized', { status: 401 })
      )
    )
    await expect(fetchTasks()).rejects.toBeInstanceOf(ApiError)
  })
})

describe('fetchStats', () => {
  it('fetches from /api/tasks/stats', async () => {
    const stats = await fetchStats()
    expect(stats.tasks_completed).toBe(statsFixture.tasks_completed)
    expect(stats.tasks_active).toBe(statsFixture.tasks_active)
    expect(stats.tasks_queued).toBe(statsFixture.tasks_queued)
  })
})

describe('completeTask', () => {
  it('sends PUT to /api/tasks/:id/complete with body', async () => {
    let capturedBody: unknown = null
    let capturedMethod: string | null = null

    server.use(
      http.put('/api/tasks/42/complete', async ({ request }) => {
        capturedMethod = request.method
        capturedBody = await request.json()
        return HttpResponse.json(null, { status: 200 })
      })
    )

    await completeTask(42, 'done', 'finished without issues')

    expect(capturedMethod).toBe('PUT')
    expect(capturedBody).toEqual({
      report_status: 'done',
      completion_note: 'finished without issues',
    })
  })

  it('throws ApiError when task not found', async () => {
    server.use(
      http.put('/api/tasks/999/complete', () =>
        new HttpResponse('Not Found', { status: 404 })
      )
    )
    await expect(completeTask(999, 'done', '')).rejects.toBeInstanceOf(ApiError)
  })
})

// ─── Zones ────────────────────────────────────────────────────────────────────

describe('fetchZones', () => {
  it('fetches from /api/zones/ and returns array', async () => {
    const zones = await fetchZones()
    expect(zones).toHaveLength(zoneFixtures.length)
    expect(zones[0].zone_id).toBe('living')
    expect(zones[0].environment.temperature).toBe(24.5)
    expect(zones[0].occupancy.count).toBe(1)
  })

  it('returns environment fields', async () => {
    const zones = await fetchZones()
    expect(zones[1].zone_id).toBe('bedroom')
    expect(zones[1].occupancy.count).toBe(0)
  })

  it('throws ApiError on server error', async () => {
    server.use(
      http.get('/api/zones/', () =>
        new HttpResponse('Internal Server Error', { status: 500 })
      )
    )
    await expect(fetchZones()).rejects.toBeInstanceOf(ApiError)
  })
})
