import { useState, useEffect, useCallback } from 'react'
import type { STTMode } from '@/hooks/use-server-stt'

const STORAGE_KEY = 'hems-stt-mode'
const LANG_STORAGE_KEY = 'hems-stt-language'
const AUTOSEND_STORAGE_KEY = 'hems-stt-autosend'

const MODE_ORDER: STTMode[] = ['push-to-talk', 'auto', 'off']

export function useSTTMode() {
  const [mode, setMode] = useState<STTMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return (stored as STTMode) || 'push-to-talk'
  })

  const [language, setLanguage] = useState(() => {
    return localStorage.getItem(LANG_STORAGE_KEY) || 'ja'
  })

  const [autoSend, setAutoSend] = useState(() => {
    return localStorage.getItem(AUTOSEND_STORAGE_KEY) !== 'false'
  })

  useEffect(() => { localStorage.setItem(STORAGE_KEY, mode) }, [mode])
  useEffect(() => { localStorage.setItem(LANG_STORAGE_KEY, language) }, [language])
  useEffect(() => { localStorage.setItem(AUTOSEND_STORAGE_KEY, String(autoSend)) }, [autoSend])

  const cycle = useCallback(() => {
    setMode((prev) => {
      const idx = MODE_ORDER.indexOf(prev)
      return MODE_ORDER[(idx + 1) % MODE_ORDER.length]
    })
  }, [])

  const toggleAutoSend = useCallback(() => {
    setAutoSend((prev) => !prev)
  }, [])

  return { mode, setMode, cycle, language, setLanguage, autoSend, setAutoSend, toggleAutoSend }
}
