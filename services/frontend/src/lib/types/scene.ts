import type { DeviceAction } from './device'

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
