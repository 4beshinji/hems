/**
 * PSD イベント駆動状態マネージャー
 *
 * videofactory の EventDetector + EffectScheduler パターン:
 *   - API をポーリングし「新しいイベント」を検出
 *   - TTL 付きの状態差分キューに積む
 *   - クールダウンで重複発火を防ぐ（seen-set パターン）
 *
 * voisona_yomiage の SceneAnalyzer パターン:
 *   - タスク・センサー・バイオデータを「イベントキー」に変換
 *   - 各イベントが表情/衣装/FX/小物/記号に影響する
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchBiometric } from '@/lib/api'
import { useVoiceEvents } from '@/hooks/queries/use-voice-events'
import { useTasks } from '@/hooks/queries/use-tasks'
import { useZones } from '@/hooks/queries/use-zones'
import {
  EVENT_STATE_MAP,
  DEFAULT_FX,
  DEFAULT_ACCESSORIES,
  type EventStateDelta,
  type PsdAvatarState,
  type PsdFx,
  type PsdAccessories,
  type PsdCostume,
} from './psd-config'

// ── TTL 付き状態スタック ──────────────────────────────────────────────────

interface TimedState {
  key:       string
  delta:     EventStateDelta
  expiresAt: number   // 0 = 永続
}

// ── イベントキー発火 ─────────────────────────────────────────────────────

/** 環境アラートのクールダウン（ms）- 同じアラートが連続発火しないようにする */
const ENV_COOLDOWN_MS = 60_000

/**
 * イベント駆動の状態差分を管理するフック。
 * 現在有効な状態差分の合成値（Partial<PsdAvatarState>）を返す。
 */
