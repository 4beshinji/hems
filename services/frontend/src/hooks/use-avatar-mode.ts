import { useState, useEffect, useCallback } from 'react'
import { IS_PSD } from '@/lib/avatar-type'

export type AvatarMode = 'hidden' | 'panel' | 'overlay'

const STORAGE_KEY = 'hems-avatar-mode'

// PSD モード: hidden ↔ panel のみ（overlay 不要）
// VRM モード: hidden → panel → overlay の3段階
const CYCLE_ORDER: AvatarMode[] = IS_PSD
  ? ['hidden', 'panel']
  : ['hidden', 'panel', 'overlay']

const DEFAULT_MODE: AvatarMode = IS_PSD ? 'panel' : 'hidden'

export function useAvatarMode() {
  const [mode, setMode] = useState<AvatarMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as AvatarMode | null
    if (IS_PSD) {
      // PSD モード: 保存値が 'panel' でなければ強制 'panel'
      // （旧 VRM 設定の 'hidden'/'overlay' が残っている場合のリセット）
      return stored === 'panel' ? 'panel' : DEFAULT_MODE
    }
    if (stored && CYCLE_ORDER.includes(stored)) return stored
    return DEFAULT_MODE
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode)
  }, [mode])

  const cycle = useCallback(() => {
    setMode((prev) => {
      const idx = CYCLE_ORDER.indexOf(prev)
      return CYCLE_ORDER[(idx + 1) % CYCLE_ORDER.length]
    })
  }, [])

  return { mode, setMode, cycle }
}
