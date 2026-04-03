# VRM アバター セットアップガイド

Dashboard に 3D キャラクターを表示し、Brain の発話に連動してジェスチャーや口パクを行う機能。

## 必要なもの

- VRM 形式のキャラクターモデル (`.vrm` ファイル)
- HEMS フロントエンドが起動済みであること

VRM モデルは [VRoid Hub](https://hub.vroid.com/) 等から入手できる。  
キャラクター YAML (`CHARACTER` 変数) と VRM モデルは別管理 — どちらか片方だけでも動作する。

## セットアップ

### 1. VRM ファイルを配置する

```bash
# Docker 環境の場合 (infra/ で起動)
cp your-character.vrm services/frontend/public/models/avatar.vrm

# フロントエンド開発サーバーの場合
cp your-character.vrm services/frontend/public/models/avatar.vrm
```

ファイルパスは `services/frontend/public/models/avatar.vrm` で固定。  
VRM ファイルがない場合は自動的にプレースホルダー表示になる。

### 2. アバターを表示する

フロントエンドのヘッダーにあるアバターボタンをクリックするとモードが切り替わる。

| モード | 説明 |
|--------|------|
| `hidden` | 非表示 (デフォルト) |
| `panel` | Dashboard 左カラムにパネル表示 |
| `overlay` | 画面右下にオーバーレイ表示 |

設定は `localStorage` に保存され、ページを再読み込みしても維持される。

## モーション設定

### 現在のモーション一覧

`config/motions.yaml` に 10 種類のジェスチャーが定義されている。

| ID | 名前 | トリガー条件 |
|----|------|-------------|
| `greeting_wave` | 手を振る挨拶 | 挨拶、帰宅、おはよう |
| `nod_agree` | うなずき | タスク完了、了解報告 |
| `point_alert` | 注意喚起の指さし | 温度・CO2 異常、警告 |
| `thinking_pose` | 考え中 | 提案、アドバイス |
| `celebrate` | お祝い | タスク完了祝い、達成 |
| `bow_polite` | お辞儀 | お礼、謝罪、丁寧な挨拶 |
| `shrug_confused` | 肩をすくめる | 不明、データ不足 |
| `stretch_suggest` | ストレッチ促し | 長時間座位、休憩提案 |
| `wave_goodbye` | 見送り | 外出、おやすみ |
| `surprise_react` | 驚き | 急なデータ変化、速報 |

### モーションの追加

1. `.vrma` ファイルを `services/frontend/public/models/motions/` に配置
2. `config/motions.yaml` にエントリを追加

```yaml
motions:
  - id: my_motion          # 一意のID
    file: my_motion.vrma   # motions/ ディレクトリ内のファイル名
    name: 説明的な名前
    description: どんな状況で使うか（日本語で詳しく書くほど精度が上がる）
    tags: [タグ1, タグ2, タグ3]
    duration: 2.0          # 秒
    category: gesture      # greeting / reaction / alert / gesture / emote / idle
```

Brain が `speak` ツールを呼ぶたびに `MotionRetriever` が発話テキストと tone から  
BM25 + トーン親和性 + 使用頻度減衰 + 新規性ボーナスのスコアリングで自動選択する。

### モーション選択のチューニング

`description` と `tags` の記述が選択精度に直結する。日本語で具体的に書くこと。

```yaml
# 精度低い
description: アクション
tags: [動き]

# 精度高い
description: 外出時に手を振って見送る。おやすみ、いってらっしゃい、バイバイに使用。
tags: [見送り, バイバイ, おやすみ, いってらっしゃい, 外出, 別れ]
```

トーンと category の対応:

| tone | 優先 category |
|------|--------------|
| `alert` | alert, reaction |
| `caring` | greeting, reaction, emote |
| `humorous` | emote, gesture |
| `neutral` | gesture, reaction |

## 機能詳細

### リップシンク

音声再生中に音声波形を解析して口の開閉を同期する。  
espeak / VoiSona / VOICEVOX / Edge TTS いずれのバックエンドでも動作する。  
音声ファイルが存在しない場合は口パクなしで待機。

### アイドルアニメーション

発話していない間、以下のアニメーションが自動再生される:
- ランダムな小さな体の揺れ
- 視線の放浪 (視点が自然に移動)

### フォールバック

`services/frontend/public/models/avatar.vrm` が存在しない場合、  
または VRM の読み込みに失敗した場合は、キャラクターアイコンのプレースホルダーを表示する。  
その他の機能 (発話、タスク管理など) は VRM の有無に関係なく正常動作する。

## トラブルシューティング

**アバターが表示されない**
- `services/frontend/public/models/avatar.vrm` が存在するか確認
- ブラウザのコンソールで WebGL エラーが出ていないか確認
- VRM ファイルが破損していないか別のビューアで確認

**モーションが再生されない**
- `services/frontend/public/models/motions/` に `.vrma` ファイルがあるか確認
- `config/motions.yaml` の `file:` フィールドとファイル名が一致しているか確認
- Brain コンテナのログで `Motion retriever init failed` が出ていないか確認

**口パクしない**
- 音声ファイルが生成されているか確認 (`GET /audio/recent` で確認可)
- VRM モデルに BlendShape (口形素) が含まれているか確認
  (VRoid Studio 製モデルは通常含まれている)
