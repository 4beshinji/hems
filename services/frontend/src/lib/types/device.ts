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
