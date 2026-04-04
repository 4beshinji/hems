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
