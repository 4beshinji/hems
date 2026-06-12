import { createContext, useContext, useCallback, useMemo, type ReactNode } from 'react'
import { useAvatarMode, type AvatarMode } from '@/hooks/use-avatar-mode'

interface AvatarContextValue {
  avatarMode: AvatarMode
  cycleAvatarMode: () => void
  setAvatarMode: (mode: AvatarMode) => void
  hideAvatar: () => void
}

const AvatarContext = createContext<AvatarContextValue | null>(null)

export function AvatarProvider({ children }: { children: ReactNode }) {
  const { mode: avatarMode, cycle: cycleAvatarMode, setMode: setAvatarMode } = useAvatarMode()

  const hideAvatar = useCallback(() => setAvatarMode('hidden'), [setAvatarMode])

  const value = useMemo<AvatarContextValue>(
    () => ({ avatarMode, cycleAvatarMode, setAvatarMode, hideAvatar }),
    [avatarMode, cycleAvatarMode, setAvatarMode, hideAvatar],
  )

  return <AvatarContext.Provider value={value}>{children}</AvatarContext.Provider>
}

export function useAvatarContext(): AvatarContextValue {
  const ctx = useContext(AvatarContext)
  if (!ctx) throw new Error('useAvatarContext must be used within AvatarProvider')
  return ctx
}
