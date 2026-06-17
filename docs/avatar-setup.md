# アバター セットアップガイド

Dashboard にキャラクターを表示し、Brain の発話に連動して表情・口パク・モーションを行うオプション機能。
アバターの有無は他の機能に一切影響しない — 設定しなくてもシステムは正常動作する。

## 表示方式の切り替え

フロントエンドはビルド時に以下の 2 方式から選択する。

| 方式 | 説明 | ビルド変数 |
|------|------|-----------|
| PSD 2D 立ち絵 | 透明背景 PNG を重ねて表示。**現在のデフォルト。** | `VITE_AVATAR_TYPE=psd` |
| VRM 3D | `.vrm` モデルを WebGL で表示。 | `VITE_AVATAR_TYPE=vrm` |

未指定時は `psd` が使われる。VRM を利用する際はビルド前に環境変数を設定する:

```bash
# 例: ローカル開発
cd services/frontend
VITE_AVATAR_TYPE=vrm pnpm dev

# 例: 本番ビルド
VITE_AVATAR_TYPE=vrm pnpm build
```

Compose 経由でビルドする場合は `.env` または `docker compose build` 時に `VITE_AVATAR_TYPE` を渡す。

> **Note**: `VITE_AVATAR_TYPE` はビルド時定数なので、実行中に切り替えるにはフロントエンドを再ビルドする必要がある。

## PSD 2D 立ち絵（デフォルト）

事前にレイヤー分割した透明背景 PNG を `public/assets/character/` 以下に配置し、CSS で重ねて表示する。

### ファイル配置

```
services/frontend/public/assets/character/
└── nurserobo/                    ← キャラクター名のディレクトリ
    ├── manifest.json             ← レイヤー定義マニフェスト (必須)
    ├── expr/                     ← 衣装 × 表情ベース
    │   ├── official_neutral.png
    │   ├── official_happy.png
    │   ├── official_surprised.png
    │   ├── official_sad.png
    │   ├── official_angry.png
    │   ├── official_worried.png
    │   ├── patient_neutral.png
    │   └── ...
    ├── eyes/                     ← 目パーツ
    │   ├── blink.png
    │   ├── closed.png
    │   ├── closed_smile.png
    │   ├── normal_half.png
    │   ├── jito_half.png
    │   ├── wink_r.png
    │   ├── wink_l.png
    │   ├── qq.png
    │   └── gt_lt.png
    ├── mouth/                    ← 口パーツ（リップシンク用）
    │   ├── close.png
    │   ├── smile.png
    │   ├── hmm.png
    │   ├── smile_open.png
    │   ├── a.png
    │   ├── i.png
    │   ├── i_smile.png
    │   ├── u.png
    │   ├── e.png
    │   ├── o.png
    │   ├── o_big.png
    │   ├── a_smile.png
    │   ├── ahaha.png
    │   ├── hawawa.png
    │   ├── tongue.png
    │   └── hmph.png
    ├── arms/                     ← 腕パーツ
    │   ├── left_default.png
    │   ├── left_down.png
    │   ├── left_syringe.png
    │   ├── left_point.png
    │   ├── left_hip.png
    │   ├── left_peace.png
    │   ├── left_open.png
    │   ├── right_default.png
    │   ├── right_hip.png
    │   ├── right_point.png
    │   ├── right_beckon.png
    │   ├── right_peace.png
    │   ├── right_open.png
    │   └── right_mouth.png
    ├── fx/                       ← エフェクト
    │   ├── tears.png
    │   ├── sweat.png
    │   ├── damage.png
    │   ├── damage2.png
    │   ├── blood.png
    │   ├── shadow.png
    │   ├── glow_orange.png
    │   └── glow_red.png
    ├── accessories/              ← アクセサリー
    │   ├── cat_ears.png
    │   ├── flower.png
    │   └── glasses.png
    └── symbols/                  ← 感情記号
        ├── exclamation.png
        ├── question.png
        └── surprise.png
```

ベースパスは `services/frontend/src/components/psd/psd-config.ts` の `BASE` 定数 (`/assets/character/nurserobo`) で固定されている。別キャラクターに差し替える場合はディレクトリ名と `BASE` 定数を合わせる必要がある。

### カスタマイズ

`services/frontend/src/components/psd/psd-config.ts` で以下を変更できる。

