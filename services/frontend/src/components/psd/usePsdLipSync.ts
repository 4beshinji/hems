/**
 * PSD リップシンク
 *
 * useLipSync.ts（VRM用）の母音分析アルゴリズムを流用し、
 * AudioAnalyser の周波数データから PsdMouth を決定する。
 *
 * VRM の useFrame ループの代わりに requestAnimationFrame を使用。
 */

import { useRef, useEffect, useState } from 'react'
import { useAudioAnalyser } from '@/audio'
import { VOWEL_MOUTH_MAP, LIP_SYNC_THRESHOLD, type PsdMouth } from './psd-config'

// useLipSync.ts と同じ周波数ビン定義
const LERP_SPEED  = 0.35
const DECAY_SPEED = 0.18

/**
 * useLipSync.ts の analyzeVowels と同一ロジック。
 * 周波数データ → [aa, ih, ou, ee, oh] ウェイト配列。
 */
function analyzeVowels(data: Uint8Array): [number, number, number, number, number] {
  if (data.length === 0) return [0, 0, 0, 0, 0]

  const norm = (start: number, end: number) => {
    let sum = 0
    for (let i = start; i < Math.min(end, data.length); i++) sum += data[i]
    return sum / (end - start) / 255
  }

  const low    = norm(2, 4)
  const midLow = norm(4, 7)
  const mid    = norm(5, 8)
  const high   = norm(13, 17)
  const total  = norm(2, 20)

  if (total < 0.05) return [0, 0, 0, 0, 0]

  const aa = Math.min(1, midLow * 2.5)
  const ih = Math.min(1, (low + high) * 1.2)
  const ou = Math.min(1, (low + mid * 0.5) * 1.8)
  const ee = Math.min(1, (low * 0.5 + high * 1.5) * 1.5)
  const oh = Math.min(1, (midLow * 0.8 + mid * 0.8) * 1.5)

  const maxVal = Math.max(aa, ih, ou, ee, oh, 0.01)
  return [aa / maxVal, ih / maxVal, ou / maxVal, ee / maxVal, oh / maxVal].map(
    v => v * total * 3
  ) as [number, number, number, number, number]
}

const VOWEL_NAMES = ['aa', 'ih', 'ou', 'ee', 'oh'] as const

/**
 * 現在の口形状を返す。
 * - 音声アクティブ: 周波数分析で母音を推定 → PsdMouth
 * - 音声なし: 'close'
 */
export function usePsdLipSync(): PsdMouth {
  const { isActive, getFrequencyData } = useAudioAnalyser()
  const weights   = useRef([0, 0, 0, 0, 0])
  const rafRef    = useRef(0)
  const [mouth, setMouth] = useState<PsdMouth>('close')

  useEffect(() => {
    const tick = () => {
      const data    = getFrequencyData()
      const targets = isActive ? analyzeVowels(data) : [0, 0, 0, 0, 0]
      const speed   = isActive ? LERP_SPEED : DECAY_SPEED

      for (let i = 0; i < 5; i++) {
        const prev = weights.current[i]
        weights.current[i] = prev + (targets[i] - prev) * speed
      }

      // 最大ウェイトの母音を口形状に変換
      const maxIdx = weights.current.reduce(
        (best, w, i) => (w > weights.current[best] ? i : best),
        0
      )
      const maxWeight = weights.current[maxIdx]

      if (maxWeight < LIP_SYNC_THRESHOLD) {
        setMouth('close')
      } else {
        const vowel = VOWEL_NAMES[maxIdx]
        setMouth(VOWEL_MOUTH_MAP[vowel] ?? 'close')
      }

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [isActive, getFrequencyData])

  return mouth
}
