/**
 * PSD 立ち絵 バストアップ表示
 *
 * サイドバーの空きスペースに配置する。
 * CSS scale でズームレベルを制御し、translateY で表示範囲を調整。
 *
 * ユーザー操作:
 *   - ホバーで [��] [+] ボタン表示 → ズーム調整
 *   - ドラッグ: 表示範囲（上下）調整
 *   - ダブルクリック: デフォルトにリセット
 * 設定は localStorage に永続化。
 */

import { useState, useCallback, useRef } from 'react'
import { Minus, Plus, RotateCcw } from 'lucide-react'
import { PsdAvatar } from './PsdAvatar'
import { usePsdState } from './usePsdState'

const LS_KEY = 'hems-psd-bust'
const DEFAULT_SCALE = 1.0
const DEFAULT_OFFSET_X = 0
const DEFAULT_OFFSET_Y = 0
const MIN_SCALE = 0.5
const SCALE_STEP = 0.15

interface BustSettings { scale: number; offsetX: number; offsetY: number }

function load(): BustSettings {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed.scale != null) return { scale: parsed.scale, offsetX: parsed.offsetX ?? 0, offsetY: parsed.offsetY ?? 0 }
    }
  } catch { /* ignore */ }
  return { scale: DEFAULT_SCALE, offsetX: DEFAULT_OFFSET_X, offsetY: DEFAULT_OFFSET_Y }
}

function save(s: BustSettings) {
  localStorage.setItem(LS_KEY, JSON.stringify(s))
}

export default function PsdBustUp() {
  const psdState = usePsdState()
  const [settings, setSettings] = useState(load)
  const dragRef = useRef<{ startX: number; startY: number; startOffsetX: number; startOffset: number } | null>(null)

  const zoomIn = useCallback(() => {
    setSettings(prev => {
      const next = { ...prev, scale: +(prev.scale + SCALE_STEP).toFixed(2) }
      save(next)
      return next
    })
  }, [])

  const zoomOut = useCallback(() => {
    setSettings(prev => {
      const next = { ...prev, scale: Math.max(MIN_SCALE, +(prev.scale - SCALE_STEP).toFixed(2)) }
      save(next)
      return next
    })
  }, [])

  const reset = useCallback(() => {
    const next = { scale: DEFAULT_SCALE, offsetX: DEFAULT_OFFSET_X, offsetY: DEFAULT_OFFSET_Y }
    save(next)
    setSettings(next)
  }, [])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button')) return
    (e.target as HTMLElement).setPointerCapture(e.pointerId)
    dragRef.current = { startY: e.clientY, startOffset: settings.offsetY, startX: e.clientX, startOffsetX: settings.offsetX }
  }, [settings.offsetX, settings.offsetY])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    setSettings(prev => ({ ...prev, offsetX: Math.round(dragRef.current!.startOffsetX + dx), offsetY: Math.round(dragRef.current!.startOffset + dy) }))
  }, [])

  const handlePointerUp = useCallback(() => {
    if (!dragRef.current) return
    dragRef.current = null
    setSettings(prev => { save(prev); return prev })
  }, [])

  return (
    <div
      className="w-full h-full overflow-hidden cursor-grab active:cursor-grabbing select-none relative group"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onDoubleClick={reset}
    >
      <div
        className="w-full aspect-[3/4] relative"
        style={{
          transform: `scale(${settings.scale}) translate(${settings.offsetX}px, ${settings.offsetY}px)`,
          transformOrigin: 'top center',
        }}
      >
        <PsdAvatar state={psdState} className="absolute inset-0" />
      </div>
      {/* Hover controls */}
      <div className="absolute top-1 right-1 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={zoomOut}
          className="h-6 w-6 rounded bg-background/80 backdrop-blur flex items-center justify-center hover:bg-background text-muted-foreground hover:text-foreground"
        >
          <Minus className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={reset}
          className="h-6 w-6 rounded bg-background/80 backdrop-blur flex items-center justify-center hover:bg-background text-muted-foreground hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={zoomIn}
          className="h-6 w-6 rounded bg-background/80 backdrop-blur flex items-center justify-center hover:bg-background text-muted-foreground hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}
