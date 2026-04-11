import { useEffect, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { AvatarMode } from '@/hooks/use-avatar-mode'
import AvatarOverlay from './AvatarOverlay'
import AvatarPanel from './AvatarPanel'

const IS_PSD = (import.meta.env.VITE_AVATAR_TYPE as string | undefined) === 'psd'

interface Props {
  mode: AvatarMode
  onClose: () => void
}

export default function AvatarContainer({ mode, onClose }: Props) {
  const [panelSlot, setPanelSlot] = useState<HTMLElement | null>(null)

  // Watch for panel slot DOM element (VRM only — PSD はダッシュボードが直接描画)
  const checkSlot = useCallback(() => {
    setPanelSlot(document.getElementById('avatar-panel-slot'))
  }, [])

  useEffect(() => {
    if (IS_PSD) return  // PSD パネルはポータル不要
    checkSlot()
    const observer = new MutationObserver(checkSlot)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [mode, checkSlot])

  if (mode === 'hidden') return null

  // PSD + panel → ダッシュボードが直接描画するため何もしない
  if (IS_PSD && mode === 'panel') return null

  if (mode === 'overlay') {
    return <AvatarOverlay onClose={onClose} />
  }

  // VRM panel mode: portal into slot if available
  if (mode === 'panel') {
    return panelSlot ? createPortal(<AvatarPanel />, panelSlot) : null
  }

  return <AvatarOverlay onClose={onClose} />
}
