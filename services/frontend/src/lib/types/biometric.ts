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
  stage?: string
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
