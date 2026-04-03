import { useState, useEffect, useCallback } from 'react'

export type AvatarMode = 'hidden' | 'panel' | 'overlay'

const STORAGE_KEY = 'hems-avatar-mode'

export function useAvatarMode() {
  const [mode, setMode] = useState<AvatarMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return (stored as AvatarMode) || 'hidden'
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode)
  }, [mode])

  const cycle = useCallback(() => {
    setMode((prev) => {
      const order: AvatarMode[] = ['hidden', 'panel', 'overlay']
      const idx = order.indexOf(prev)
      return order[(idx + 1) % order.length]
    })
  }, [])

  return { mode, setMode, cycle }
}
