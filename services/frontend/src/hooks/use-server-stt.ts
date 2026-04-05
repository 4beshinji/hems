/**
 * Server-side STT hook.
 * Supports push-to-talk and VAD auto modes.
 * Falls back to Web Speech API when STT service is unavailable.
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { useAudioCapture } from '@/audio/useAudioCapture'
import { useSileroVAD } from '@/audio/useSileroVAD'
import { transcribeAudio, checkSTTAvailable } from '@/lib/api/stt'
import { useSpeechRecognition } from '@/hooks/use-speech-recognition'

export type STTMode = 'push-to-talk' | 'auto' | 'off'

export interface ServerSTTOptions {
  mode: STTMode
  language?: string
  onResult: (cleanedText: string, rawText: string) => void
  onError?: (error: string) => void
  onListeningChange?: (listening: boolean) => void
}

export interface ServerSTTHook {
  isListening: boolean
  isProcessing: boolean
  isSpeaking: boolean
  isSupported: boolean
  useServerSTT: boolean
  startListening: () => void
  stopListening: () => void
  audioLevel: number
}

export function useServerSTT(opts: ServerSTTOptions): ServerSTTHook {
  const [isProcessing, setIsProcessing] = useState(false)
  const [serverAvailable, setServerAvailable] = useState<boolean | null>(null)
  const optsRef = useRef(opts)
  optsRef.current = opts

  // Check STT service availability on mount
  useEffect(() => {
    checkSTTAvailable().then((info) => {
      setServerAvailable(info !== null)
    })
  }, [])

  // Audio capture (push-to-talk)
  const audioCapture = useAudioCapture()

  // VAD (auto mode)
  const vad = useSileroVAD({
    onSpeechStart: () => {
      optsRef.current.onListeningChange?.(true)
    },
    onSpeechEnd: async (audio) => {
      optsRef.current.onListeningChange?.(false)
      await processAudio(audio)
    },
    threshold: 0.5,
    silenceTimeout: 800,
  })

  // Web Speech API fallback
  const webSpeech = useSpeechRecognition({
    lang: opts.language === 'en' ? 'en-US' : 'ja-JP',
    onResult: (text) => {
      optsRef.current.onResult(text, text)
    },
  })

  const useServer = serverAvailable === true
  const serverChecked = serverAvailable !== null
  const isOff = opts.mode === 'off'

  const processAudio = useCallback(
    async (blob: Blob) => {
      setIsProcessing(true)
      try {
        const result = await transcribeAudio(
          blob,
          optsRef.current.language ?? 'ja',
        )
        if (result.cleaned_text || result.text) {
          optsRef.current.onResult(
            result.cleaned_text || result.text,
            result.text,
          )
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        optsRef.current.onError?.(msg)
      } finally {
        setIsProcessing(false)
      }
    },
    [],
  )

  // Push-to-talk: start
  const startListening = useCallback(() => {
    if (isOff) return

    if (useServer) {
      if (opts.mode === 'auto') {
        vad.start()
      } else {
        audioCapture.startRecording()
      }
      return
    }

    // Server not available (or still checking) — try audio capture if supported,
    // otherwise fall back to Web Speech API
    if (!serverChecked && audioCapture.isSupported) {
      // Still checking — use audio capture optimistically; if server turns out
      // unavailable the blob will fail to transcribe and we'll get an error callback
      audioCapture.startRecording()
      return
    }

    // Fallback: Web Speech API
    webSpeech.start()
  }, [isOff, opts.mode, useServer, serverChecked, vad, audioCapture, webSpeech])

  // Push-to-talk: stop + transcribe
  const stopListening = useCallback(async () => {
    if (opts.mode === 'auto' && useServer) {
      vad.stop()
      return
    }

    if (opts.mode === 'push-to-talk' && useServer) {
      const blob = await audioCapture.stopRecording()
      if (blob) {
        await processAudio(blob)
      }
      return
    }

    // Fallback
    webSpeech.stop()
  }, [opts.mode, useServer, audioCapture, vad, webSpeech, processAudio])

  const isListening =
    (useServer && opts.mode === 'push-to-talk' && audioCapture.isRecording) ||
    (useServer && opts.mode === 'auto' && vad.isListening) ||
    (!useServer && webSpeech.isListening)

  // Show mic if: server STT available, OR browser supports Web Speech API,
  // OR still checking server availability (optimistic — show button early)
  const isSupported =
    (useServer && audioCapture.isSupported) ||
    (!useServer && webSpeech.isSupported) ||
    (!serverChecked && audioCapture.isSupported)

  // Notify parent of listening state changes
  useEffect(() => {
    optsRef.current.onListeningChange?.(isListening)
  }, [isListening])

  return {
    isListening,
    isProcessing,
    isSpeaking: vad.isSpeaking,
    isSupported,
    useServerSTT: useServer,
    startListening,
    stopListening,
    audioLevel: audioCapture.audioLevel,
  }
}
