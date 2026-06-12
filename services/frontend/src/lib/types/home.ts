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
