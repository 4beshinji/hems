/**
 * Audio capture hook using MediaRecorder API.
 * Records mono audio as WebM/Opus for efficient upload.
 */
import { useState, useRef, useCallback, useEffect } from 'react'

export interface AudioCaptureHook {
  isRecording: boolean
  isSupported: boolean
  audioLevel: number
  startRecording: () => Promise<void>
  stopRecording: () => Promise<Blob | null>
}

export function useAudioCapture(): AudioCaptureHook {
  const [isRecording, setIsRecording] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number>(0)

  const isSupported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'

  const startRecording = useCallback(async () => {
    if (isRecording || !isSupported) return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      // Audio level meter
      const audioCtx = new AudioContext()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const updateLevel = () => {
        if (!analyserRef.current) return
        analyserRef.current.getByteFrequencyData(dataArray)
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length
        setAudioLevel(avg / 255)
        rafRef.current = requestAnimationFrame(updateLevel)
      }
      updateLevel()

      // MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorderRef.current = recorder
      recorder.start(100) // collect chunks every 100ms
      setIsRecording(true)
    } catch (err) {
      console.error('Failed to start recording:', err)
    }
  }, [isRecording, isSupported])

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    if (!recorderRef.current || recorderRef.current.state === 'inactive') {
      return null
    }

    return new Promise((resolve) => {
      const recorder = recorderRef.current!
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType })
        chunksRef.current = []

        // Cleanup
        cancelAnimationFrame(rafRef.current)
        analyserRef.current = null
        setAudioLevel(0)

        streamRef.current?.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        recorderRef.current = null
        setIsRecording(false)

        resolve(blob.size > 0 ? blob : null)
      }
      recorder.stop()
    })
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current)
      streamRef.current?.getTracks().forEach((t) => t.stop())
      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.stop()
      }
    }
  }, [])

  return { isRecording, isSupported, audioLevel, startRecording, stopRecording }
}
