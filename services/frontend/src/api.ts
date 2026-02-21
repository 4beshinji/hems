/**
 * HEMS API client — centralized fetch functions for TanStack Query.
 */

export interface TaskData {
  id: number
  title: string
  description?: string
  location?: string
  xp_reward: number
  is_completed: boolean
  urgency: number
  zone?: string
  task_type?: string[]
  estimated_duration?: number
  announcement_audio_url?: string
  completion_audio_url?: string
  assigned_to?: number | null
  accepted_at?: string | null
  report_status?: string | null
  completion_note?: string | null
}

export interface StatsData {
  total_xp: number
  tasks_completed: number
  tasks_created: number
  tasks_active: number
}

export interface VoiceEvent {
  id: number
  message: string
  audio_url: string
  zone?: string
  tone: string
}

export interface EnvironmentData {
  temperature?: number | null
  humidity?: number | null
  co2?: number | null
  pressure?: number | null
  light?: number | null
  voc?: number | null
  last_update?: number | null
}

export interface ZoneData {
  zone_id: string
  environment: EnvironmentData
  occupancy: { count: number; last_update?: number | null }
  events: { type: string; description: string; severity: number; timestamp: number }[]
}

export interface ServiceStatusItem {
  name: string
  available: boolean
  unread_count: number
  summary: string
  last_check: number
  error?: string | null
}

export interface ServicesData {
  status?: string
  [key: string]: ServiceStatusItem | string | undefined
}

export interface PCMetrics {
  status?: string
  cpu?: { usage_percent: number; core_count: number; temp_c: number }
  memory?: { used_gb: number; total_gb: number; percent: number }
  gpu?: { usage_percent: number; vram_used_gb: number; vram_total_gb: number; temp_c: number }
  disk?: { mount: string; used_gb: number; total_gb: number; percent: number }[]
  top_processes?: { pid: number; name: string; cpu_percent: number; mem_mb: number }[]
  bridge_connected?: boolean
}

const API_BASE = '/api'

export const fetchTasks = async (): Promise<TaskData[]> => {
  const res = await fetch(`${API_BASE}/tasks/`)
  if (!res.ok) throw new Error('Failed to fetch tasks')
  return res.json()
}

