// ─── Voice Events ────────────────────────────────────────────────────────────
export interface VoiceEvent {
  id: number
  message: string
  audio_url: string
  zone?: string | null
  tone: string
  motion_id?: string | null
  character_name?: string | null
  created_at?: string | null
}

// ─── Tasks ────────────────────────────────────────────────────────────────────
export type PreferredTimeSlot =
  | 'morning'
  | 'afternoon'
  | 'evening'
  | 'deep_night'
  | 'anytime'

export type TaskProposalStatus = 'proposed' | 'dismissed' | null

export interface TaskData {
  id: number
  title: string
  description?: string | null
  location?: string | null
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
  cognitive_load?: number | null
  preferred_time_slot?: PreferredTimeSlot | null
  deadline?: string | null
  source?: string | null
  source_ref?: string | null
  confidence?: number | null
  proposal_status?: TaskProposalStatus
  dismissed_at?: string | null
  dismiss_reason?: string | null
  locked_start?: string | null
}

export interface TaskCreatePayload {
  title: string
  description?: string
  location?: string
  urgency?: number
  zone?: string
  estimated_duration?: number
  task_type?: string[]
  cognitive_load?: number
  preferred_time_slot?: PreferredTimeSlot
  deadline?: string
  source?: string
  source_ref?: string
}

// ─── Timeline ────────────────────────────────────────────────────────────────
export type TimelineSlotKind =
  | 'calendar'
  | 'task'
  | 'routine_wake'
  | 'commute_out'
  | 'commute_in'
  | 'focus_free'
  | 'sleep'
  | 'prep'

export interface ScheduledBlock {
  id: number
  date: string
  start_ts: string
  end_ts: string
  kind: TimelineSlotKind
  ref_task_id?: number | null
  ref_calendar_event_id?: string | null
  title: string
  location?: string | null
  is_locked: boolean
  travel_buffer_minutes: number
  generated_at?: string | null
}

export interface TimelineData {
  date: string
  blocks: ScheduledBlock[]
  generated_at?: string | null
}

// ─── System Stats ─────────────────────────────────────────────────────────────
export interface SystemStatsResponse {
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

// ─── Shopping List ───────────────────────────────────────────────────────────
export interface ShoppingItem {
  id: number
  name: string
  category?: string | null
  quantity: number
  unit?: string | null
  store?: string | null
  store_category?: string | null   // brain classifier output (drugstore/supermarket/...)
  price?: number | null
  is_purchased: boolean
  is_recurring: boolean
  recurrence_days?: number | null
  last_purchased_at?: string | null
  next_purchase_at?: string | null
  notes?: string | null
  priority: number
  created_at?: string | null
  purchased_at?: string | null
  created_by: string
  share_token?: string | null
}

export interface ShoppingStats {
  total_items: number
  purchased_items: number
  pending_items: number
  total_spent_this_month: number
  category_breakdown: Record<string, number>
}

export interface PurchaseHistoryItem {
  id: number
  item_name: string
  category?: string | null
  store?: string | null
  price?: number | null
  quantity: number
  purchased_at?: string | null
}

// ─── Chat ────────────────────────────────────────────────────────────────────
export interface ChatMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  audio_url?: string | null
  tool_calls_json?: string | null
  metadata_json?: string | null
  created_at?: string | null
}

export interface ChatResponse {
  user_message: ChatMessage
  assistant_message: ChatMessage
  conversation_id: number
}

export interface ConversationSummary {
  id: number
  title?: string | null
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
  last_message?: string | null
}

// ─── Brain / Power mode ───────────────────────────────────────────────────────

export type PowerMode = 'normal' | 'sleep' | 'away'

export interface BrainStatus {
  mode: PowerMode
  reason: string
  entered_at: number
  cycle_interval_sec: number
  llm_cooldown_remaining_sec: number
  manual_override_remaining_sec: number
}

export interface OllamaModel {
  name: string
  size_gb: number
  family: string
}

export type BatchTaskName = 'news_briefing' | 'morning_greeting' | 'weather_report' | 'task_planning'

// ─── Device Registry ──────────────────────────────────────────────────────────

export type DeviceVendor = 'zigbee' | 'switchbot' | 'tapo' | 'ha' | 'mcp' | 'ir_via_hub'
export type DeviceKind = 'sensor' | 'actuator' | 'both'

export type DeviceCapability =
  | 'on_off'
  | 'brightness'
  | 'color_temp'
  | 'set_position'
  | 'set_temperature'
  | 'pulse'
  | 'ir_send'

export type DeviceAction =
  | 'on'
  | 'off'
  | 'toggle'
  | 'set_brightness'
  | 'set_color_temp'
  | 'set_position'
  | 'set_temperature'
  | 'pulse'
  | 'ir_send'

