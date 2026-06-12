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
