/**
 * PSD トーン→表情マッピング
 *
 * useExpressionMapping.ts（VRM用）の tone ベース表情制御を移植。
 * AudioAnalyser.currentTone（脳が分類したトーン）→ PsdExpression を返す。
 *
 * voisona_yomiage の ParamMapper パターン:
 *   emotion → style_weights のスムーズ補間 の代わりに、
 *   tone → 離散 PsdExpression の即時切り替え（2D立ち絵のため）。
 */

import { useAudioAnalyser } from '@/audio'
import { TONE_EXPRESSION_MAP, type PsdExpression } from './psd-config'

/**
 * 現在の音声トーンに対応する表情を返す。
 * - 音声アクティブ: currentTone → PsdExpression
 * - 音声なし: 'neutral'
 */
export function usePsdTone(): PsdExpression {
  const { isActive, currentTone } = useAudioAnalyser()

  if (isActive && currentTone && currentTone in TONE_EXPRESSION_MAP) {
    return TONE_EXPRESSION_MAP[currentTone]
  }
  return 'neutral'
}
