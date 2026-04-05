import type { ChatResponse, ChatMessage, ConversationSummary } from '@/lib/types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const sendChatMessage = (
  content: string,
  conversationId?: number,
  tts?: boolean,
): Promise<ChatResponse> =>
  apiFetch('/chat/', {
    method: 'POST',
    body: JSON.stringify({
      content,
      conversation_id: conversationId ?? null,
      tts: tts ?? null,
    }),
  })

export const fetchConversations = (limit = 20): Promise<ConversationSummary[]> =>
  apiFetch(`/chat/conversations?limit=${limit}`)

export const fetchConversationMessages = (
  conversationId: number,
): Promise<{ messages: ChatMessage[] }> =>
  apiFetch(`/chat/conversations/${conversationId}`)

export const archiveConversation = (conversationId: number): Promise<void> =>
  apiFetch(`/chat/conversations/${conversationId}`, { method: 'DELETE' })
