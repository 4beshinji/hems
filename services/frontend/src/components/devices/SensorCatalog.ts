// Device class catalog — home-use subset (from Office_as_AI_ToyBox DEVICE_CATALOG).
// Provides icon / label / color hints for the /devices UI.

import type { DeviceCapability } from '@/lib/types'

export interface DeviceCatalogEntry {
  label: string
  channels: string[]
  capabilities: DeviceCapability[]
  color: string
  icon: string // lucide icon name
}

export const DEVICE_CATALOG: Record<string, DeviceCatalogEntry> = {
  // Environment
  temp_humidity: {
    label: '温湿度',
    channels: ['temperature', 'humidity'],
    capabilities: [],
    color: '#10b981',
    icon: 'Thermometer',
  },
  bme680: {
    label: 'BME680 (温湿圧ガス)',
    channels: ['temperature', 'humidity', 'pressure', 'voc'],
    capabilities: [],
    color: '#10b981',
    icon: 'Thermometer',
  },
  co2: {
    label: 'CO2',
    channels: ['co2'],
    capabilities: [],
    color: '#0ea5e9',
    icon: 'Wind',
  },
  illuminance: {
    label: '照度',
    channels: ['illuminance'],
    capabilities: [],
    color: '#f59e0b',
    icon: 'Sun',
  },
  pressure: {
    label: '気圧',
    channels: ['pressure'],
    capabilities: [],
    color: '#64748b',
    icon: 'Gauge',
  },
  air_quality: {
    label: '空気質 (PM/VOC)',
    channels: ['pm25', 'voc'],
    capabilities: [],
    color: '#10b981',
    icon: 'Wind',
  },
  soil: {
    label: '土壌水分',
    channels: ['soil_moisture', 'temperature'],
    capabilities: [],
    color: '#65a30d',
    icon: 'Sprout',
  },
  // Motion / presence
  pir: {
    label: '人感 (PIR)',
    channels: ['motion'],
    capabilities: [],
    color: '#f59e0b',
    icon: 'PersonStanding',
  },
  presence: {
    label: 'Presence (mmWave)',
    channels: ['motion', 'occupancy'],
    capabilities: [],
    color: '#f59e0b',
    icon: 'Radar',
  },
  // Contact / safety
  contact: {
    label: '開閉',
    channels: ['contact'],
    capabilities: [],
    color: '#8b5cf6',
    icon: 'DoorOpen',
  },
  water_leak: {
    label: '漏水',
    channels: ['water_leak'],
    capabilities: [],
    color: '#0ea5e9',
    icon: 'Droplet',
  },
  smoke: {
    label: '煙',
    channels: ['smoke'],
    capabilities: [],
    color: '#dc2626',
    icon: 'Flame',
  },
  // Actuators
  plug: {
    label: 'スマートプラグ',
    channels: [],
    capabilities: ['on_off', 'pulse'],
    color: '#3b82f6',
    icon: 'Plug',
  },
  light: {
    label: 'スマートライト',
    channels: [],
    capabilities: ['on_off', 'brightness'],
    color: '#fbbf24',
    icon: 'Lightbulb',
  },
  bulb: {
    label: 'スマート電球',
    channels: [],
    capabilities: ['on_off', 'brightness', 'color_temp'],
    color: '#fbbf24',
    icon: 'Lightbulb',
  },
  curtain: {
    label: 'カーテン',
    channels: [],
    capabilities: ['set_position'],
    color: '#8b5cf6',
    icon: 'Blinds',
  },
  climate: {
    label: 'エアコン',
    channels: [],
    capabilities: ['set_temperature', 'on_off'],
    color: '#06b6d4',
    icon: 'AirVent',
  },
  hub_ir: {
    label: 'IR Hub',
    channels: [],
    capabilities: ['ir_send'],
    color: '#a855f7',
    icon: 'Rss',
  },
  pump: {
    label: '水ポンプ',
    channels: [],
    capabilities: ['on_off', 'pulse'],
    color: '#0891b2',
    icon: 'Droplets',
  },
  // Generic fallback
  sensor: {
    label: 'センサー',
    channels: [],
    capabilities: [],
    color: '#9ca3af',
    icon: 'Activity',
  },
  actuator: {
    label: 'アクチュエータ',
    channels: [],
    capabilities: ['on_off'],
    color: '#9ca3af',
    icon: 'ToggleRight',
  },
}

export const VENDOR_LABELS: Record<string, string> = {
  zigbee: 'Zigbee',
  switchbot: 'SwitchBot',
  tapo: 'Tapo',
  ha: 'Home Assistant',
  mcp: 'MCP (ESP32)',
  ir_via_hub: 'IR (Hub経由)',
}

export const KIND_LABELS: Record<string, string> = {
  sensor: 'センサー',
  actuator: 'アクチュエータ',
  both: 'センサー+アクチュエータ',
}

export const CHANNEL_UNITS: Record<string, string> = {
  temperature: '°C',
  humidity: '%',
  co2: 'ppm',
  pressure: 'hPa',
  illuminance: 'lx',
  light: 'lx',
  voc: '',
  soil_moisture: '%',
  pm25: 'µg/m³',
  power_watts: 'W',
  voltage: 'V',
  current: 'A',
  energy_kwh: 'kWh',
}

export function lookupCatalog(deviceClass?: string | null): DeviceCatalogEntry | null {
  if (!deviceClass) return null
  return DEVICE_CATALOG[deviceClass] ?? null
}
