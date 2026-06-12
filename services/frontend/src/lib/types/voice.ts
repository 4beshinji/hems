// ─── Voice Events ────────────────────────────────────────────────────────────
export interface VoiceEvent {
  id: number
  message: string
  audio_url: string
  zone?: string | null
  tone: string
  motion_id?: string | null
  character_name?: string | null
  created_at?: string | null
}
