import { useState, useRef, useCallback } from 'react'
import { Send, Mic, MicOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSpeechRecognition } from '@/hooks/use-speech-recognition'

interface ChatInputProps {
  onSend: (message: string) => void
  isLoading: boolean
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isLoading) return
    onSend(text)
    setInput('')
    // Reset textarea height
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
    // Auto-resize
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  const { isListening, start, stop, isSupported } = useSpeechRecognition({
    lang: 'ja-JP',
    onResult: (text) => {
      setInput((prev) => (prev ? prev + ' ' + text : text))
    },
  })

  return (
    <div className="flex items-end gap-2 w-full">
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

      {isSupported && (
        <Button
          type="button"
          size="icon"
          variant={isListening ? 'destructive' : 'outline'}
          onClick={isListening ? stop : start}
          disabled={isLoading}
          className="h-9 w-9 shrink-0"
          title={isListening ? '録音停止' : '音声入力'}
        >
          {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
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
  )
}
