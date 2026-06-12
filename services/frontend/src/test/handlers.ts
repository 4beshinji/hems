import { http, HttpResponse } from 'msw'
import type {
  VoiceEvent,
  TaskData,
  ZoneData,
  SystemStatsResponse,
} from '@/lib/types'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

export const voiceEventFixtures: VoiceEvent[] = [
  {
    id: 1,
    message: 'おはようございます',
    audio_url: '/audio/1.wav',
    zone: 'living',
    tone: 'friendly',
    motion_id: null,
    character_name: 'ena',
    created_at: '2026-06-12T08:00:00Z',
  },
  {
    id: 2,
    message: '気温が高くなっています',
    audio_url: '/audio/2.wav',
    zone: null,
    tone: 'alert',
    motion_id: null,
    character_name: null,
    created_at: '2026-06-12T09:00:00Z',
  },
]

export const taskFixtures: TaskData[] = [
  {
    id: 1,
    title: '洗濯を干す',
    description: '洗濯物が溜まっています',
    is_completed: false,
    is_queued: true,
    urgency: 2,
    zone: 'living',
    estimated_duration: 15,
  },
  {
    id: 2,
    title: '買い物',
    description: null,
    is_completed: true,
    is_queued: false,
    urgency: 1,
    zone: null,
    estimated_duration: 30,
  },
]

export const zoneFixtures: ZoneData[] = [
  {
    zone_id: 'living',
    environment: {
      temperature: 24.5,
      humidity: 55,
      co2: 800,
      last_update: '2026-06-12T09:00:00Z',
    },
    occupancy: { count: 1, last_update: '2026-06-12T09:00:00Z' },
    events: [],
  },
  {
    zone_id: 'bedroom',
    environment: {
      temperature: 22.0,
      humidity: 50,
      last_update: '2026-06-12T08:30:00Z',
    },
    occupancy: { count: 0 },
    events: [],
  },
]

export const statsFixture: SystemStatsResponse = {
  tasks_completed: 5,
  tasks_created: 8,
  tasks_active: 3,
  tasks_queued: 2,
  tasks_completed_last_hour: 1,
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

export const handlers = [
  http.get('/api/voice-events/recent', () =>
    HttpResponse.json(voiceEventFixtures)
  ),

  http.get('/api/tasks/', () =>
    HttpResponse.json(taskFixtures)
  ),

  http.get('/api/tasks/stats', () =>
    HttpResponse.json(statsFixture)
  ),

  http.get('/api/zones/', () =>
    HttpResponse.json(zoneFixtures)
  ),
]
