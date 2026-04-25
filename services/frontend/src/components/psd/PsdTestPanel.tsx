/**
 * PSD アバター 疑似データ注入テストパネル（開発専用）
 *
 * import.meta.env.DEV のときのみ表示。
 * TanStack Query キャッシュに直接モックデータを注入し、
 * usePsdEventDriven の各イベント経路を実際に通して動作確認する。
 */

import { useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { audioAnalyser } from '@/audio/AudioAnalyser'
import type { TaskData, VoiceEvent, ZoneSnapshot, BiometricData } from '@/lib/types'

// ── モックデータ生成 ────────────────────────────────────────────────────────

function mockTask(overrides: Partial<TaskData>): TaskData {
  return {
    id: Date.now(),
    title: 'テストタスク',
    urgency: 5,
    is_completed: false,
    is_queued: false,
    estimated_duration: 30,
    ...overrides,
  }
}

function mockVoiceEvent(tone: string): VoiceEvent {
  return {
    id: Date.now(),
    message: `テスト発話（${tone}）`,
    audio_url: '',
    tone,
    created_at: new Date().toISOString(),
  }
}

function mockZone(temp: number, co2: number): ZoneSnapshot {
  return {
    zone_id: 'test',
    environment: { temperature: temp, co2, humidity: 50 },
    occupancy: { count: 1 },
  }
}

function mockBio(hrBpm: number, stress: number, fatigue: number): BiometricData {
  return {
    heart_rate: { bpm: hrBpm, zone: hrBpm > 100 ? 'high' : 'normal' },
    stress:     { score: stress, category: stress > 70 ? 'high' : 'normal' },
    fatigue:    { score: fatigue },
  }
}

// ── テストシナリオ定義 ───────────────────────────────────────────────────────

interface Scenario {
  label:   string
  emoji:   string
  color:   string
  action:  (qc: ReturnType<typeof useQueryClient>, nextId: () => number) => void
}

const SCENARIOS: Scenario[] = [
  {
    label: 'リセット',
    emoji: '↩️',
    color: '#555',
    action: (qc) => {
      qc.setQueryData(['tasks'],        [])
      qc.setQueryData(['zones'],        [])
      qc.setQueryData(['voice-events'], [])
      qc.setQueryData(['biometric'],    {})
      audioAnalyser.setTestTone(null, 0)
    },
  },
  // ── トーン（表情のみ、FXなし）──────────────────────────────────────────
  {
    label: 'tone: caring',
    emoji: '🌸',
    color: '#c084fc',
    action: () => audioAnalyser.setTestTone('caring', 5000),
  },
  {
    label: 'tone: humorous',
    emoji: '😄',
    color: '#facc15',
    action: () => audioAnalyser.setTestTone('humorous', 5000),
  },
  {
    label: 'tone: alert',
    emoji: '⚡',
    color: '#f97316',
    action: () => audioAnalyser.setTestTone('alert', 5000),
  },
  // ── タスクイベント ─────────────────────────────────────────────────────
  {
    label: 'task_created',
    emoji: '📋',
    color: '#60a5fa',
    action: (qc, nextId) => {
      qc.setQueryData(['tasks'], (old: TaskData[] = []) => [
        mockTask({ id: nextId(), title: '新規タスク', urgency: 5 }),
        ...old.slice(0, 10),
      ])
    },
  },
  {
    label: 'task_urgent',
    emoji: '🚨',
    color: '#ef4444',
    action: (qc, nextId) => {
      qc.setQueryData(['tasks'], (old: TaskData[] = []) => [
        mockTask({ id: nextId(), title: '緊急タスク！', urgency: 9 }),
        ...old.slice(0, 10),
      ])
    },
  },
  {
    label: 'task_completed',
    emoji: '✅',
    color: '#22c55e',
    action: (qc, nextId) => {
      // 未完了タスクを新規追加 → 次のポーリングで seen に登録済みになるため、
      // 直接 completed=true で注入するとタスクが既知でないため completion は発火しない。
      // ここでは: まず未完了タスクを注入し、1秒後に完了状態にする。
      const id = nextId()
      qc.setQueryData(['tasks'], (old: TaskData[] = []) => [
        mockTask({ id, title: '完了タスク', urgency: 5, is_completed: false }),
        ...old.slice(0, 10),
      ])
      // firstLoad が false になるタイミングを待ってから完了させる
      setTimeout(() => {
        qc.setQueryData(['tasks'], (old: TaskData[] = []) =>
          old.map(t => t.id === id ? { ...t, is_completed: true } : t)
        )
      }, 1200)
    },
  },
  // ── 環境アラート ───────────────────────────────────────────────────────
  {
    label: 'alert_co2',
    emoji: '💨',
    color: '#a3e635',
    action: (qc) => qc.setQueryData(['zones'], [mockZone(24, 1600)]),
  },
  {
    label: 'alert_heat',
    emoji: '🌡️',
    color: '#fb923c',
    action: (qc) => qc.setQueryData(['zones'], [mockZone(29, 800)]),
  },
  // ── バイオメトリクス ───────────────────────────────────────────────────
  {
    label: 'biometric_hr',
    emoji: '💓',
    color: '#f43f5e',
    action: (qc) => qc.setQueryData(['biometric'], mockBio(130, 50, 30)),
  },
  {
    label: 'biometric_stress',
    emoji: '😰',
    color: '#8b5cf6',
    action: (qc) => qc.setQueryData(['biometric'], mockBio(80, 85, 40)),
  },
  {
    label: 'biometric_fatigue',
    emoji: '😴',
    color: '#64748b',
    action: (qc) => qc.setQueryData(['biometric'], mockBio(70, 50, 80)),
  },
  // ── ゲストモード ───────────────────────────────────────────────────────
  {
    label: 'voice_event (alert)',
    emoji: '🔔',
    color: '#e879f9',
    action: (qc) => {
      qc.setQueryData(['voice-events'], (old: VoiceEvent[] = []) => [
        mockVoiceEvent('alert'),
        ...old.slice(0, 5),
      ])
    },
  },
]

// ── アバターモーション（VRMA）テストシナリオ ────────────────────────────────
// 全 16 モーション、ボタン押下で 1 回再生する。

const MOTION_IDS = [
  'greeting_wave', 'celebrate', 'point_alert', 'stretch_suggest', 'show_full',
  'spin', 'model_pose', 'thinking_pose', 'wave_goodbye', 'surprise_react',
  'nod_agree', 'bow_polite', 'shrug_confused', 'look_around', 'relax', 'sleepy',
] as const

const MOTION_SCENARIOS: Scenario[] = MOTION_IDS.map((id) => ({
  label: id,
  emoji: '🎭',
  color: '#10b981',
  action: () => audioAnalyser.setTestMotion(id),
}))

// ── コンポーネント ───────────────────────────────────────────────────────────

export function PsdTestPanel() {
  if (!import.meta.env.DEV) return null

  const qc = useQueryClient()
  const idCounter = useRef(100_000)
  const nextId = useCallback(() => ++idCounter.current, [])

  return (
    <div
      style={{
        position:        'fixed',
        top:             8,
        right:           8,
        zIndex:          9999,
        background:      'rgba(0,0,0,0.85)',
        border:          '1px solid #333',
        borderRadius:    8,
        padding:         '8px 10px',
        display:         'flex',
        flexWrap:        'wrap',
        gap:             4,
        maxWidth:        360,
        backdropFilter:  'blur(4px)',
      }}
    >
      <div style={{ width: '100%', color: '#888', fontSize: 10, marginBottom: 2 }}>
        PSD Avatar Test — DEV only
      </div>
      {SCENARIOS.map(s => (
        <button
          key={s.label}
          onClick={() => s.action(qc, nextId)}
          title={s.label}
          style={{
            background:   s.color + '22',
            border:       `1px solid ${s.color}66`,
            borderRadius: 4,
            color:        '#eee',
            cursor:       'pointer',
            fontSize:     11,
            padding:      '3px 7px',
            whiteSpace:   'nowrap',
          }}
        >
          {s.emoji} {s.label}
        </button>
      ))}
      <div style={{ width: '100%', color: '#888', fontSize: 10, marginTop: 6, marginBottom: 2 }}>
        Avatar motions (VRMA)
      </div>
      {MOTION_SCENARIOS.map(s => (
        <button
          key={s.label}
          onClick={() => s.action(qc, nextId)}
          title={s.label}
          style={{
            background:   s.color + '22',
            border:       `1px solid ${s.color}66`,
            borderRadius: 4,
            color:        '#eee',
            cursor:       'pointer',
            fontSize:     11,
            padding:      '3px 7px',
            whiteSpace:   'nowrap',
          }}
        >
          {s.emoji} {s.label}
        </button>
      ))}
    </div>
  )
}