| 項目 | 定義箇所 | 例 |
|------|----------|-----|
| 表情 | `PsdExpression` / `ALL_EXPRESSIONS` | `neutral`, `happy`, `sad`, `surprised`, `angry`, `worried` |
| 口形状 | `PsdMouth` / `ALL_MOUTHS` | `close`, `a`, `i`, `u`, `e`, `o`, ... |
| 目 | `PsdEyes` / `ALL_EYES` | `blink`, `wink_r`, `qq`, ... |
| 左腕 | `PsdArmLeft` / `ALL_ARMS_LEFT` | `default`, `point`, `peace`, ... |
| 右腕 | `PsdArmRight` / `ALL_ARMS_RIGHT` | `default`, `beckon`, `mouth`, ... |
| 衣装 | `PsdCostume` / `ALL_COSTUMES` | `official`, `patient` |
| FX | `PsdFx` / `ALL_FX_KEYS` | `tears`, `sweat`, `glow_red`, ... |
| アクセサリー | `PsdAccessories` / `ALL_ACC_KEYS` | `cat_ears`, `flower`, `glasses` |
| 記号 | `PsdSymbol` / `ALL_SYMBOLS` | `exclamation`, `question`, `surprise` |

イベント → 状態の対応は `EVENT_STATE_MAP` で定義している。例:

```typescript
news_urgent: { delta: { expression: 'surprised', symbol: 'exclamation', fx: { glow_orange: true } }, ttl: 15_000 },
```

tone → 表情の対応は `TONE_EXPRESSION_MAP` で定義している。例:

```typescript
neutral:  'neutral',
caring:   'worried',
humorous: 'happy',
alert:    'surprised',
```

リップシンクは `VOWEL_MOUTH_MAP` で VRM 母音 (`aa`, `ih`, `ou`, `ee`, `oh`) を PSD 口形状にマッピングする。

### 開発用テストパネル

`VITE_AVATAR_TYPE=psd` かつ `pnpm dev` 実行時、画面右上に `PsdTestPanel` が表示される。

- tone (`caring` / `humorous` / `alert`) の切り替え
- タスク作成 / 緊急 / 完了イベント
- 環境アラート (`alert_co2`, `alert_heat`)
- バイオメトリクス (`biometric_hr`, `biometric_stress`, `biometric_fatigue`)
- ゲストモード (`voice_event`)
- 各種 VRMA モーションの発火

これらは TanStack Query キャッシュにモックデータを注入し、`usePsdEventDriven` のイベント経路を実際に通して動作確認する。本番ビルド (`import.meta.env.DEV === false`) では自動的に非表示になる。

## VRM 3D（オプション）

> 以下は `VITE_AVATAR_TYPE=vrm` でビルドした場合のみ適用される。

### 必要なもの

- VRM 形式のキャラクターモデル (`.vrm` ファイル)
- HEMS フロントエンドが起動済みであること

