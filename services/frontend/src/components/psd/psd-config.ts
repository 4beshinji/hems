/**
 * PSD 立ち絵アバター設定
 *
 * レイヤー→ファイルパスマップ、状態型定義、
 * イベント→状態マップ（videofactory EventDetector パターン）、
 * トーン→表情マップ（voisona_yomiage ParamMapper パターン）
 */

// ── 型定義 ─────────────────────────────────────────────────────────────────

export type PsdExpression = 'neutral' | 'happy' | 'sad' | 'surprised' | 'angry' | 'worried'
export type PsdMouth      = 'close' | 'smile' | 'hmm' | 'smile_open' | 'a' | 'i' | 'i_smile' | 'u' | 'e' | 'o' | 'o_big' | 'a_smile' | 'ahaha' | 'hawawa' | 'tongue' | 'hmph'
export type PsdEyes       = null | 'blink' | 'closed' | 'closed_smile' | 'normal_half' | 'jito_half' | 'wink_r' | 'wink_l' | 'qq' | 'gt_lt'
export type PsdArmLeft    = 'default' | 'down' | 'syringe' | 'point' | 'hip' | 'peace' | 'open'
export type PsdArmRight   = 'default' | 'hip' | 'point' | 'beckon' | 'peace' | 'open' | 'mouth'
export type PsdCostume    = 'official' | 'patient'
export type PsdSymbol     = 'exclamation' | 'question' | 'surprise' | null

export interface PsdFx {
  tears:       boolean
  sweat:       boolean
  damage:      boolean
  damage2:     boolean
  blood:       boolean
  shadow:      boolean
  glow_orange: boolean
  glow_red:    boolean
}

export interface PsdAccessories {
  cat_ears: boolean
  flower:   boolean
  glasses:  boolean
}

export interface PsdAvatarState {
  expression:  PsdExpression
  eyes:        PsdEyes
  mouth:       PsdMouth
  armLeft:     PsdArmLeft
  armRight:    PsdArmRight
  costume:     PsdCostume
  fx:          PsdFx
  accessories: PsdAccessories
  symbol:      PsdSymbol
}

// ── デフォルト状態 ─────────────────────────────────────────────────────────

export const DEFAULT_FX: PsdFx = {
  tears: false, sweat: false, damage: false, damage2: false,
  blood: false, shadow: false, glow_orange: false, glow_red: false,
}

export const DEFAULT_ACCESSORIES: PsdAccessories = {
  cat_ears: false, flower: false, glasses: false,
}

export const DEFAULT_STATE: PsdAvatarState = {
  expression:  'neutral',
  eyes:        null,
  mouth:       'close',
  armLeft:     'default',
  armRight:    'default',
  costume:     'official',
  fx:          DEFAULT_FX,
  accessories: DEFAULT_ACCESSORIES,
  symbol:      null,
}

// ── アセット URL ────────────────────────────────────────────────────────────

const BASE = '/assets/character/nurserobo'

export const ALL_EXPRESSIONS: PsdExpression[] = ['neutral', 'happy', 'sad', 'surprised', 'angry', 'worried']
export const ALL_COSTUMES: PsdCostume[]        = ['official', 'patient']
export const ALL_EYES: NonNullable<PsdEyes>[]  = ['blink', 'closed', 'closed_smile', 'normal_half', 'jito_half', 'wink_r', 'wink_l', 'qq', 'gt_lt']
export const ALL_ARMS_LEFT: PsdArmLeft[]       = ['default', 'down', 'syringe', 'point', 'hip', 'peace', 'open']
export const ALL_ARMS_RIGHT: PsdArmRight[]     = ['default', 'hip', 'point', 'beckon', 'peace', 'open', 'mouth']
export const ALL_MOUTHS: PsdMouth[]            = ['close', 'smile', 'hmm', 'smile_open', 'a', 'i', 'i_smile', 'u', 'e', 'o', 'o_big', 'a_smile', 'ahaha', 'hawawa', 'tongue', 'hmph']
export const ALL_FX_KEYS = ['tears', 'sweat', 'damage', 'damage2', 'blood', 'shadow', 'glow_orange', 'glow_red'] as const
export const ALL_ACC_KEYS = ['cat_ears', 'flower', 'glasses'] as const
export const ALL_SYMBOLS: Array<NonNullable<PsdSymbol>> = ['exclamation', 'question', 'surprise']

