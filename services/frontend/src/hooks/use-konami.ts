import { useEffect, useRef } from 'react'

interface KonamiSequence {
  keys: string[]
  onActivate: () => void
}

export function useKonami(sequences: KonamiSequence[], timeout = 3000) {
  const bufferRef = useRef<string[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      bufferRef.current.push(e.key.toLowerCase())

      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        bufferRef.current = []
      }, timeout)

      for (const seq of sequences) {
        const buf = bufferRef.current
        if (buf.length >= seq.keys.length) {
          const tail = buf.slice(-seq.keys.length)
          if (tail.every((k, i) => k === seq.keys[i])) {
            seq.onActivate()
            bufferRef.current = []
            clearTimeout(timerRef.current)
            break
          }
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
      clearTimeout(timerRef.current)
    }
  }, [sequences, timeout])
}
