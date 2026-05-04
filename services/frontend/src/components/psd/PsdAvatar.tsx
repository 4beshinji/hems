/**
 * PSD 立ち絵アバター レンダラー
 *
 * 事前抽出した透明背景 PNG を CSS position:absolute で重ねて表示する。
 * 全レイヤーの objectFit / objectPosition を統一し、
 * 同一コンテナ内で位置ズレが起きないようにする。
 *
 * レイヤー構成（下→上）:
 *   1. 表情ベース（衣装×表情、口なし）
 *   2. 口オーバーレイ（リップシンク用）
 *   3. FX オーバーレイ（返り血・汗・目玉光る等）
 *   4. アクセサリー（猫耳・花・メガネ）
 *   5. 記号（！？びっくり）
 */

import { memo } from 'react'
import {
  type PsdAvatarState,
  ALL_EXPRESSIONS,
  ALL_COSTUMES,
  ALL_EYES,
  ALL_ARMS_LEFT,
  ALL_ARMS_RIGHT,
  ALL_MOUTHS,
  ALL_FX_KEYS,
  ALL_ACC_KEYS,
  ALL_SYMBOLS,
  exprUrl,
  eyesUrl,
  armLeftUrl,
  armRightUrl,
  mouthUrl,
  fxUrl,
  accessoryUrl,
  symbolUrl,
} from './psd-config'

// ── 共通レイヤースタイル ──────────────────────────────────────────────────

const LAYER_BASE: React.CSSProperties = {
  position:       'absolute',
  top:            0,
  left:           0,
  width:          '100%',
  height:         '100%',
  objectFit:      'contain',
  // objectPosition は全レイヤー共通で props から受け取る
  transition:     'opacity 0.12s ease',
  pointerEvents:  'none',
  userSelect:     'none',
}

// ── メインコンポーネント ────────────────────────────────────────────────────

interface Props {
  state:      PsdAvatarState
  className?: string
}

export const PsdAvatar = memo(function PsdAvatar({ state, className }: Props) {
  // パネル配置: 上寄せ（頭部優先）で統一
  // 全レイヤーが同じ objectPosition を使わないと口が顔に重ならない
  const objPos = 'top center'

  const layerStyle = (visible: boolean): React.CSSProperties => ({
    ...LAYER_BASE,
    objectPosition: objPos,
    opacity:        visible ? 1 : 0,
  })

  return (
    <div
      className={className}
      style={{ overflow: 'hidden' }}
    >
      {/* 1. 表情ベース（衣装 × 表情、口なし） */}
      {ALL_COSTUMES.flatMap(costume =>
        ALL_EXPRESSIONS.map(expression => (
          <img
            key={`expr_${costume}_${expression}`}
            src={exprUrl(costume, expression)}
            alt=""
            draggable={false}
            style={layerStyle(
              state.costume === costume && state.expression === expression
            )}
          />
        ))
      )}

      {/* 2. 腕オーバーレイ（default含む全ポーズ、ベースは腕なし） */}
      {ALL_ARMS_LEFT.map(arm => (
        <img
          key={`arm_l_${arm}`}
          src={armLeftUrl(arm)}
          alt=""
          draggable={false}
          style={layerStyle(state.armLeft === arm)}
        />
      ))}
      {ALL_ARMS_RIGHT.map(arm => (
        <img
          key={`arm_r_${arm}`}
          src={armRightUrl(arm)}
          alt=""
          draggable={false}
          style={layerStyle(state.armRight === arm)}
        />
      ))}

      {/* 3. 目オーバーレイ（瞬き・半目等） */}
      {ALL_EYES.map(eyes => (
        <img
          key={`eyes_${eyes}`}
          src={eyesUrl(eyes)}
          alt=""
          draggable={false}
          style={layerStyle(state.eyes === eyes)}
        />
      ))}

      {/* 4. 口オーバーレイ */}
      {ALL_MOUTHS.map(mouth => (
        <img
          key={`mouth_${mouth}`}
          src={mouthUrl(mouth)}
          alt=""
          draggable={false}
          style={layerStyle(state.mouth === mouth)}
        />
      ))}

      {/* 5. FX オーバーレイ */}
      {ALL_FX_KEYS.map(key => (
        <img
          key={`fx_${key}`}
          src={fxUrl(key)}
          alt=""
          draggable={false}
          style={layerStyle(state.fx[key])}
        />
      ))}

      {/* 6. アクセサリー */}
      {ALL_ACC_KEYS.map(key => (
        <img
          key={`acc_${key}`}
          src={accessoryUrl(key)}
          alt=""
          draggable={false}
          style={layerStyle(state.accessories[key])}
        />
      ))}

      {/* 7. 記号 */}
      {ALL_SYMBOLS.map(sym => (
        <img
          key={`sym_${sym}`}
          src={symbolUrl(sym)}
          alt=""
          draggable={false}
          style={layerStyle(state.symbol === sym)}
        />
      ))}
    </div>
  )
})
