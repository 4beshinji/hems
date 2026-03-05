# Xiaomi Smart Band 10 セットアップガイド

Xiaomi Smart Band 10 を HEMS に接続し、心拍数・SpO2・睡眠・歩数・ストレス等のヘルスデータをリアルタイムで取得するための手順。

## 目次

- [概要](#概要)
- [必要なもの](#必要なもの)
- [Step 1: Smart Band 10 の初期設定](#step-1-smart-band-10-の初期設定)
- [Step 2: HEMS biometric-bridge の起動](#step-2-hems-biometric-bridge-の起動)
- [Step 3: データ取得パスの構成](#step-3-データ取得パスの構成)
  - [パス A: Health Connect コンパニオンアプリ (推奨)](#パス-a-health-connect-コンパニオンアプリ-推奨)
  - [パス B: Huami クラウド API (サーバーサイド)](#パス-b-huami-クラウド-api-サーバーサイド)
- [Step 4: 動作確認](#step-4-動作確認)
- [取得できるデータ一覧](#取得できるデータ一覧)
- [アーキテクチャ](#アーキテクチャ)
- [トラブルシューティング](#トラブルシューティング)
- [構成リファレンス](#構成リファレンス)

---

## 概要

HEMS はデュアルパスアーキテクチャでバンドデータを取得する:

| パス | 経路 | 遅延 | 必要なもの |
|------|------|------|-----------|
| **A: Health Connect** (推奨) | Band → Mi Fitness → Health Connect → コンパニオンアプリ → biometric-bridge | ~15分 | Android 14+ スマホ |
| **B: Huami API** (補助) | Band → Mi Fitness → Huami クラウド → biometric-bridge | ~15分 | huami-token (初回のみ) |

両パスを同時に有効化可能。重複データは自動的に除去される (5分ウィンドウ)。
片方だけでも運用できる。

## 必要なもの

- **Xiaomi Smart Band 10** (Standard Edition: 約6,280円 / Ceramic Edition: 約8,680円)
- **Android スマートフォン** (Android 14 以上推奨、Health Connect 対応)
- **Mi Fitness アプリ** (Google Play からインストール)
- **HEMS サーバー** (Docker Compose 稼働中)

## Step 1: Smart Band 10 の初期設定

### 1.1 Mi Fitness アプリのインストール

1. Google Play から **Mi Fitness** (Xiaomi公式) をインストール
2. Xiaomi アカウントでログイン (未作成なら新規作成)
3. アプリ内で **「デバイスを追加」** → **Xiaomi Smart Band 10** を選択
4. 画面の指示に従い Bluetooth ペアリングを完了

### 1.2 Health Connect の有効化

Mi Fitness が Health Connect にデータを書き込むよう設定する:

1. Mi Fitness アプリを開く
2. **プロフィール** → **サードパーティ連携** → **Health Connect**
3. 連携を有効化し、以下の項目を許可:
   - 心拍数 (Heart Rate)
   - 血中酸素濃度 (SpO2)
   - 睡眠 (Sleep)
   - 歩数 (Steps)
   - 消費カロリー (Calories)

> **注意**: Mi Fitness の Health Connect 連携は、アプリがバックグラウンドで動作中に
> 同期が途切れることがある。Android の設定でバッテリー最適化から Mi Fitness を除外すること。
>
> **設定** → **アプリ** → **Mi Fitness** → **バッテリー** → **制限なし**

### 1.3 測定の自動化設定

Mi Fitness アプリでバンドの自動測定を有効化:

1. Mi Fitness → **デバイス管理** → Smart Band 10
2. **ヘルスモニタリング**:
   - 心拍数の継続モニタリング: **オン** (1分間隔推奨)
   - 血中酸素の自動測定: **オン**
   - ストレスモニタリング: **オン**
   - 睡眠モニタリング: **オン** (睡眠呼吸品質含む)

## Step 2: HEMS biometric-bridge の起動

### 2.1 .env の設定

```bash
# .env に追記

# Webhook 認証シークレット (必須)
BIOMETRIC_WEBHOOK_SECRET=$(openssl rand -hex 32)

# Huami API を使う場合 (Step 3 パスB参照)
# HUAMI_ENABLED=true
# HUAMI_AUTH_TOKEN=...
# HUAMI_USER_ID=...
```

### 2.2 biometric プロファイルで起動

```bash
cd infra
docker compose --profile biometric up -d --build
```

### 2.3 疎通確認

```bash
curl http://localhost:8017/health
# → {"status":"ok","provider":"gadgetbridge","active_providers":["gadgetbridge"]}
```

## Step 3: データ取得パスの構成

### パス A: Health Connect コンパニオンアプリ (推奨)

Android スマホ上のコンパニオンアプリが Health Connect からデータを読み取り、
HEMS の biometric-bridge に定期送信する。

#### A.1 アプリのビルドとインストール

```bash
# Android Studio で開く
# File → Open → apps/healthconnect-companion/

# または CLI でビルド (Android SDK 必要)
cd apps/healthconnect-companion
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

#### A.2 アプリの設定

1. HEMS Health アプリを起動
2. **「Grant Health Connect Permissions」** をタップし、全項目を許可
3. 設定を入力:
   - **Bridge URL**: `http://<HEMSサーバーのIP>:8017`
   - **Webhook Secret**: `.env` の `BIOMETRIC_WEBHOOK_SECRET` の値
   - **Sync Interval**: `15` (分)
4. **「Save」** をタップ → バックグラウンド同期がスケジュールされる
5. **「Sync Now」** で即時テスト

#### A.3 動作フロー

```
Xiaomi Smart Band 10
    ↓ (Bluetooth)
Mi Fitness アプリ
    ↓ (自動同期)
Health Connect (Android OS)
    ↓ (15分ごとに読み取り)
HEMS Health コンパニオンアプリ
    ↓ (HTTPS POST + HMAC署名)
biometric-bridge webhook
    ↓ (MQTT publish)
HEMS Brain
```

---

### パス B: Huami クラウド API (サーバーサイド)

HEMS サーバーが Huami クラウド API を直接ポーリングしてデータを取得する。
スマホ不要 (Mi Fitness でバンドと同期済みであること)。

#### B.1 認証トークンの取得

Huami API にアクセスするには、認証トークンが必要。
`huami-token` ツールを使って取得する:

```bash
pip install huami-token

# Xiaomi アカウントで認証 (Mi Fitness で使用したアカウント)
huami-token --method xiaomi --email your@email.com

# ブラウザが開くので Xiaomi アカウントにログイン
# 成功すると以下が表示される:
#   Auth token: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#   User ID:    1234567890
```

> **トークンの有効期限**: 数ヶ月〜半年程度。
> 401 エラーが出たら再取得が必要。

#### B.2 .env に設定

```bash
# .env に追記
HUAMI_ENABLED=true
HUAMI_AUTH_TOKEN=ここに取得したAuth tokenを貼る
HUAMI_USER_ID=ここに取得したUser IDを貼る
HUAMI_SERVER_REGION=us
HUAMI_POLL_INTERVAL=900
```

**サーバーリージョン一覧**:

| リージョン | 値 | API サーバー |
|-----------|-----|-------------|
| 米国 (デフォルト) | `us` | api-mifit-us2.huami.com |
| 中国 | `cn` | api-mifit.huami.com |
| ヨーロッパ | `eu` | api-mifit-de.huami.com |
| シンガポール | `sg` | api-mifit-sg.huami.com |
| ロシア | `ru` | api-mifit-ru.huami.com |

Mi Fitness アカウント作成時の地域に合わせて設定する。
日本のアカウントは通常 `us` または `sg`。

#### B.3 biometric-bridge を再起動

```bash
cd infra
docker compose --profile biometric up -d --build
```

確認:

```bash
curl http://localhost:8017/health
# → {"status":"ok","provider":"gadgetbridge","active_providers":["gadgetbridge","huami"]}
# "huami" が active_providers に含まれていれば成功
```

#### B.4 動作フロー

```
Xiaomi Smart Band 10
    ↓ (Bluetooth)
Mi Fitness アプリ
    ↓ (クラウド同期)
Huami クラウドサーバー
    ↓ (15分ごとにポーリング)
biometric-bridge (HuamiProvider)
    ↓ (MQTT publish)
HEMS Brain
```

## Step 4: 動作確認

### ヘルスデータの確認

```bash
# 最新のバイオメトリクス
curl http://localhost:8017/api/biometric/latest
# → {"provider":"healthconnect","timestamp":1741186800.0,"heart_rate":72,"steps":4500,...}

# 睡眠サマリー
curl http://localhost:8017/api/biometric/sleep
# → {"duration_minutes":420,"deep_minutes":90,"rem_minutes":60,...}

# 活動サマリー
curl http://localhost:8017/api/biometric/activity
# → {"steps":8500,"calories":250,...}
```

### MQTT トピックの監視

```bash
# MQTT メッセージをリアルタイム監視
docker exec hems-mqtt mosquitto_sub -t 'hems/personal/biometrics/#' -v \
  -u hems-biometric -P <password>
```

正常に動作していれば、以下のようなメッセージが流れる:

```
hems/personal/biometrics/healthconnect/heart_rate {"bpm":72,"resting_bpm":62}
hems/personal/biometrics/healthconnect/steps {"count":8500,"daily_goal":10000}
hems/personal/biometrics/healthconnect/sleep {"duration_minutes":420,"deep_minutes":90,...}
hems/personal/biometrics/huami/heart_rate {"bpm":72,"resting_bpm":60}
```

## 取得できるデータ一覧

| データ | Health Connect (パスA) | Huami API (パスB) | MQTT トピック |
|--------|:---------------------:|:-----------------:|-------------|
| 心拍数 | o | o | `{provider}/heart_rate` |
| 安静時心拍数 | o | o | `{provider}/heart_rate` |
| SpO2 (血中酸素) | o | o* | `{provider}/spo2` |
| 歩数 | o | o | `{provider}/steps` |
| 消費カロリー | o | o | `{provider}/activity` |
| 睡眠 (総時間) | o | o | `{provider}/sleep` |
| 睡眠ステージ (深い/浅い/REM) | o | o | `{provider}/sleep` |
| HRV (心拍変動) | o | - | `{provider}/hrv` |
| ストレス | - | o* | `{provider}/stress` |
| 疲労スコア (算出) | - | - | `{provider}/fatigue` |

`o*` = デバイスとAPIバージョンによる。Smart Band 10 は対応。
疲労スコアは心拍数・睡眠・ストレスから biometric-bridge が算出する派生指標。

## アーキテクチャ

```
┌─────────────────────────────┐
│    Xiaomi Smart Band 10     │
│  HR / SpO2 / Sleep / Steps  │
└──────────┬──────────────────┘
           │ Bluetooth
           ▼
┌─────────────────────────────┐
│      Mi Fitness アプリ       │
│      (Android スマホ)        │
└──────┬──────────────┬───────┘
       │              │
       ▼              ▼
┌────────────┐  ┌──────────────┐
│  Health    │  │ Huami Cloud  │
│  Connect   │  │  Server      │
└──────┬─────┘  └──────┬───────┘
       │               │
       ▼               ▼
┌────────────┐  ┌──────────────┐
│ HEMS Health│  │ biometric-   │
│ Companion  │  │ bridge       │
│ App        │  │ HuamiProvider│
└──────┬─────┘  └──────┬───────┘
       │ HTTP POST     │ (内部)
       ▼               ▼
┌─────────────────────────────┐
│      biometric-bridge       │
│   [dedup] → MQTT publish    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         HEMS Brain          │
│   WorldModel / RuleEngine   │
└─────────────────────────────┘
```

**重複排除 (Dedup)**:
両パスが同じデータを配信した場合、5分以内に同一値の MQTT publish を抑制する。
例: Health Connect から HR=72 を受信後、Huami API からも HR=72 が来た場合、後者は破棄。

## トラブルシューティング

### Health Connect にデータが来ない

1. Mi Fitness アプリのバッテリー最適化を「制限なし」に設定
2. Mi Fitness → プロフィール → サードパーティ連携 → Health Connect が有効か確認
3. Health Connect アプリ → Mi Fitness → 共有データの項目がすべて許可されているか確認
4. Mi Fitness アプリを一度開いて手動同期を実行

### Huami API が 401 エラー

トークンの有効期限切れ。再取得する:

```bash
huami-token --method xiaomi --email your@email.com
# 取得したトークンを .env の HUAMI_AUTH_TOKEN に設定
cd infra && docker compose --profile biometric up -d --build
```

### Huami API にデータが無い

- Mi Fitness アプリでバンドと最新データを同期済みか確認
- `HUAMI_SERVER_REGION` が正しいか確認 (アカウント地域と一致)
- Huami API はクラウド同期後のデータを返すため、Mi Fitness アプリの同期完了を待つ

### コンパニオンアプリの同期が止まる

- Android のバッテリー最適化で HEMS Health アプリを「制限なし」に
- WorkManager は Android の電力管理下で動作するため、Doze モードでは遅延が発生しうる
- 最小同期間隔は 15分 (WorkManager の制約)

### biometric-bridge に接続できない

```bash
# bridge が起動しているか
docker ps | grep biometric
# ログの確認
docker logs -f hems-biometric-bridge
# ファイアウォール確認 (ポート 8017)
curl http://localhost:8017/health
```

## 構成リファレンス

### .env 変数一覧

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `BIOMETRIC_WEBHOOK_SECRET` | (なし) | Webhook HMAC 認証シークレット。未設定時は認証無効 |
| `BIOMETRIC_PROVIDER` | `gadgetbridge` | デフォルトプロバイダ名 |
| `HUAMI_ENABLED` | `false` | Huami クラウド API ポーリングの有効化 |
| `HUAMI_AUTH_TOKEN` | (なし) | Huami API 認証トークン |
| `HUAMI_USER_ID` | (なし) | Huami ユーザー ID |
| `HUAMI_SERVER_REGION` | `us` | API サーバーリージョン (us/cn/eu/sg/ru) |
| `HUAMI_POLL_INTERVAL` | `900` | ポーリング間隔 (秒) |
| `BIOMETRIC_DEDUP_WINDOW` | `300` | 重複排除ウィンドウ (秒) |

### MQTT トピック

すべて `hems/personal/biometrics/{provider}/` 配下:

| サブトピック | ペイロード例 |
|------------|------------|
| `heart_rate` | `{"bpm": 72, "resting_bpm": 62}` |
| `spo2` | `{"percent": 98}` |
| `steps` | `{"count": 8500, "daily_goal": 10000}` |
| `sleep` | `{"duration_minutes": 420, "deep_minutes": 90, "rem_minutes": 60, "light_minutes": 180}` |
| `stress` | `{"level": 45, "category": "normal"}` |
| `activity` | `{"calories": 250, "active_minutes": 45, "steps": 8500}` |
| `hrv` | `{"rmssd_ms": 42}` |
| `fatigue` | `{"score": 35, "factors": ["poor_sleep"]}` |
| `bridge/status` | `{"connected": true, "provider": "gadgetbridge", "active_providers": ["gadgetbridge", "huami"]}` |

### Webhook ペイロード形式

コンパニオンアプリが biometric-bridge に POST するデータ形式:

```json
POST /api/biometric/webhook
Content-Type: application/json
X-HEMS-Signature: sha256=<hmac_sha256_hex>

{
  "provider": "healthconnect",
  "timestamp": 1741186800.0,
  "heart_rate": 72,
  "resting_heart_rate": 62,
  "spo2": 98,
  "steps": 8500,
  "calories": 250,
  "hrv": 42,
  "sleep_duration": 420,
  "sleep_deep": 90,
  "sleep_rem": 60,
  "sleep_light": 180,
  "sleep_start_ts": 1741125000.0,
  "sleep_end_ts": 1741150200.0
}
```

### Brain ツール

biometric-bridge のデータは Brain の以下のツールからアクセスされる:

- **`get_biometrics`**: 最新のバイオメトリクス (HR, SpO2, Steps, Stress, 疲労スコア)
- **`get_sleep_summary`**: 直近の睡眠サマリー (総時間, ステージ別, 品質スコア)

### Brain ルール (自動トリガー)

| ルール | 条件 | アクション |
|--------|------|----------|
| 心拍数高 | HR > 120 | speak で警告 |
| 心拍数低 | HR < 45 | speak で警告 |
| SpO2 低 | SpO2 < 92 | speak で警告 |
| ストレス高 | Stress > 80 | speak で通知 + 休憩提案 |
| 疲労高 | Fatigue > 70 | speak で通知 |
| 睡眠品質低 | Quality < 40 | 朝に speak で報告 |
| 歩数目標 | Steps >= Goal | speak で達成通知 |
