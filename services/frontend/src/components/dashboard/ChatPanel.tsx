import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageCircle, Bot, User, Volume2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useAppContext } from '@/app/layout'
import { AudioPriority } from '@/audio'
import { fetchVoiceEvents, sendChatMessage } from '@/lib/api'
import { ZONE_LABELS } from '@/lib/constants'
import ChatInput from './ChatInput'
import type { VoiceEvent, ChatMessage } from '@/lib/types'

const TONE_VARIANTS: Record<string, 'secondary' | 'info' | 'warning' | 'destructive'> = {
  neutral: 'secondary',
  caring: 'info',
  humorous: 'warning',
  alert: 'destructive',
}

// Unified timeline item: chat message or voice event
type TimelineItem =
  | { type: 'chat'; data: ChatMessage }
  | { type: 'voice'; data: VoiceEvent }

export default function ChatPanel() {
  const { audioEnabled, enqueueAudio } = useAppContext()
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Poll voice events (same as AIActivityLog)
  const { data: voiceEvents } = useQuery({
    queryKey: ['voiceEvents'],
    queryFn: fetchVoiceEvents,
    refetchInterval: 3000,
  })

  // Merge chat messages and voice events into unified timeline
  const timeline = useMemo<TimelineItem[]>(() => {
    const items: TimelineItem[] = []

    for (const msg of chatMessages) {
      items.push({ type: 'chat', data: msg })
    }

    // Show recent voice events (last 10) that aren't duplicated by chat
    if (voiceEvents) {
      for (const ev of voiceEvents.slice(0, 10)) {
        items.push({ type: 'voice', data: ev })
      }
    }

    // Sort by timestamp ascending
    items.sort((a, b) => {
      const tA = a.type === 'chat' ? a.data.created_at : a.data.created_at
      const tB = b.type === 'chat' ? b.data.created_at : b.data.created_at
      if (!tA || !tB) return 0
      return new Date(tA).getTime() - new Date(tB).getTime()
    })

    return items
  }, [chatMessages, voiceEvents])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [timeline.length, isLoading])

  const handleSend = useCallback(async (message: string, _opts?: { tts?: boolean }) => {
    setIsLoading(true)
    setError(null)

    // Optimistic UI: add user message
    const optimisticMsg: ChatMessage = {
      id: -Date.now(),
      conversation_id: conversationId ?? 0,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    }
    setChatMessages(prev => [...prev, optimisticMsg])

    try {
      const resp = await sendChatMessage(
        message,
        conversationId ?? undefined,
        true,
      )
      setConversationId(resp.conversation_id)

      // Replace optimistic message + add assistant response
      setChatMessages(prev => [
        ...prev.filter(m => m.id !== optimisticMsg.id),
        resp.user_message,
        resp.assistant_message,
      ])

      // Play audio if available
      if (resp.assistant_message.audio_url && audioEnabled) {
        enqueueAudio(resp.assistant_message.audio_url, AudioPriority.USER_ACTION)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'エラーが発生しました')
      // Remove optimistic message on error
      setChatMessages(prev => prev.filter(m => m.id !== optimisticMsg.id))
    } finally {
      setIsLoading(false)
    }
  }, [conversationId, audioEnabled, enqueueAudio])

  const handleNewChat = useCallback(() => {
    setConversationId(null)
    setChatMessages([])
    setError(null)
  }, [])

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-primary" />
            Chat
          </span>
          {conversationId && (
            <button
              onClick={handleNewChat}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              + 新しい会話
            </button>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent className="flex-1 min-h-0 flex flex-col gap-2 pb-2">
        {/* Message area */}
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
          {timeline.length === 0 && !isLoading && (
            <p className="text-sm text-muted-foreground py-8 text-center">
              メッセージを入力してAIと会話しましょう
            </p>
          )}

          {timeline.map((item) =>
            item.type === 'chat' ? (
              <ChatBubble key={`chat-${item.data.id}`} message={item.data} />
            ) : (
              <VoiceEventRow key={`voice-${item.data.id}`} event={item.data} />
            ),
          )}

          {isLoading && (
            <div className="flex gap-2 items-center px-2">
              <Bot className="h-4 w-4 text-primary shrink-0" />
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-primary/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          )}

          {error && (
            <p className="text-xs text-destructive px-2">{error}</p>
          )}
        </div>

        {/* Input area */}
        <ChatInput onSend={handleSend} isLoading={isLoading} />
      </CardContent>
    </Card>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <Bot className="h-4 w-4 text-primary shrink-0 mt-1" />}
      <div
        className={`max-w-[80%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap break-words ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-secondary text-secondary-foreground'
        }`}
      >
        {message.content}
      </div>
      {isUser && <User className="h-4 w-4 text-muted-foreground shrink-0 mt-1" />}
    </div>
  )
}

function VoiceEventRow({ event }: { event: VoiceEvent }) {
  const variant = TONE_VARIANTS[event.tone] ?? 'secondary'
  const time = event.created_at
    ? new Date(event.created_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <div className="flex gap-2 items-start px-1">
      <Volume2 className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-1" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-[10px] text-muted-foreground font-mono">{time}</span>
          {event.character_name && (
            <span className="text-[10px] font-medium text-primary">{event.character_name}</span>
          )}
          <Badge variant={variant} className="text-[9px] px-1 py-0 leading-tight">
            {event.tone}
          </Badge>
          {event.zone && (
            <Badge variant="outline" className="text-[9px] px-1 py-0 leading-tight">
              {ZONE_LABELS[event.zone] ?? event.zone}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{event.message}</p>
      </div>
    </div>
  )
}
