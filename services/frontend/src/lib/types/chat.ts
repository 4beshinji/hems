// ─── Chat ────────────────────────────────────────────────────────────────────
export interface ChatMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  audio_url?: string | null
  tool_calls_json?: string | null
  metadata_json?: string | null
  created_at?: string | null
}

export interface ChatResponse {
  user_message: ChatMessage
  assistant_message: ChatMessage
  conversation_id: number
}

export interface ConversationSummary {
  id: number
  title?: string | null
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
  last_message?: string | null
}
