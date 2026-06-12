import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useSTTMode } from '@/hooks/use-stt-mode'
import type { STTMode } from '@/hooks/use-server-stt'

interface SttContextValue {
  sttMode: STTMode
  setSTTMode: (mode: STTMode) => void
  cycleSTTMode: () => void
  sttLanguage: string
  setSTTLanguage: (lang: string) => void
  sttAutoSend: boolean
  toggleSTTAutoSend: () => void
}

const SttContext = createContext<SttContextValue | null>(null)

export function SttProvider({ children }: { children: ReactNode }) {
  const {
    mode: sttMode,
    setMode: setSTTMode,
    cycle: cycleSTTMode,
    language: sttLanguage,
    setLanguage: setSTTLanguage,
    autoSend: sttAutoSend,
    toggleAutoSend: toggleSTTAutoSend,
  } = useSTTMode()

  const value = useMemo<SttContextValue>(
    () => ({
      sttMode,
      setSTTMode,
      cycleSTTMode,
      sttLanguage,
      setSTTLanguage,
      sttAutoSend,
      toggleSTTAutoSend,
    }),
    [sttMode, setSTTMode, cycleSTTMode, sttLanguage, setSTTLanguage, sttAutoSend, toggleSTTAutoSend],
  )

  return <SttContext.Provider value={value}>{children}</SttContext.Provider>
}

export function useSttContext(): SttContextValue {
  const ctx = useContext(SttContext)
  if (!ctx) throw new Error('useSttContext must be used within SttProvider')
  return ctx
}
