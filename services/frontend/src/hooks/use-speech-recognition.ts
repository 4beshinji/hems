import { useState, useCallback, useRef } from 'react'

interface SpeechRecognitionOptions {
  lang?: string
  onResult: (text: string) => void
}

interface SpeechRecognitionHook {
  isListening: boolean
  start: () => void
  stop: () => void
  isSupported: boolean
}

export function useSpeechRecognition(opts: SpeechRecognitionOptions): SpeechRecognitionHook {
  const [isListening, setIsListening] = useState(false)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null)

  const SpeechRecognitionAPI =
    typeof window !== 'undefined'
      ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      : null

  const isSupported = !!SpeechRecognitionAPI

  const start = useCallback(() => {
    if (!SpeechRecognitionAPI || isListening) return

    const recognition = new SpeechRecognitionAPI()
    recognition.lang = opts.lang ?? 'ja-JP'
    recognition.interimResults = false
    recognition.continuous = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event: any) => {
      const text = event.results[0][0].transcript
      opts.onResult(text)
    }
    recognition.onend = () => setIsListening(false)
    recognition.onerror = () => setIsListening(false)

    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }, [SpeechRecognitionAPI, isListening, opts])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setIsListening(false)
  }, [])

  return { isListening, start, stop, isSupported }
}
