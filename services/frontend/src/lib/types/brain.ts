// ─── Brain / Power mode ───────────────────────────────────────────────────────

export type PowerMode = 'normal' | 'sleep' | 'away'

export interface BrainStatus {
  mode: PowerMode
  reason: string
  entered_at: number
  cycle_interval_sec: number
  llm_cooldown_remaining_sec: number
  manual_override_remaining_sec: number
  last_cycle?: BrainCycleSummary
}

export interface BrainTriggerEvent {
  zone: string
  event: string
  severity: number
}

export interface BrainCycleToolCall {
  tool: string
  summary: string
  success: boolean
}

export interface BrainCycleSummary {
  timestamp: number
  elapsed: number
  iterations: number
  total_tool_calls: number
  mode: string  // "llm" | "rule_low_power_throttled" | "rule_low_power_idle" | "rule_vlm_swap" | "rule_gpu_busy"
  trigger_events: BrainTriggerEvent[]
  tool_calls: BrainCycleToolCall[]
}

export interface OllamaModel {
  name: string
  size_gb: number
  family: string
}

export type BatchTaskName = 'news_briefing' | 'morning_greeting' | 'weather_report' | 'task_planning'
