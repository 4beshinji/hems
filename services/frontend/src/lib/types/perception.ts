// ─── Perception ───────────────────────────────────────────────────────────────
export type InferenceSource = 'camera' | 'presence_sensor' | 'motion' | 'pc_activity' | 'biometric' | 'none'

export interface SceneSnapshot {
  timestamp: number
  description: string
  objects: string[]
  scene_type: string
  anomalies: string[]
  tier?: string
}

export interface PerceptionZone {
  person_count: number
  activity_level: number | null
  activity_class?: string
  posture?: string
  posture_status: string
  posture_duration_sec: number
  last_update?: number
  // Multi-source presence inference
  inferred_occupied?: boolean
  inference_source?: InferenceSource
  inference_sources?: InferenceSource[]
  presence_state?: boolean | null
  last_motion_ts?: number
  motion_event_count_5min?: number
  // VLM scene data
  scene_description?: string
  scene_objects?: string[]
  scene_type?: string
  scene_anomalies?: string[]
  vlm_last_update?: number
  vlm_history?: SceneSnapshot[]
}

export interface PerceptionData {
  status?: string | null
  zones?: Record<string, PerceptionZone>
  last_update?: number | null
}