export const exprUrl = (costume: PsdCostume, expression: PsdExpression) =>
  `${BASE}/expr/${costume}_${expression}.png`

export const eyesUrl = (eyes: NonNullable<PsdEyes>) =>
  `${BASE}/eyes/${eyes}.png`

export const armLeftUrl = (arm: PsdArmLeft) =>
  `${BASE}/arms/left_${arm}.png`

export const armRightUrl = (arm: PsdArmRight) =>
  `${BASE}/arms/right_${arm}.png`

export const mouthUrl = (mouth: PsdMouth) =>
  `${BASE}/mouth/${mouth}.png`

export const fxUrl = (name: (typeof ALL_FX_KEYS)[number]) =>
  `${BASE}/fx/${name}.png`

export const accessoryUrl = (name: (typeof ALL_ACC_KEYS)[number]) =>
  `${BASE}/accessories/${name}.png`

export const symbolUrl = (symbol: NonNullable<PsdSymbol>) =>
  `${BASE}/symbols/${symbol}.png`

// ── イベント→状態マップ（videofactory EventDetector / EffectScheduler 参考）──
//
// videofactory では EventType ごとに SegmentEvent を生成し、
// EffectScheduler がクールダウン・発火確率を管理する。
// HEMS では MQTT/APIイベントを「イベントキー」に変換し、
// usePsdEventDriven がクールダウン（TTL）を管理する。

export interface EventStateDelta {
  expression?:  PsdExpression
  costume?:     PsdCostume
  symbol?:      PsdSymbol
  fx?:          Partial<PsdFx>
  accessories?: Partial<PsdAccessories>
}

export interface EventStateEntry {
  delta: EventStateDelta
  ttl:   number  // ms; 0 = persistent（ゲストモード等）
}

export const EVENT_STATE_MAP: Record<string, EventStateEntry> = {
  // タスク
  task_urgent:       { delta: { expression: 'surprised', symbol: 'exclamation', fx: { glow_red: true  } }, ttl: 12_000 },
  task_created:      { delta: { symbol: 'exclamation'                                                    }, ttl:  5_000 },
  task_completed:    { delta: { expression: 'happy'                                                      }, ttl:  6_000 },
  // 環境アラート
  alert_co2:         { delta: { fx: { sweat: true  }, expression: 'worried'                              }, ttl: 30_000 },
  alert_heat:        { delta: { fx: { sweat: true  }                                                     }, ttl: 30_000 },
  // バイオメトリクス
  biometric_hr:      { delta: { fx: { glow_red: true }, expression: 'surprised'                          }, ttl: 20_000 },
  biometric_stress:  { delta: { fx: { shadow: true  }, expression: 'worried'                             }, ttl: 30_000 },
  biometric_fatigue: { delta: { fx: { shadow: true  }                                                    }, ttl: 60_000 },
  // ニュース
  news_urgent:       { delta: { expression: 'surprised', symbol: 'exclamation', fx: { glow_orange: true }}, ttl: 15_000 },
  // ゲストモード（衣装切り替え）
  guest_mode_on:     { delta: { costume: 'patient'   }, ttl: 0 },
  guest_mode_off:    { delta: { costume: 'official'  }, ttl: 0 },
}

// ── トーン→表情マップ（voisona_yomiage ParamMapper パターン）──────────────
//
// AudioAnalyser.currentTone (脳が分類) → PsdExpression
// voisona_yomiage では emotion → style_weights でスムーズ補間するが、
// 2D立ち絵は離散スイッチなので単純マッピングで十分。

export const TONE_EXPRESSION_MAP: Record<string, PsdExpression> = {
  neutral:  'neutral',
  caring:   'worried',   // 困惑顔で優しく
  humorous: 'happy',
  alert:    'surprised',
}

// ── リップシンク: 周波数ビン → 口形状マップ ─────────────────────────────
//
// useLipSync.ts の母音分析アルゴリズムを流用し、
// VRM vowel 名 → PsdMouth へ変換する。

export const VOWEL_MOUTH_MAP: Record<string, PsdMouth> = {
  aa: 'a',   // /a/
  ih: 'i',   // /i/
  ou: 'u',   // /u/
  ee: 'i',   // /e/ → い で代替（えレイヤー省略）
  oh: 'o',   // /o/
}

/** リップシンク発動の音量閾値（この値未満は 'close'）*/
export const LIP_SYNC_THRESHOLD = 0.08
