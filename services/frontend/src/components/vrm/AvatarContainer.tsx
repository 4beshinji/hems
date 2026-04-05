import { useEffect, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { AvatarMode } from '@/hooks/use-avatar-mode'
import AvatarOverlay from './AvatarOverlay'
import AvatarPanel from './AvatarPanel'

interface Props {
  mode: AvatarMode
  onClose: () => void
}

export default function AvatarContainer({ mode, onClose }: Props) {
  const [panelSlot, setPanelSlot] = useState<HTMLElement | null>(null)

  // Watch for panel slot DOM element
  const checkSlot = useCallback(() => {
    setPanelSlot(document.getElementById('avatar-panel-slot'))
  }, [])

  useEffect(() => {
    checkSlot()
    // Re-check when mode changes or on route navigation
    const observer = new MutationObserver(checkSlot)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [mode, checkSlot])

  if (mode === 'hidden') return null

  if (mode === 'overlay') {
    return <AvatarOverlay onClose={onClose} />
  }

  // Panel mode: portal into slot if available, otherwise hide
  if (mode === 'panel') {
    return panelSlot ? createPortal(<AvatarPanel />, panelSlot) : null
  }

  return <AvatarOverlay onClose={onClose} />
}
