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
  pm25?: number | null
  soil_moisture?: number | null
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
