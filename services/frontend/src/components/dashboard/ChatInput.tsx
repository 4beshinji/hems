import { useState, useRef, useCallback } from 'react'
import { Send, Mic, MicOff, Loader2, Radio, AudioLines, SendHorizonal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useAppContext } from '@/app/layout'
import { useServerSTT } from '@/hooks/use-server-stt'

interface ChatInputProps {
  onSend: (message: string, opts?: { tts?: boolean }) => void
  isLoading: boolean
}

const LANG_LABELS: Record<string, string> = {
  ja: 'JP',
  en: 'EN',
  auto: 'Auto',
}

const LANG_CYCLE = ['ja', 'en', 'auto']

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const { sttMode, sttLanguage, setSTTLanguage, sttAutoSend, toggleSTTAutoSend } = useAppContext()

  // Track whether last input came from voice
  const voiceInputRef = useRef(false)

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isLoading) return
    // If sent from voice input, request TTS on the response
    onSend(text, voiceInputRef.current ? { tts: true } : undefined)
    setInput('')
    voiceInputRef.current = false
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
  }, [input, isLoading, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    voiceInputRef.current = false // manual edit → no longer voice input
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  const {
    isListening,
    isProcessing,
    isSpeaking,
    isSupported,
    useServerSTT: hasServer,
    startListening,
    stopListening,
    audioLevel,
  } = useServerSTT({
    mode: sttMode,
    language: sttLanguage,
    onResult: (cleanedText, _rawText) => {
      voiceInputRef.current = true
      if (sttAutoSend) {
        // Auto-send with TTS
        onSend(cleanedText, { tts: true })
      } else {
        // Populate input for manual review
        setInput((prev) => (prev ? prev + ' ' + cleanedText : cleanedText))
      }
    },
    onError: (err) => {
      console.error('STT error:', err)
    },
  })

  const handleMicClick = useCallback(() => {
    if (sttMode === 'off') return
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }, [sttMode, isListening, startListening, stopListening])

  const cycleLang = useCallback(() => {
    const idx = LANG_CYCLE.indexOf(sttLanguage)
    setSTTLanguage(LANG_CYCLE[(idx + 1) % LANG_CYCLE.length])
  }, [sttLanguage, setSTTLanguage])

  const isOff = sttMode === 'off'
  const showMic = isSupported && !isOff

  return (
    <div className="space-y-1.5">
      {/* Status bar — visible when STT is active */}
      {showMic && (isListening || isProcessing) && (
        <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-muted/50 text-xs text-muted-foreground">
          {isProcessing ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin text-primary" />
              <span>認識中...</span>
            </>
          ) : isListening && isSpeaking ? (
            <>
              <AudioLines className="h-3 w-3 text-red-500 animate-pulse" />
              <span>音声検出中</span>
              <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-500 rounded-full transition-all duration-75"
                  style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
                />
              </div>
            </>
          ) : isListening && sttMode === 'auto' ? (
            <>
              <Radio className="h-3 w-3 text-primary animate-pulse" />
              <span>待機中 (VAD)</span>
              <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary/50 rounded-full transition-all duration-75"
                  style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
                />
              </div>
            </>
          ) : isListening ? (
            <>
              <Mic className="h-3 w-3 text-red-500" />
              <span>録音中</span>
              <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-500 rounded-full transition-all duration-75"
                  style={{ width: `${Math.min(audioLevel * 100, 100)}%` }}
                />
              </div>
            </>
          ) : null}
          <Badge variant="outline" className="text-[9px] px-1 py-0">
            {hasServer ? 'Server' : 'Browser'}
          </Badge>
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-1.5 w-full">
        <textarea
          ref={inputRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="メッセージを入力..."
          rows={1}
          disabled={isLoading}
          className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm
                     placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1
                     focus-visible:ring-ring disabled:opacity-50 max-h-[120px]"
        />

        {/* Auto-send toggle (visible when STT active) */}
        {showMic && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={toggleSTTAutoSend}
            disabled={isLoading}
            className="h-9 w-9 shrink-0"
            title={sttAutoSend ? '自動送信: ON (認識後すぐ送信)' : '自動送信: OFF (手動で確認・修正)'}
          >
            <SendHorizonal className={`h-4 w-4 ${sttAutoSend ? 'text-primary' : 'text-muted-foreground'}`} />
          </Button>
        )}

        {/* Language toggle */}
        {showMic && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={cycleLang}
            disabled={isLoading}
            className="h-9 w-9 shrink-0"
            title={`STT言語: ${LANG_LABELS[sttLanguage] ?? sttLanguage}`}
          >
            <span className="text-[10px] font-mono font-bold">{LANG_LABELS[sttLanguage] ?? sttLanguage}</span>
          </Button>
        )}

        {/* Mic button */}
        {showMic && (
          <Button
            type="button"
            size="icon"
            variant={isListening ? 'destructive' : 'outline'}
            onClick={handleMicClick}
            disabled={isLoading || isProcessing}
            className="h-9 w-9 shrink-0 relative"
            title={
              isProcessing
                ? '認識中...'
                : isListening
                  ? sttMode === 'auto' ? '自動検出停止' : '録音停止'
                  : sttMode === 'auto'
                    ? '自動検出開始'
                    : '音声入力'
            }
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isListening && isSpeaking ? (
              <AudioLines className="h-4 w-4 animate-pulse" />
            ) : isListening && sttMode === 'auto' ? (
              <Radio className="h-4 w-4 animate-pulse" />
            ) : isListening ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
            {isListening && audioLevel > 0.05 && (
              <span
                className="absolute inset-0 rounded-md border-2 border-red-400 pointer-events-none"
                style={{ opacity: Math.min(audioLevel * 2, 1) }}
              />
            )}
          </Button>
        )}

        <Button
          type="button"
          size="icon"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          className="h-9 w-9 shrink-0"
          title="送信"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  )
}
