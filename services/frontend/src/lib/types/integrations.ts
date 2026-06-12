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

// ─── Weather ──────────────────────────────────────────────────────────────────
export interface WeatherCurrent {
  condition: string
  temperature: number
  humidity: number
  wind_speed: number
  last_update?: number | null
}

export interface WeatherForecast {
  datetime: string
  condition: string
  temperature: number
  precipitation_probability: number
  wind_speed: number
}

export type WeatherAlertSeverity =
  | 'minor'
  | 'moderate'
  | 'severe'
  | 'extreme'
  | 'warning'
  | 'advisory'
  | 'watch'
  | 'critical'
  | 'unknown'

export interface WeatherAlert {
  title: string
  severity: WeatherAlertSeverity | string
  description: string
  area: string
  issued_at: string
  expires_at: string
}

export interface WeatherData {
  status?: string | null
  current?: WeatherCurrent | null
  forecast?: WeatherForecast[] | null
  alerts?: WeatherAlert[] | null
  last_alerts_update?: number | null
}

// ─── Device action log ───────────────────────────────────────────────────────
export interface DeviceActionEvent {
  id: number
  device_id: string
  action: string
  params: Record<string, unknown>
  source?: string | null
  success: boolean
  timestamp: string
}

// ─── News ─────────────────────────────────────────────────────────────────────
export interface NewsArticle {
  title?: string
  url?: string
  source?: string
  summary?: string
  category?: string
  urgency?: number
  timestamp?: number
}

export interface NewsData {
  status?: string | null
  daily_summary?: string
  daily_chunks?: string[]
  daily_timestamp?: number
  urgent_articles?: NewsArticle[]
  bridge_connected?: boolean
}

// ─── Time Series ──────────────────────────────────────────────────────────────
export interface TimeSeriesPoint {
  value: number
  recorded_at: string
  zone?: string | null
}