VRM モデルは [VRoid Hub](https://hub.vroid.com/)、[VRoid Studio](https://vroid.com/studio) 等から入手・作成できる。
キャラクター YAML (`CHARACTER` 変数) と VRM モデルは別管理 — どちらか片方だけでも動作する。

> **Note**: アバター関連のバイナリファイル (`.vrm`, `.vrma`) はリポジトリに含まれていない。
> 各ユーザーが本ガイドに従ってローカル環境に配置する。

### ファイル配置

```
services/frontend/public/models/
├── avatar.vrm                    ← VRM キャラクターモデル (必須)
└── motions/                      ← モーションファイル (任意)
    ├── walk.vrma                 ← 歩行モーション (任意、なければプロシージャル生成)
    ├── greeting_wave.vrma        ← Brain 発話連動モーション
    ├── nod_agree.vrma
    ├── ...
    └── (ユーザーが自由に追加可能)
```

すべてのファイルは `.gitignore` 済み。

### 1. VRM モデルの配置

```bash
cp your-character.vrm services/frontend/public/models/avatar.vrm
```

パスは `services/frontend/public/models/avatar.vrm` で固定。
ファイルがない場合はプレースホルダーアイコンが表示される。

#### VRM モデルの要件

- 形式: VRM 0.x または VRM 1.0
- **リップシンク**: BlendShape に口形素 (aa, ih, ou, ee, oh) が含まれていること
  - VRoid Studio 製モデルは標準で含まれる
- **表情**: `happy`, `surprised`, `relaxed` 等の Expression があると表情連動が有効になる
- **アイドルアニメーション**: Humanoid ボーンがあれば自動的にまばたき・呼吸・微動が再生される

### 2. モーションファイルの配置

`.vrma` (VRM Animation) 形式のファイルを `services/frontend/public/models/motions/` に配置する。

#### 歩行モーション（オーバーレイモード）

```bash
cp your-walk.vrma services/frontend/public/models/motions/walk.vrma
```

`walk.vrma` が存在すればオーバーレイモードの歩行時にループ再生される。
存在しなければプロシージャル歩行アニメーション（足振り・腕振り）にフォールバックする。

#### Brain 発話連動モーション

Brain が `speak` ツールで発話するたびに `MotionRetriever` がテキスト・tone からモーションを自動選択する。
フロントエンド側のレジストリとファイルが対応している必要がある。

**デフォルトのモーション ID 一覧:**

| ID | トリガー例 | category |
|----|-----------|----------|
| `greeting_wave` | 挨拶、帰宅、おはよう | greeting |
| `nod_agree` | タスク完了、了解 | reaction |
| `point_alert` | 温度異常、警告 | alert |
| `thinking_pose` | 提案、アドバイス | gesture |
| `celebrate` | 達成、お祝い | emote |
| `bow_polite` | お礼、謝罪 | greeting |
| `shrug_confused` | 不明、データ不足 | reaction |
| `stretch_suggest` | 長時間座位、休憩 | gesture |
| `wave_goodbye` | 外出、おやすみ | greeting |
| `surprise_react` | 急な変化、速報 | reaction |
| `look_around` | 周囲確認 | idle |
| `relax` | 平穏な環境 | idle |
| `sleepy` | 深夜、疲労 | idle |
| `show_full` | 自己紹介 | gesture |
| `spin` | テンションが高い | emote |
| `model_pose` | 余裕がある場面 | gesture |

一部またはすべてのファイルがなくても動作する — ファイルがないモーションはスキップされる。

### モーションの追加・カスタマイズ

VRM モードで新しいモーションを追加する場合、**以下 3 箇所**を更新する必要がある。

1. `.vrma` ファイルを `services/frontend/public/models/motions/` に配置
2. `config/motions.yaml` にエントリを追加

```yaml
motions:
  - id: my_motion          # 一意の ID
    file: my_motion.vrma   # motions/ ディレクトリ内のファイル名
    name: 説明的な名前
    description: どんな状況で使うか (日本語で詳しく書くほど選択精度が上がる)
    tags: [タグ1, タグ2, タグ3]
    duration: 2.0          # 秒
    category: gesture      # greeting / reaction / alert / gesture / emote / idle
```

3. `services/frontend/src/lib/motion-registry.ts` にも同じ ID でエントリを追加

```typescript
my_motion: { file: '/models/motions/my_motion.vrma', duration: 2.0, category: 'gesture' },
```

> **重要**: VRM モードでは `motion-registry.ts` と `config/motions.yaml` の両方を更新しないと、フロントエンドがファイルを解決できないか、Brain がモーションを選択できない。PSD モードではモーションファイルは VRM 用であり、`PsdTestPanel` や tone 連動で簡易的に発火される。

### モーション選択のチューニング

`description` と `tags` の記述が Brain の選択精度に直結する。日本語で具体的に書くこと。

```yaml
# 精度低い
description: アクション
tags: [動き]

# 精度高い
description: 外出時に手を振って見送る。おやすみ、いってらっしゃい、バイバイに使用。
tags: [見送り, バイバイ, おやすみ, いってらっしゃい, 外出, 別れ]
```

tone と category の対応:

| tone | 優先 category |
|------|--------------|
| `alert` | alert, reaction |
| `caring` | greeting, reaction, emote |
| `humorous` | emote, gesture |
| `neutral` | gesture, reaction |

### .vrma ファイルの入手方法

#### 方法 1: 既存のコレクションから取得

- **[tk256ailab/vrm-viewer](https://github.com/tk256ailab/vrm-viewer)** — `VRMA/` ディレクトリに 11 個。MIT ライセンス。
- **[VRoid 公式モーションパック](https://vroid.booth.pm/items/5512385)** — 7 個。無料。改変・商用利用可 (要クレジット)。再配布禁止。
- **[moeru-ai/airi](https://github.com/moeru-ai/airi)** — idle_loop.vrma。MIT ライセンス。

#### 方法 2: Mixamo から変換

1. [Mixamo](https://www.mixamo.com/) で FBX をダウンロード (「Without Skin」を選択)
2. [fbx2vrma-converter](https://github.com/tk256ailab/fbx2vrma-converter) (MIT) で変換:

```bash
git clone https://github.com/tk256ailab/fbx2vrma-converter
cd fbx2vrma-converter && npm install
node fbx2vrma-converter.js -i input.fbx -o output.vrma
```

#### 方法 3: BVH から変換

- **[vrm-c/bvh2vrma](https://vrm-c.github.io/bvh2vrma/)** — ブラウザ上で BVH → .vrma 変換 (MIT)
- BVH ソース: [CMU Motion Capture Database](http://mocap.cs.cmu.edu/) (パブリックドメイン)

#### 方法 4: Blender で自作

1. [VRM Add-on for Blender](https://extensions.blender.org/add-ons/vrm/) (MIT) をインストール
2. VRM モデルを読み込み、アニメーションを作成
3. File → Export → VRM Animation (.vrma)

## 表示モード

フロントエンドのヘッダーにあるアバターボタンをクリックするとモードが切り替わる。

| モード | 説明 | PSD | VRM |
|--------|------|-----|-----|
| `hidden` | 非表示 | ✅ | ✅ |
| `panel` | Dashboard 左カラムにパネル表示 | ✅ **(デフォルト)** | ✅ |
| `overlay` | 画面上にオーバーレイ表示。画面内を自律歩行する | ❌ 非対応 | ✅ **(VRM デフォルトは `hidden`)** |

設定は `localStorage` に保存され、再読み込みしても維持される。

PSD モードでは `overlay` は不要のため、サイクルは `hidden → panel → hidden` のみとなる。過去に VRM モードで `hidden` または `overlay` が保存されていても、PSD モードでは `panel` に正規化される。

### オーバーレイモードの動作（VRM のみ）

- **歩行**: 画面内をランダムに歩行 (3〜8 秒待機 → 目標地点へ移動を繰り返す)
- **向き**: 移動方向に応じて自然に体が回転
- **待機中モーション**: 8〜18 秒間隔でランダムにアイドルモーションを再生
- **モーション遷移**: クロスフェード (0.3〜0.5 秒) で滑らかに切り替わる

## 機能詳細

### リップシンク

音声再生中に音声波形を周波数解析して口の開閉を同期する。
espeak / VoiSona / VOICEVOX / Edge TTS / A.I.VOICE いずれのバックエンドでも動作する。
音声ファイルが存在しない場合は口パクなしで待機。

PSD モードでは `useLipSync.ts` の母音分析結果を `VOWEL_MOUTH_MAP` 経由で PSD 口形状に変換する。
VRM モードでは BlendShape の口形素 (`aa`, `ih`, `ou`, `ee`, `oh`) を直接駆動する。

### 表情連動

Brain の発話 tone に応じて表情が変化する。

PSD:

| tone | 表情 |
|------|------|
| `neutral` | `neutral` |
| `caring` | `worried` |
| `humorous` | `happy` |
| `alert` | `surprised` |

VRM:

| tone | Expression |
|------|-----------|
| `neutral` | relaxed (0.0) |
| `caring` | happy (0.4) |
| `humorous` | happy (0.7) |
| `alert` | surprised (0.5) |

### アイドルアニメーション（VRM のみ）

発話・モーション再生していない間、以下が自動再生される:

- まばたき (2〜6 秒間隔のランダム)
- 呼吸 (脊椎の微振動)
- 首の微動

### フォールバック

PSD / VRM いずれも、アセットが存在しない、または読み込みに失敗した場合はキャラクターアイコンのプレースホルダーを表示する。
その他の機能（発話、タスク管理など）はアバターの有無に関係なく正常動作する。

## トラブルシューティング

**アバターが表示されない**

PSD の場合:
- `services/frontend/public/assets/character/nurserobo/` に `manifest.json` と各 PNG が存在するか確認
- ブラウザの開発者ツールで 404 エラーが出ていないか確認
- ファイル名が `psd-config.ts` の `ALL_*` 配列と一致しているか確認

VRM の場合:
- `services/frontend/public/models/avatar.vrm` が存在するか確認
- ブラウザのコンソールで WebGL エラーが出ていないか確認
- VRM ファイルが破損していないか別のビューアで確認

**T ポーズのまま（VRM のみ）**
- 正常動作。レストポーズ（腕を下ろした状態）は自動適用される
- 解消しない場合は VRM のボーン構成を確認

**モーションが再生されない（VRM のみ）**
- `services/frontend/public/models/motions/` に `.vrma` ファイルがあるか確認
- `config/motions.yaml` の `file:` フィールドとファイル名が一致しているか確認
- `motion-registry.ts` にエントリがあるか確認
- Brain コンテナのログで `Motion retriever init failed` が出ていないか確認

**口パクしない**
- 音声ファイルが生成されているか確認 (`GET /audio/{filename}` で確認可)
- PSD: `public/assets/character/nurserobo/mouth/` に口形状 PNG が揃っているか確認
- VRM: VRM モデルに BlendShape（口形素）が含まれているか確認
  (VRoid Studio 製モデルは通常含まれている)

**歩行モーションが不自然（VRM のみ）**
- `services/frontend/public/models/motions/walk.vrma` に好みの歩行アニメーションを配置すると置き換わる
- Mixamo の "Walking" を fbx2vrma-converter で変換するのが手軽

**PSD のアセット差し替え後に表示が崩れる**
- 全レイヤーが同じ解像度・同じ `source_size` であることを確認
- `manifest.json` の `size` / `source_size` / `scale` が実際の PNG と一致しているか確認
- 表情ベースに口が含まれていないことを確認（口は `mouth/` レイヤーで重ねる）

## TTS プロバイダー対応状況

Brain の発話に使用できる TTS バックエンド:

- `espeak` — espeak-ng（常に利用可能）
- `voicevox` — VOICEVOX Docker
- `edge-tts` — Microsoft Edge TTS
- `voisona` — VoiSona Talk
- `aivoice` — A.I.VOICE Editor


