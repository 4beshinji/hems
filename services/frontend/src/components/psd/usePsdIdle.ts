/**
 * PSD アバター アイドルアニメーション
 *
 * VRM の useIdleAnimations / useIdleMotionPlayer に相当。
 * 2D 立ち絵で実現可能な範囲のアイドル挙動:
 *
 *   1. 瞬き — blink オーバーレイ (閉じ→開き state machine)
 *   2. 腕ポーズ切替 — 一定間隔で左右の腕ポーズをランダム変更
 *
 * prefers-reduced-motion を尊重してアニメーション無効化。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { PsdEyes, PsdArmLeft, PsdArmRight } from './psd-config'

// ── Blink timings ───────────────────────────────────────────────────────────

const BLINK_CLOSE_MS  = 60   // closing phase
const BLINK_HOLD_MS   = 80   // held closed
const BLINK_OPEN_MS   = 80   // opening phase
const BLINK_MIN_MS    = 2000 // min interval between blinks
const BLINK_RANGE_MS  = 4000 // random range added to min

// ── Arm pose timings ────────────────────────────────────────────────────────

const ARM_MIN_MS    = 12000  // min interval between arm changes
const ARM_RANGE_MS  = 18000  // random range

// Idle arm pool (exclude syringe — too dramatic for idle)
const IDLE_ARMS_LEFT: PsdArmLeft[]   = ['default', 'default', 'down', 'hip', 'open']
const IDLE_ARMS_RIGHT: PsdArmRight[] = ['default', 'default', 'hip', 'beckon', 'open', 'mouth']

// ── Hook ────────────────────────────────────────────────────────────────────

export interface PsdIdleState {
  eyes:     PsdEyes
  armLeft:  PsdArmLeft
  armRight: PsdArmRight
}

export function usePsdIdle(): PsdIdleState {
  const [eyes, setEyes]         = useState<PsdEyes>(null)
  const [armLeft, setArmLeft]   = useState<PsdArmLeft>('default')
  const [armRight, setArmRight] = useState<PsdArmRight>('default')

  const reducedMotion = useRef(false)
  useEffect(() => {
    reducedMotion.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  // ── Blink state machine ─────────────────────────────────────────────────

  const blinkPhase = useRef<'idle' | 'closing' | 'closed' | 'opening'>('idle')
  const blinkTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  const scheduleBlink = useCallback(() => {
    if (reducedMotion.current) return
    const delay = BLINK_MIN_MS + Math.random() * BLINK_RANGE_MS
    blinkTimer.current = setTimeout(() => {
      // closing
      blinkPhase.current = 'closing'
      setEyes('blink')

      blinkTimer.current = setTimeout(() => {
        // closed hold
        blinkPhase.current = 'closed'

        blinkTimer.current = setTimeout(() => {
          // opening → clear
          blinkPhase.current = 'opening'
          setEyes(null)

          blinkTimer.current = setTimeout(() => {
            blinkPhase.current = 'idle'
            scheduleBlink()
          }, BLINK_OPEN_MS)
        }, BLINK_HOLD_MS)
      }, BLINK_CLOSE_MS)
    }, delay)
  }, [])

  useEffect(() => {
    scheduleBlink()
    return () => clearTimeout(blinkTimer.current)
  }, [scheduleBlink])

  // ── Arm pose cycling ────────────────────────────────────────────────────

  const armTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  const scheduleArmChange = useCallback(() => {
    if (reducedMotion.current) return
    const delay = ARM_MIN_MS + Math.random() * ARM_RANGE_MS
    armTimer.current = setTimeout(() => {
      setArmLeft(IDLE_ARMS_LEFT[Math.floor(Math.random() * IDLE_ARMS_LEFT.length)])
      setArmRight(IDLE_ARMS_RIGHT[Math.floor(Math.random() * IDLE_ARMS_RIGHT.length)])
      scheduleArmChange()
    }, delay)
  }, [])

  useEffect(() => {
    scheduleArmChange()
    return () => clearTimeout(armTimer.current)
  }, [scheduleArmChange])

  return { eyes, armLeft, armRight }
}
