# VRM アバター セットアップガイド

Dashboard に 3D キャラクターを表示し、Brain の発話に連動してジェスチャーや口パクを行うオプション機能。
アバターの有無は他の機能に一切影響しない — 設定しなくてもシステムは正常動作する。

## 必要なもの

- VRM 形式のキャラクターモデル (`.vrm` ファイル)
- HEMS フロントエンドが起動済みであること

VRM モデルは [VRoid Hub](https://hub.vroid.com/)、[VRoid Studio](https://vroid.com/studio) 等から入手・作成できる。
キャラクター YAML (`CHARACTER` 変数) と VRM モデルは別管理 — どちらか片方だけでも動作する。

> **Note**: アバター関連のバイナリファイル (`.vrm`, `.vrma`) はリポジトリに含まれていない。
> 各ユーザーが本ガイドに従ってローカル環境に配置する。

## ファイル配置

```
services/frontend/public/models/
├── avatar.vrm                    ← VRM キャラクターモデル (必須)
└── motions/                      ← モーションファイル (任意)
    ├── walk.vrma                 ← 歩行モーション (任意、なければプロシージャル生成)
    ��── greeting_wave.vrma        ← Brain 発話連動モーション
    ├── nod_agree.vrma
    ├── ...
    └── (ユーザーが自由に追加可能)
```

すべてのファイルは `.gitignore` 済み。

## 1. VRM モデルの配置

```bash
cp your-character.vrm services/frontend/public/models/avatar.vrm
```

パスは `services/frontend/public/models/avatar.vrm` で固定。
ファイルがない場合はプレースホルダーアイコンが表示される。

### VRM モデルの要件

- 形式: VRM 0.x または VRM 1.0
- **リップシンク**: BlendShape に口形素 (aa, ih, ou, ee, oh) が含まれていること
  - VRoid Studio 製モデルは標準で含まれる
- **表情**: `happy`, `surprised`, `relaxed` 等の Expression があると表情連動が有効になる
- **アイドルアニメーション**: Humanoid ボーンがあれば自動的にまばたき・呼吸・微動が再生される

## 2. モーションファイルの配置

`.vrma` (VRM Animation) 形式のファイルを `services/frontend/public/models/motions/` に配置する。

### 歩行モーション (オーバーレイモード)

```bash
cp your-walk.vrma services/frontend/public/models/motions/walk.vrma
```

`walk.vrma` が存在すればオーバーレイモードの歩行時にループ再生される。
存在しなければプロシージャル歩行アニメーション (足振り・腕振り) にフォールバックする。

### Brain 発話連動モーション

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
| `relax` | 平穏な環�� | idle |
| `sleepy` | 深夜、疲労 | idle |
| `show_full` | 自己紹介 | gesture |
| `spin` | テンションが高い | emote |
| `model_pose` | 余裕がある場面 | gesture |

一部またはすべてのファイルがなくても動作する — ファイルがないモーションはスキップされる。

### モーションの追加・カスタマイズ

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

### モーション選択のチューニング

`description` と `tags` の記述が Brain の選択精度に直結する。日本語で具体的に書くこと。

```yaml
# 精度低い
description: アクション
tags: [動き]

# 精度高い
description: 外出時に手を振って見送る。おやすみ、いってらっしゃい、バイバイに使用。
tags: [見送り, バイバイ, おやすみ, い��てらっしゃい, 外出, 別れ]
```

tone と category の対応:

| tone | 優先 category |
|------|--------------|
| `alert` | alert, reaction |
| `caring` | greeting, reaction, emote |
| `humorous` | emote, gesture |
| `neutral` | gesture, reaction |

## .vrma ファイルの入手方法

### 方法 1: 既存のコレクションから取得

- **[tk256ailab/vrm-viewer](https://github.com/tk256ailab/vrm-viewer)** — `VRMA/` ディレクトリに 11 個。MIT ライセンス。
- **[VRoid 公式モーションパック](https://vroid.booth.pm/items/5512385)** — 7 個。無料。改変・商用利用可 (要クレジット)。再配布禁止。
- **[moeru-ai/airi](https://github.com/moeru-ai/airi)** — idle_loop.vrma。MIT ライセンス。

### 方法 2: Mixamo から変換

1. [Mixamo](https://www.mixamo.com/) で FBX をダウンロード (「Without Skin」を選択)
2. [fbx2vrma-converter](https://github.com/tk256ailab/fbx2vrma-converter) (MIT) で変換:

```bash
git clone https://github.com/tk256ailab/fbx2vrma-converter
cd fbx2vrma-converter && npm install
node fbx2vrma-converter.js -i input.fbx -o output.vrma
```

### 方法 3: BVH から変換

- **[vrm-c/bvh2vrma](https://vrm-c.github.io/bvh2vrma/)** — ブラウザ上で BVH → .vrma 変換 (MIT)
- BVH ソース: [CMU Motion Capture Database](http://mocap.cs.cmu.edu/) (パブリックドメイン)

### 方法 4: Blender で自作

1. [VRM Add-on for Blender](https://extensions.blender.org/add-ons/vrm/) (MIT) をインストール
2. VRM モデルを読み込み、アニメーションを作成
3. File → Export → VRM Animation (.vrma)

## 表示モード

フロントエンドのヘッダーにあるアバターボタンをクリックするとモードが切り替わる。

| モード | 説明 |
|--------|------|
| `hidden` | 非表示 (デフォルト) |
| `panel` | Dashboard 左カラムにパネル表示 |
| `overlay` | 画面上にオーバーレイ表示。画面内を自律歩行する |

設定は `localStorage` に保存され、再読み込みしても維持される。

### オーバーレイモードの動作

- **歩行**: 画面内をランダムに歩行 (3〜8 秒待機 → 目標地点へ移動を繰り返す)
- **向き**: 移動方向に応じて自然に体が回転
- **待機中モーション**: 8〜18 秒間隔でランダムにアイドルモーションを再生
- **モーション遷移**: クロスフェード (0.3〜0.5 秒) で滑らかに切り替わる

## 機能詳細

### リップシンク

音声再生中に音声波形を周波数解析して口の開閉を同期する。
espeak / VoiSona / VOICEVOX / Edge TTS いずれのバックエンドでも動作する。
音声ファイルが存在しない場合は口パクなしで待機。

### 表情連動

Brain の発話 tone に応じて表情が変化する:
- `neutral` → relaxed (0.0)
- `caring` → happy (0.4)
- `humorous` → happy (0.7)
- `alert` → surprised (0.5)

### アイドルアニメーション

発話・モーション再生していない間、以下が自動再生される:
- まばたき (2〜6 秒間隔のランダム)
- 呼吸 (脊椎の微振動)
- 首の微動

### フォールバック

`avatar.vrm` が存在しない、または読み込みに失敗した場合はキャラクターアイコンのプレースホルダーを表示する。
その他の機能 (発話、タスク管理など) は VRM の有無に関係なく正常動作する。

## トラブルシューティング

**アバターが表示されない**
- `services/frontend/public/models/avatar.vrm` が存在するか確認
- ブラウザのコンソールで WebGL エラーが出ていないか確認
- VRM ファイルが破損していないか別のビューアで確認

**T ポーズのまま**
- 正常動作。レストポーズ (腕を下ろした状態) は自動適用される
- 解消しない場合は VRM のボーン構成を確認

**モーションが再生されない**
- `services/frontend/public/models/motions/` に `.vrma` ファイルがあるか確認
- `config/motions.yaml` の `file:` フィールドとファイル名が一致しているか確認
- `motion-registry.ts` にエントリがあるか確認
- Brain コンテナのログで `Motion retriever init failed` が出ていないか確認

**口パクしない**
- 音声ファイルが生成されているか確認 (`GET /audio/recent` で確認可)
- VRM モデルに BlendShape (口形素) が含まれているか確認
  (VRoid Studio 製モデルは通常含まれている)

**歩行モーションが不自然**
- `services/frontend/public/models/motions/walk.vrma` に好みの歩行アニメーションを配置すると置き換わる
- Mixamo の "Walking" を fbx2vrma-converter で変換するのが手軽