export const fetchStats = async (): Promise<StatsData> => {
  const res = await fetch(`${API_BASE}/tasks/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export const fetchZones = async (): Promise<ZoneData[]> => {
  const res = await fetch(`${API_BASE}/zones/`)
  if (!res.ok) throw new Error('Failed to fetch zones')
  return res.json()
}

export const fetchPC = async (): Promise<PCMetrics> => {
  const res = await fetch(`${API_BASE}/pc/`)
  if (!res.ok) throw new Error('Failed to fetch PC metrics')
  return res.json()
}

export const fetchServices = async (): Promise<ServicesData> => {
  const res = await fetch(`${API_BASE}/services/`)
  if (!res.ok) throw new Error('Failed to fetch services')
  return res.json()
}

export interface KnowledgeData {
  status?: string
  total_notes?: number
  indexed?: number
  bridge_connected?: boolean
  recent_changes?: { path: string; title: string; action: string }[]
}

export interface GASCalendarEvent {
  id: string
  title: string
  start: string
  end: string
  location?: string
  is_all_day?: boolean
  calendar_name?: string
}

export interface GASTaskItem {
  title: string
  due: string
  status: string
  list_name: string
  is_overdue: boolean
}

export interface GASFreeSlot {
  start: string
  end: string
  duration_minutes: number
}

export interface GASData {
  status?: string
  bridge_connected?: boolean
  calendar_events?: GASCalendarEvent[]
  calendar_event_count?: number
  tasks_due?: GASTaskItem[]
  overdue_count?: number
  gmail_inbox_unread?: number
  free_slots?: GASFreeSlot[]
  last_calendar_update?: number
  last_tasks_update?: number
  last_gmail_update?: number
}

export const fetchGAS = async (): Promise<GASData> => {
  const res = await fetch(`${API_BASE}/gas/`)
  if (!res.ok) throw new Error('Failed to fetch GAS data')
  return res.json()
}

export const fetchVoiceEvents = async (): Promise<VoiceEvent[]> => {
  const res = await fetch(`${API_BASE}/voice-events/recent`)
  if (!res.ok) throw new Error('Failed to fetch voice events')
  return res.json()
}

export const fetchKnowledge = async (): Promise<KnowledgeData> => {
  const res = await fetch(`${API_BASE}/knowledge/`)
  if (!res.ok) throw new Error('Failed to fetch knowledge')
  return res.json()
}

export interface BiometricData {
  status?: string
  bridge_connected?: boolean
  provider?: string
  heart_rate?: { bpm: number; zone: string; resting_bpm?: number | null }
  spo2?: { percent: number }
  sleep?: {
    stage: string
    duration_minutes: number
    deep_minutes: number
    rem_minutes: number
    light_minutes: number
    quality_score: number
  }
  activity?: {
    steps: number
    steps_goal: number
    calories: number
    active_minutes: number
    level: string
  }
  stress?: { level: number; category: string }
  fatigue?: { score: number; factors: string[] }
  hrv?: { rmssd_ms: number }
  body_temperature?: { celsius: number }
  respiratory_rate?: { breaths_per_minute: number }
  screen_time?: { total_minutes: number }
}

export const fetchBiometric = async (): Promise<BiometricData> => {
  const res = await fetch(`${API_BASE}/biometric/`)
  if (!res.ok) throw new Error('Failed to fetch biometric data')
  return res.json()
}

// --- Perception ---

export interface PerceptionZone {
  person_count: number
  activity_level: number | null
  activity_class: string
  posture_status: string
  posture_duration_sec: number
  last_update: number
}

export interface PerceptionData {
  status?: string
  zones?: Record<string, PerceptionZone>
}

export const fetchPerception = async (): Promise<PerceptionData> => {
  const res = await fetch(`${API_BASE}/perception/`)
  if (!res.ok) throw new Error('Failed to fetch perception data')
  return res.json()
}

// --- Home (HA) ---

export interface HomeLight {
  on: boolean
  brightness: number
}

export interface HomeClimate {
  mode: string
  target_temp: number
  current_temp: number
}

export interface HomeCover {
  position: number
  is_open: boolean
}

export interface HomeData {
  status?: string
  bridge_connected?: boolean
  lights?: Record<string, HomeLight>
  climates?: Record<string, HomeClimate>
  covers?: Record<string, HomeCover>
  switches?: Record<string, unknown>
}

export const fetchHome = async (): Promise<HomeData> => {
  const res = await fetch(`${API_BASE}/home/`)
  if (!res.ok) throw new Error('Failed to fetch home data')
  return res.json()
}

export const controlLight = async (
  entity_id: string, on: boolean, brightness?: number, color_temp?: number
): Promise<void> => {
  await fetch(`${API_BASE}/home/light/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_id, on, brightness, color_temp }),
  })
}

export const controlClimate = async (
  entity_id: string, mode?: string, temperature?: number
): Promise<void> => {
  await fetch(`${API_BASE}/home/climate/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_id, mode, temperature }),
  })
}

export const controlCover = async (
  entity_id: string, action?: string, position?: number
): Promise<void> => {
  await fetch(`${API_BASE}/home/cover/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_id, action, position }),
  })
}

// --- Time Series ---

export interface TimeSeriesPoint {
  value: number
  recorded_at: string
  zone?: string | null
}

export const fetchTimeSeries = async (
  metric: string, zone?: string, hours: number = 24
): Promise<TimeSeriesPoint[]> => {
  const params = new URLSearchParams({ metric, hours: String(hours) })
  if (zone) params.set('zone', zone)
  const res = await fetch(`${API_BASE}/timeseries/?${params}`)
  if (!res.ok) throw new Error('Failed to fetch timeseries')
  return res.json()
}
