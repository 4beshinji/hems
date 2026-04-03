import { apiFetch } from '@/lib/api-client'
import type { ChatResponse, ChatMessage, ConversationSummary } from '@/lib/types'

export const sendChatMessage = (
  content: string,
  conversationId?: number,
): Promise<ChatResponse> =>
  apiFetch('/chat/', {
    method: 'POST',
    body: JSON.stringify({
      content,
      conversation_id: conversationId ?? null,
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