export function usePsdEventDriven(): Partial<PsdAvatarState> {
  // TTL 付き状態スタック
  const stack = useRef<TimedState[]>([])
  // 合成済み出力（レンダリング用）
  const [merged, setMerged] = useState<Partial<PsdAvatarState>>({})

  // ── seen-set（重複発火防止）────────────────────────────────────────
  const seenTaskIds    = useRef<Set<number>>(new Set())
  const lastVoiceId    = useRef<number | null>(null)
  const envCooldowns   = useRef<Record<string, number>>({})
  // 初回ロードフラグ: 起動時の既存データを seen に登録するだけでイベントを発火しない
  const taskFirstLoad  = useRef(true)
  const voiceFirstLoad = useRef(true)

  // ── API ポーリング (共有 hook 経由 — TanStack dedup で重複 HTTP なし) ──
  const { data: tasks }   = useTasks()
  const { data: zones }   = useZones()
  const { data: voiceEvs} = useVoiceEvents()  // key='voiceEvents' に統一 (旧: 'voice-events')
  const { data: bio }     = useQuery({ queryKey: ['biometric'],    queryFn: fetchBiometric,    refetchInterval: 15_000 })

  // ── スタック合成ロジック ───────────────────────────────────────────
  const recompute = useCallback(() => {
    const now = Date.now()
    // 期限切れエントリを除去
    stack.current = stack.current.filter(s => s.expiresAt === 0 || s.expiresAt > now)

    // スタックを順に合成（後勝ち）
    let costume: PsdCostume | undefined
    const fx:   Partial<PsdFx>          = {}
    const acc:  Partial<PsdAccessories> = {}
    let expression = undefined
    let symbol     = undefined

    for (const s of stack.current) {
      if (s.delta.costume)     costume    = s.delta.costume
      if (s.delta.expression)  expression = s.delta.expression
      if (s.delta.symbol !== undefined) symbol = s.delta.symbol
      if (s.delta.fx)          Object.assign(fx,  s.delta.fx)
      if (s.delta.accessories) Object.assign(acc, s.delta.accessories)
    }

    const next: Partial<PsdAvatarState> = {}
    if (costume    !== undefined) next.costume     = costume
    if (expression !== undefined) next.expression  = expression
    if (symbol     !== undefined) next.symbol      = symbol
    if (Object.keys(fx).length)  next.fx           = { ...DEFAULT_FX,         ...fx  }
    if (Object.keys(acc).length) next.accessories  = { ...DEFAULT_ACCESSORIES, ...acc }

    setMerged(next)
  }, [])

  // ── イベント発火ヘルパー ──────────────────────────────────────────
  const fire = useCallback((key: string) => {
    const entry = EVENT_STATE_MAP[key]
    if (!entry) return

    // 既存の同キーエントリを置換（重複積み上げ防止）
    stack.current = stack.current.filter(s => s.key !== key)
    stack.current.push({
      key,
      delta:     entry.delta,
      expiresAt: entry.ttl > 0 ? Date.now() + entry.ttl : 0,
    })
    recompute()
  }, [recompute])

  const envFire = useCallback((key: string) => {
    const last = envCooldowns.current[key] ?? 0
    if (Date.now() - last < ENV_COOLDOWN_MS) return
    envCooldowns.current[key] = Date.now()
    fire(key)
  }, [fire])

  // ── TTL 期限監視タイマー ──────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(recompute, 1_000)
    return () => clearInterval(id)
  }, [recompute])

  // ── タスクイベント検出 ────────────────────────────────────────────
  useEffect(() => {
    if (!tasks) return

    if (taskFirstLoad.current) {
      // 初回: 既存タスクを全て seen に登録するだけ（イベント発火しない）
      for (const task of tasks) {
        seenTaskIds.current.add(task.id)
        if (task.is_completed) seenTaskIds.current.add(-task.id)
      }
      taskFirstLoad.current = false
      return
    }

    for (const task of tasks) {
      if (!seenTaskIds.current.has(task.id)) {
        seenTaskIds.current.add(task.id)
        if (!task.is_completed) {
          if (task.urgency >= 8) fire('task_urgent')
          else                    fire('task_created')
        }
      } else if (task.is_completed && !seenTaskIds.current.has(-task.id)) {
        seenTaskIds.current.add(-task.id)
        fire('task_completed')
      }
    }
  }, [tasks, fire])

  // ── 音声イベント検出（tone ≠ neutral の alert） ──────────────────
  // 注: トーンベースの表情は usePsdTone が担当。
  // ここでは tone=alert のみ task_urgent に準じる追加 FX を発火する。
  useEffect(() => {
    if (!voiceEvs?.length) return
    const latest = voiceEvs[0]

    if (voiceFirstLoad.current) {
      // 初回: 既存の最新IDを記録するだけ（発火しない）
      lastVoiceId.current = latest.id
      voiceFirstLoad.current = false
      return
    }

    if (latest.id === lastVoiceId.current) return
    lastVoiceId.current = latest.id
    // tone=alert で直近のタスクが高緊急度なら glow_red を追加
    if (latest.tone === 'alert') {
      const highUrgency = tasks?.some(t => !t.is_completed && t.urgency >= 8)
      if (highUrgency) fire('biometric_hr')  // glow_red を流用
    }
  }, [voiceEvs, tasks, fire])

  // ── 環境センサーアラート ─────────────────────────────────────────
  useEffect(() => {
    if (!zones) return
    for (const zone of zones) {
      const env = zone.environment
      if ((env.co2 ?? 0) > 1500)  envFire('alert_co2')
      if ((env.temperature ?? 0) > 28) envFire('alert_heat')
    }
  }, [zones, envFire])

  // ── バイオメトリクスアラート ─────────────────────────────────────
  useEffect(() => {
    if (!bio) return
    const hrBpm     = bio.heart_rate?.bpm          ?? 0
    const stress    = bio.stress?.score             ?? 0
    const fatigue   = bio.fatigue?.score            ?? 0

    if (hrBpm > 120)  envFire('biometric_hr')
    if (stress > 80)  envFire('biometric_stress')
    if (fatigue > 75) envFire('biometric_fatigue')
  }, [bio, envFire])

  return merged
}
