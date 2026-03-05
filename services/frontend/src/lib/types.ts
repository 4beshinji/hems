// ─── Voice Events ────────────────────────────────────────────────────────────
export interface VoiceEvent {
  id: number
  message: string
  audio_url: string
  zone?: string | null
  tone: string
  character_name?: string | null
  created_at?: string | null
}

// ─── Tasks ────────────────────────────────────────────────────────────────────
export interface TaskData {
  id: number
  title: string
  description?: string | null
  location?: string | null
  xp_reward: number
  is_completed: boolean
  is_queued: boolean
  urgency: number
  zone?: string | null
  estimated_duration: number
  task_type?: string[] | null
  announcement_audio_url?: string | null
  announcement_text?: string | null
  completion_audio_url?: string | null
  completion_text?: string | null
  assigned_to?: number | null
  accepted_at?: string | null
  dispatched_at?: string | null
  created_at?: string | null
  completed_at?: string | null
  expires_at?: string | null
  last_reminded_at?: string | null
  report_status?: string | null
  completion_note?: string | null
}

// ─── System Stats ─────────────────────────────────────────────────────────────
export interface SystemStatsResponse {
  total_xp: number
  tasks_completed: number
  tasks_created: number
  tasks_active: number
  tasks_queued: number
  tasks_completed_last_hour: number
}

// ─── Zones ────────────────────────────────────────────────────────────────────
export interface EnvironmentData {
  temperature?: number | null
  humidity?: number | null
  co2?: number | null
  pressure?: number | null
  light?: number | null
  voc?: number | null
  /** Unix timestamp or ISO string */
  last_update?: number | string | null
}

export interface OccupancyData {
  count: number
  last_update?: number | string | null
}

export interface ZoneSnapshot {
  zone_id: string
  environment: EnvironmentData
  occupancy: OccupancyData
  events?: Record<string, unknown>[]
}

/** Alias used by ZoneEnvironmentCard */
export type ZoneData = ZoneSnapshot

// ─── PC Metrics ───────────────────────────────────────────────────────────────
export interface PCCpu {
  usage_percent: number
  temp_c: number
}

export interface PCMemory {
  percent: number
  used_gb: number
  total_gb: number
}

export interface PCGpu {
  usage_percent: number
  temp_c: number
}

export interface PCDisk {
  mount: string
  percent: number
  used_gb: number
  total_gb: number
}

export interface PCProcess {
  name: string
  cpu_percent: number
  mem_mb: number
  pid: number
}

export interface PCMetrics {
  status?: string | null
  bridge_connected?: boolean
  cpu?: PCCpu | null
  memory?: PCMemory | null
  gpu?: PCGpu | null
  disk?: PCDisk[] | null
  top_processes?: PCProcess[] | null
  last_update?: number | null
}

// ─── Services ─────────────────────────────────────────────────────────────────
export interface ServiceStatusItem {
  name: string
  status: string
  unread_count: number
  last_check?: string | null
  error?: string | null
  summary?: string | null
}

export interface ServicesData {
  status?: string | null
  [key: string]: unknown
}

// ─── Knowledge ────────────────────────────────────────────────────────────────
export interface KnowledgeChange {
  title: string
  action: string
  timestamp?: string | null
}

export interface KnowledgeData {
  status?: string | null
  total_notes?: number | null
  indexed?: number | null
  recent_changes?: KnowledgeChange[]
  last_update?: number | null
}

// ─── GAS ──────────────────────────────────────────────────────────────────────
export interface CalendarEvent {
  id?: string | null
  title: string
  start?: string | null
  end?: string | null
  is_all_day?: boolean
  location?: string | null
}

export interface FreeSlot {
  start: string
  end: string
  duration_minutes: number
}

export interface GASTask {
  title: string
  due?: string | null
  is_overdue?: boolean
}

export interface GASData {
  status?: string | null
  calendar_events?: CalendarEvent[]
  tasks_due?: GASTask[]
  free_slots?: FreeSlot[]
  overdue_count?: number
  gmail_inbox_unread?: number
  last_update?: number | null
}

// ─── Biometrics ───────────────────────────────────────────────────────────────
export interface HeartRateData {
  bpm: number
  zone: string
  resting_bpm?: number | null
}

export interface SpO2Data {
  percent: number
}

export interface HRVData {
  rmssd_ms: number
}

export interface SleepData {
  duration_minutes: number
  quality_score: number
  deep_minutes: number
  rem_minutes: number
  light_minutes: number
}

export interface ActivityData {
  steps: number
  steps_goal: number
  calories: number
  distance_km?: number
  active_minutes?: number
}

export interface StressData {
  score?: number | null
  category: string
  level?: number | null
}

export interface FatigueData {
  score: number
}

export interface BodyTemperatureData {
  celsius: number
}

export interface RespiratoryRateData {
  breaths_per_minute: number
}

export interface ScreenTimeData {
  total_minutes: number
}

export interface BodyMetricsData {
  weight_kg?: number | null
  bmi?: number | null
}

export interface BiometricData {
  status?: string | null
  bridge_connected?: boolean
  provider?: string | null
  heart_rate?: HeartRateData | null
  spo2?: SpO2Data | null
  hrv?: HRVData | null
  sleep?: SleepData | null
  activity?: ActivityData | null
  stress?: StressData | null
  fatigue?: FatigueData | null
  body_temperature?: BodyTemperatureData | null
  respiratory_rate?: RespiratoryRateData | null
  screen_time?: ScreenTimeData | null
  body?: BodyMetricsData | null
  last_update?: number | null
}

// ─── Perception ───────────────────────────────────────────────────────────────
export interface PerceptionZone {
  person_count: number
  activity_level: number | null
  posture_status: string
  posture_duration_sec: number
}

export interface PerceptionData {
  status?: string | null
  zones?: Record<string, PerceptionZone>
  last_update?: number | null
}

// ─── Home Assistant ───────────────────────────────────────────────────────────
export interface HomeLight {
  on: boolean
  brightness: number
  color_temp?: number | null
}

export interface HomeClimate {
  mode: string
  current_temp: number
  target_temp: number
  fan_mode?: string | null
}

export interface HomeCover {
  position: number
  is_open: boolean
}

export interface EnergySensor {
  value: number
  unit: string
  device_class: string
}

export interface HomeData {
  status?: string | null
  bridge_connected?: boolean
  lights?: Record<string, HomeLight>
  climates?: Record<string, HomeClimate>
  covers?: Record<string, HomeCover>
  energy_sensors?: Record<string, EnergySensor>
  last_update?: number | null
}

// ─── Time Series ──────────────────────────────────────────────────────────────
export interface TimeSeriesPoint {
  value: number
  recorded_at: string
  zone?: string | null
}
