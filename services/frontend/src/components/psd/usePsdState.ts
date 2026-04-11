/**
 * PSD アバター統合状態管理
 *
 * voisona_yomiage の param_mapper パターン（ベース + オフセット合成）を参考に、
 * 3 つのソースを優先度付きで合成して PsdAvatarState を返す。
 *
 * 優先度（高 → 低）:
 *   1. リップシンク mouth   ← useAudioAnalyser 周波数、リアルタイム
 *   2. イベント駆動差分     ← TTL 付き（衣装/FX/小物/記号/表情）
 *   3. トーンベース表情     ← currentTone から（音声アクティブ時）
 *   4. デフォルト           ← DEFAULT_STATE
 */

import { useMemo } from 'react'
import { DEFAULT_STATE, type PsdAvatarState } from './psd-config'
import { usePsdLipSync } from './usePsdLipSync'
import { usePsdTone } from './usePsdTone'
import { usePsdEventDriven } from './usePsdEventDriven'

export function usePsdState(): PsdAvatarState {
  const mouth       = usePsdLipSync()
  const toneExpr    = usePsdTone()
  const eventDelta  = usePsdEventDriven()

  return useMemo<PsdAvatarState>(() => ({
    // 表情: イベント駆動 > トーン > デフォルト
    expression: eventDelta.expression ?? toneExpr,

    // 口: 常にリップシンク（最高優先）
    mouth,

    // 衣装: イベント駆動 > デフォルト
    costume: eventDelta.costume ?? DEFAULT_STATE.costume,

    // FX: デフォルトにイベント差分をスプレッドマージ（部分上書きを正しく処理）
    fx: { ...DEFAULT_STATE.fx, ...eventDelta.fx },

    // アクセサリー: 同上
    accessories: { ...DEFAULT_STATE.accessories, ...eventDelta.accessories },

    // 記号: イベント駆動のみ（通常は null）
    symbol: eventDelta.symbol ?? null,
  }), [mouth, toneExpr, eventDelta])
}
