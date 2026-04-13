// Zone display labels
export const ZONE_LABELS: Record<string, string> = {
  living_room: 'リビング',
  bedroom: '寝室',
  kitchen: 'キッチン',
  bathroom: '浴室',
  entrance: '玄関',
  office: 'オフィス',
  study: '書斎',
  balcony: 'バルコニー',
}

// Task urgency levels (0–4)
export const URGENCY_LABELS: Record<number, string> = {
  0: '超低',
  1: '低',
  2: '通常',
  3: '高',
  4: '緊急',
}

export const URGENCY_VARIANTS: Record<number, 'success' | 'info' | 'secondary' | 'warning' | 'destructive'> = {
  0: 'success',
  1: 'info',
  2: 'secondary',
  3: 'warning',
  4: 'destructive',
}

// Climate modes — used as both value and display text in ClimateCard
export const CLIMATE_MODES = ['off', 'heat', 'cool', 'auto'] as const

// Posture labels from perception service
export const POSTURE_LABELS: Record<string, string> = {
  standing: '立位',
  sitting: '座位',
  lying: '横臥',
  walking: '歩行',
  unknown: '不明',
}

// Task completion report statuses
export const REPORT_STATUS_LABELS: Record<string, string> = {
  no_issue: '問題なし',
  partial: '部分完了',
  issue: '問題あり',
  impossible: '実行不可',
}

// Timeline slot kind → display metadata
export const TIMELINE_KIND_LABELS: Record<string, string> = {
  calendar: '予定',
  task: 'タスク',
  routine_wake: '起床',
  commute_out: '外出移動',
  commute_in: '帰宅移動',
  focus_free: '集中時間',
  sleep: '睡眠',
  prep: '準備',
}

export const TIMELINE_KIND_COLORS: Record<string, string> = {
  calendar: 'bg-indigo-500/20 border-indigo-500/60 text-indigo-700 dark:text-indigo-300',
  task: 'bg-amber-500/20 border-amber-500/60 text-amber-700 dark:text-amber-300',
  routine_wake: 'bg-orange-500/20 border-orange-500/60 text-orange-700 dark:text-orange-300',
  commute_out: 'bg-slate-500/20 border-slate-500/60 text-slate-700 dark:text-slate-300',
  commute_in: 'bg-slate-500/20 border-slate-500/60 text-slate-700 dark:text-slate-300',
  focus_free: 'bg-emerald-500/20 border-emerald-500/60 text-emerald-700 dark:text-emerald-300',
  sleep: 'bg-zinc-500/20 border-zinc-500/60 text-zinc-600 dark:text-zinc-400',
  prep: 'bg-rose-500/20 border-rose-500/60 text-rose-700 dark:text-rose-300',
}

export const TASK_SOURCE_LABELS: Record<string, string> = {
  user: 'ユーザー',
  'extractor:pws': 'AI 抽出 (pws)',
  'extractor:obsidian': 'AI 抽出',
  prep_auto: '準備 (自動)',
}
