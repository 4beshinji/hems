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

export const fetchVoiceEvents = async (): Promise<VoiceEvent[]> => {
  const res = await fetch(`${API_BASE}/voice-events/recent`)
  if (!res.ok) throw new Error('Failed to fetch voice events')
  return res.json()
}
