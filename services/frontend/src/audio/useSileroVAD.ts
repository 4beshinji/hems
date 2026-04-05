/**
 * Silero VAD (Voice Activity Detection) hook using @ricky0123/vad-web.
 * Detects speech segments in real-time and emits audio blobs.
 */
import { useState, useRef, useCallback, useEffect } from 'react'

export interface VADOptions {
  /** Called when speech starts (for visual indicator) */
  onSpeechStart?: () => void
  /** Called when a speech segment ends, with the audio blob */
  onSpeechEnd: (audio: Blob) => void
  /** VAD probability threshold (0-1, default 0.5) */
  threshold?: number
  /** Minimum speech duration in ms (default 300) */
  minSpeechDuration?: number
  /** Silence timeout after speech ends in ms (default 800) */
  silenceTimeout?: number
}

export interface VADHook {
  isListening: boolean
  isSpeaking: boolean
  isSupported: boolean
  start: () => Promise<void>
  stop: () => void
}

export function useSileroVAD(opts: VADOptions): VADHook {
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vadRef = useRef<any>(null)
  const optsRef = useRef(opts)
  optsRef.current = opts

  const isSupported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof AudioContext !== 'undefined'

  const start = useCallback(async () => {
    if (isListening || !isSupported) return

    try {
      // Dynamic import to avoid bundling if not used
      const { MicVAD } = await import('@ricky0123/vad-web')

      const vad = await MicVAD.new({
        positiveSpeechThreshold: optsRef.current.threshold ?? 0.5,
        negativeSpeechThreshold: (optsRef.current.threshold ?? 0.5) - 0.15,
        minSpeechMs: optsRef.current.minSpeechDuration ?? 300,
        redemptionMs: optsRef.current.silenceTimeout ?? 800,
        onSpeechStart: () => {
          setIsSpeaking(true)
          optsRef.current.onSpeechStart?.()
        },
        onSpeechEnd: (audio: Float32Array) => {
          setIsSpeaking(false)
          // Convert Float32Array to WAV blob
          const blob = float32ToWavBlob(audio, 16000)
          optsRef.current.onSpeechEnd(blob)
        },
      })

      vad.start()
      vadRef.current = vad
      setIsListening(true)
    } catch (err) {
      console.error('Failed to start VAD:', err)
    }
  }, [isListening, isSupported])

  const stop = useCallback(() => {
    if (vadRef.current) {
      vadRef.current.pause()
      vadRef.current.destroy()
      vadRef.current = null
    }
    setIsListening(false)
    setIsSpeaking(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (vadRef.current) {
        vadRef.current.pause()
        vadRef.current.destroy()
        vadRef.current = null
      }
    }
  }, [])

  return { isListening, isSpeaking, isSupported, start, stop }
}

/** Convert Float32Array PCM samples to WAV Blob */
function float32ToWavBlob(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  // WAV header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // chunk size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeString(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)

  // PCM data
  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}