export interface Device {
  id: number
  device_id: string
  vendor: DeviceVendor
  vendor_ref?: string | null
  kind: DeviceKind
  device_class?: string | null
  capabilities: DeviceCapability[]
  channels: string[]
  units: Record<string, string>
  display_name?: string | null
  zone?: string | null
  location?: string | null
  purpose?: string | null
  description?: string | null
  icon?: string | null
  last_state: Record<string, unknown>
  last_value: Record<string, unknown>
  last_seen?: string | null
  battery_pct?: number | null
  is_enabled: boolean
  notes?: string | null
  metadata_json?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface DeviceUpdate {
  display_name?: string | null
  zone?: string | null
  location?: string | null
  purpose?: string | null
  description?: string | null
  icon?: string | null
  is_enabled?: boolean
  notes?: string | null
  kind?: DeviceKind
  device_class?: string | null
  capabilities?: DeviceCapability[]
  channels?: string[]
  units?: Record<string, string>
  metadata_json?: string | null
}

export interface DeviceCreate extends DeviceUpdate {
  device_id: string
  vendor: DeviceVendor
  vendor_ref?: string | null
  kind: DeviceKind
}

export interface DeviceControlRequest {
  action: DeviceAction
  params?: Record<string, unknown>
}

export interface DeviceControlResponse {
  success: boolean
  result?: string | null
  error?: string | null
}

// ─── Scenes ───────────────────────────────────────────────────────────────────

export interface SceneAction {
  device_id: string
  action: DeviceAction
  params?: Record<string, unknown>
  delay_s: number
}

export interface Scene {
  id: number
  name: string
  display_name: string
  description?: string | null
  actions: SceneAction[]
  is_enabled: boolean
  last_executed_at?: string | null
  execution_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface SceneCreate {
  name: string
  display_name: string
  description?: string | null
  actions: SceneAction[]
  is_enabled?: boolean
}

export interface SceneUpdate {
  display_name?: string
  description?: string | null
  actions?: SceneAction[]
  is_enabled?: boolean
}

export interface SceneExecuteResponse {
  success: boolean
  executed: number
  errors: string[]
}

// ─── Automation rules ─────────────────────────────────────────────────────────

export type AutomationTriggerType = 'sensor_threshold' | 'schedule' | 'event' | 'device_state'
export type AutomationMode = 'direct' | 'llm_review'

export interface AutomationRule {
  id: number
  name: string
  description?: string | null
  enabled: boolean
  trigger_type: AutomationTriggerType
  trigger_config: Record<string, unknown>
  actions: SceneAction[]
  cooldown_s: number
  last_fired_at?: string | null
  mode: AutomationMode
  require_confirm: boolean
  fire_count: number
  last_evaluation_ts?: number | null
  created_at?: string | null
  updated_at?: string | null
}

export interface AutomationRuleCreate {
  name: string
  description?: string | null
  enabled?: boolean
  trigger_type: AutomationTriggerType
  trigger_config: Record<string, unknown>
  actions: SceneAction[]
  cooldown_s?: number
  mode?: AutomationMode
  require_confirm?: boolean
}

export type AutomationRuleUpdate = Partial<AutomationRuleCreate>

export interface AutomationTestResponse {
  rule_id: number
  would_fire: boolean
  reason: string
  sampled_value?: number | string | null
}

// ─── Frequent Places (mobile companion geofence targets) ───────────────────

export type FrequentPlaceCategory =
  | 'drugstore'
  | 'supermarket'
  | 'convenience'
  | 'home_center'
  | 'other'

export interface FrequentPlace {
  id: number
  label: string
  category: FrequentPlaceCategory
  lat: number
  lon: number
  radius_m: number
  enabled: boolean
  cooldown_min: number
  created_at?: string
  updated_at?: string
}

export interface FrequentPlaceCreate {
  label: string
  category: FrequentPlaceCategory
  lat: number
  lon: number
  radius_m?: number
  enabled?: boolean
  cooldown_min?: number
}

export type FrequentPlaceUpdate = Partial<FrequentPlaceCreate>

// ─── Mobile devices ────────────────────────────────────────────────────────

export interface MobileDevice {
  id: number
  device_label: string
  platform?: string
  registered_at?: string
  last_seen_at?: string
  enabled: boolean
}

export interface MobileDeviceRegisterRequest {
  device_label: string
  platform?: string
}

/** One-time response containing plaintext credentials — render as QR, drop. */
export interface MobileDeviceRegisterResponse {
  device_id: number
  device_key: string
  hmac_secret: string
  backend_url?: string
  character_version?: string
}
