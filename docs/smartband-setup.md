# スマートバンド セットアップガイド

スマートバンド / スマートウォッチを HEMS に接続し、心拍数・SpO2・睡眠・歩数・ストレス等のヘルスデータをリアルタイムで取得するための手順。

HEMS へのデータ送信には、**HEMS Health Connect コンパニオンアプリ（推奨）** または **Gadgetbridge** を使用する。

## 対応デバイス

| デバイス | コンパニオンアプリ | Health Connect | クラウド API | 備考 |
|---------|-------------------|:--------------:|:----------:|------|
| Xiaomi Smart Band 8/9/10 | Mi Fitness | o | o (Huami) | デュアルパス対応 |
| Amazfit (各モデル) | Mi Fitness / Zepp | o | o (Huami) | デュアルパス対応 |
| **CMF Watch Pro 2** | **CMF Watch** | **o** | - | Health Connect パスのみ |

すべてのデバイスは **Health Connect** 経由 (パスA) で HEMS に接続可能。
Xiaomi / Amazfit デバイスは追加で **Huami クラウド API** (パスB) も利用可能。

## 目次

- [対応デバイス](#対応デバイス)
- [概要](#概要)
- [デバイス別セットアップ](#デバイス別セットアップ)
  - [Xiaomi Smart Band 10](#xiaomi-smart-band-10)
  - [CMF Watch Pro 2](#cmf-watch-pro-2)
- [HEMS biometric-bridge の起動](#hems-biometric-bridge-の起動)
- [データ取得パスの構成](#データ取得パスの構成)
  - [パス A: Health Connect コンパニオンアプリ (推奨)](#パス-a-health-connect-コンパニオンアプリ-推奨)
  - [パス B: Huami クラウド API (Xiaomi/Amazfit のみ)](#パス-b-huami-クラウド-api-xiaomiamazfit-のみ)
- [動作確認](#動作確認)
- [取得できるデータ一覧](#取得できるデータ一覧)
- [アーキテクチャ](#アーキテクチャ)
- [トラブルシューティング](#トラブルシューティング)
- [構成リファレンス](#構成リファレンス)

---

## 概要

HEMS はデュアルパスアーキテクチャでバンドデータを取得する:

| パス | 経路 | 遅延 | 必要なもの | 対応デバイス |
|------|------|------|-----------|-------------|
| **A: Health Connect** (推奨) | Band → コンパニオンアプリ → Health Connect → HEMS コンパニオン → biometric-bridge | ~15分 | Android 14+ スマホ (必須) | 全デバイス |
| **B: Huami API** (補助) | Band → Mi Fitness → Huami クラウド → biometric-bridge | ~15分 | huami-token (初回のみ) | Xiaomi / Amazfit のみ |

両パスを同時に有効化可能。重複データは自動的に除去される (5分ウィンドウ)。
片方だけでも運用できる。

---

## デバイス別セットアップ

### Xiaomi Smart Band 10

#### 必要なもの

- **Xiaomi Smart Band 10** (Standard Edition: 約6,280円 / Ceramic Edition: 約8,680円)
- **Android スマートフォン** (Android 14 以上必須、Health Connect 対応)
- **Mi Fitness アプリ** (Google Play からインストール)
- **HEMS Health Connect コンパニオンアプリ** または **Gadgetbridge**
- **HEMS サーバー** (Docker Compose 稼働中)

#### 1. Mi Fitness アプリのインストール

1. Google Play から **Mi Fitness** (Xiaomi公式) をインストール
2. Xiaomi アカウントでログイン (未作成なら新規作成)
3. アプリ内で **「デバイスを追加」** → **Xiaomi Smart Band 10** を選択
4. 画面の指示に従い Bluetooth ペアリングを完了

#### 2. Health Connect の有効化

Mi Fitness が Health Connect にデータを書き込むよう設定する:

1. Mi Fitness アプリを開く
2. **プロフィール** → **サードパーティ連携** → **Health Connect**
3. 連携を有効化し、以下の項目を許可:
   - 心拍数 (Heart Rate)
   - 安静時心拍数 (Resting Heart Rate)
   - 心拍変動 (Heart Rate Variability / HRV)
   - 血中酸素濃度 (SpO2)
   - 睡眠 (Sleep)
   - 歩数 (Steps)
   - 消費カロリー (Calories)

> **注意**: Mi Fitness の Health Connect 連携は、アプリがバックグラウンドで動作中に
> 同期が途切れることがある。Android の設定でバッテリー最適化から Mi Fitness を除外すること。
>
> **設定** → **アプリ** → **Mi Fitness** → **バッテリー** → **制限なし**

#### 3. 測定の自動化設定

Mi Fitness アプリでバンドの自動測定を有効化:

1. Mi Fitness → **デバイス管理** → Smart Band 10
2. **ヘルスモニタリング**:
   - 心拍数の継続モニタリング: **オン** (1分間隔推奨)
   - 血中酸素の自動測定: **オン**
   - ストレスモニタリング: **オン**
   - 睡眠モニタリング: **オン** (睡眠呼吸品質含む)

---

### CMF Watch Pro 2

#### 必要なもの

- **CMF Watch Pro 2** (Nothing サブブランド、約8,800円)
- **Android スマートフォン** (Android 14 以上必須、Health Connect 対応)
- **CMF Watch アプリ** (Google Play からインストール)
- **HEMS Health Connect コンパニオンアプリ** または **Gadgetbridge**
- **HEMS サーバー** (Docker Compose 稼働中)

#### 1. CMF Watch アプリのインストール

1. Google Play から **CMF Watch** (Nothing公式) をインストール
2. Nothing アカウントでログイン (未作成なら新規作成)
3. アプリ内で **「デバイスを追加」** → **CMF Watch Pro 2** を選択
4. 画面の指示に従い Bluetooth ペアリングを完了

#### 2. Health Connect の有効化

CMF Watch アプリが Health Connect にデータを書き込むよう設定する:

1. CMF Watch アプリを開く
2. **プロフィール** → **Health Connect** (または **サードパーティ連携**)
3. 連携を有効化し、以下の項目を許可:
   - 心拍数 (Heart Rate)
   - 安静時心拍数 (Resting Heart Rate)
   - 心拍変動 (Heart Rate Variability / HRV)
   - 血中酸素濃度 (SpO2)
   - 睡眠 (Sleep)
   - 歩数 (Steps)
   - 消費カロリー (Calories)

> **注意**: CMF Watch アプリもバックグラウンド同期が途切れることがある。
> Android の設定でバッテリー最適化から除外すること。
>
> **設定** → **アプリ** → **CMF Watch** → **バッテリー** → **制限なし**

#### 3. 測定の自動化設定

CMF Watch アプリでウォッチの自動測定を有効化:

1. CMF Watch → **デバイス管理** → CMF Watch Pro 2
2. **ヘルスモニタリング**:
   - 心拍数の継続モニタリング: **オン**
   - 血中酸素の自動測定: **オン**
   - ストレスモニタリング: **オン**
   - 睡眠モニタリング: **オン**

#### 4. データ取得パス

CMF Watch Pro 2 は **Health Connect パス (パスA) のみ** 対応。
Huami クラウド API (パスB) は使用不可。

```
CMF Watch Pro 2
    ↓ (Bluetooth)
CMF Watch アプリ
    ↓ (自動同期)
Health Connect (Android OS)
    ↓ (15分ごとに読み取り)
HEMS Health Connect コンパニオンアプリ
    ↓ (HTTPS POST + HMAC署名)
biometric-bridge webhook
    ↓ (MQTT publish)
HEMS Brain
```

> **CMF Watch Pro 2 の特徴**: GPS 内蔵、1.32" AMOLED、BLE 5.3、IP68防水。
> Xiaomi Smart Band に比べディスプレイが大きく、スマートウォッチ型の操作感。

## HEMS biometric-bridge の起動

### .env の設定

```bash
# .env に追記

# Webhook 認証シークレット (必須)
BIOMETRIC_WEBHOOK_SECRET=$(openssl rand -hex 32)

# 内部サービス間通信用トークン (任意)。
# 設定すると /api/biometric/* の GET 系に Authorization: Bearer <token> が必要になる。
# 未設定時は認証なし (dev mode)。
# HEMS_INTERNAL_TOKEN=$(openssl rand -hex 32)

# Webhook replay 攻撃防止を厳格化。
# 現行 HEMS Health Connect コンパニオンアプリは legacy HMAC 署名のみ対応のため、
#  true にするとリクエストが拒否される。false (デフォルト) のまま運用すること。
# WEBHOOK_REPLAY_STRICT=false

# Huami API を使う場合 (Step 3 パスB参照)
# HUAMI_ENABLED=true
# HUAMI_AUTH_TOKEN=...
# HUAMI_USER_ID=...
```

### biometric プロファイルで起動

```bash
cd infra
docker compose --profile biometric up -d --build
```

### 疎通確認

```bash
curl http://localhost:8017/health
# → {"status":"ok","provider":"gadgetbridge","active_providers":["gadgetbridge"],"mqtt_connected":true,"queue_pending":0}
```

## データ取得パスの構成

### パス A: Health Connect コンパニオンアプリ (推奨)

Android スマホ上の HEMS Health Connect コンパニオンアプリが Health Connect からデータを読み取り、
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

> **要件**: `minSdk = 34` なので、**Android 14 以上が必須**。

#### A.2 アプリの設定

1. HEMS Health Connect コンパニオンアプリを起動
2. **「Grant Health Connect Permissions」** をタップし、全項目を許可
   （心拍数、安静時心拍数、HRV、SpO2、睡眠、歩数、消費カロリー等）
3. 設定を入力:
   - **Bridge URL**: `http://<HEMSサーバーのIP>:8017`
     （末尾の `/api/biometric/webhook` はアプリが自動付加するので、ベース URL のみ入力）
   - **Webhook Secret**: `.env` の `BIOMETRIC_WEBHOOK_SECRET` の値
   - **Sync Interval**: `15` (分)
4. **「Save」** をタップ → バックグラウンド同期がスケジュールされる
5. **「Sync Now」** で即時テスト

#### A.3 動作フロー

```
スマートバンド / スマートウォッチ
    ↓ (Bluetooth)
コンパニオンアプリ (Mi Fitness / CMF Watch 等)
    ↓ (自動同期)
Health Connect (Android OS)
    ↓ (15分ごとに読み取り)
HEMS Health Connect コンパニオンアプリ
    ↓ (HTTPS POST + HMAC署名)
biometric-bridge webhook
    ↓ (MQTT publish)
HEMS Brain
```

---

### パス B: Huami クラウド API (Xiaomi/Amazfit のみ)

HEMS サーバーが Huami クラウド API を直接ポーリングしてデータを取得する。
スマホ不要 (Mi Fitness でバンドと同期済みであること)。

> **注意**: このパスは Xiaomi / Amazfit デバイスのみ対応。CMF Watch Pro 2 等は Health Connect パス (パスA) を使用すること。

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
# → {"status":"ok","provider":"gadgetbridge","active_providers":["gadgetbridge","huami"],"mqtt_connected":true,"queue_pending":0}
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

## 動作確認

### ヘルスデータの確認

`/api/biometric/*` の GET 系は `private_router` に属する。
`.env` で `HEMS_INTERNAL_TOKEN` を設定している場合、`Authorization: Bearer <token>` ヘッダーが必要。
未設定時は認証不要 (dev mode)。

```bash
# 最新のバイオメトリクス
curl -H "Authorization: Bearer ${HEMS_INTERNAL_TOKEN}" \
  http://localhost:8017/api/biometric/latest
# → {"provider":"healthconnect","timestamp":1741186800.0,"heart_rate":72,"steps":4500,...}

# 睡眠サマリー
curl -H "Authorization: Bearer ${HEMS_INTERNAL_TOKEN}" \
  http://localhost:8017/api/biometric/sleep
# → {"duration_minutes":420,"deep_minutes":90,"rem_minutes":60,...}

# 活動サマリー
curl -H "Authorization: Bearer ${HEMS_INTERNAL_TOKEN}" \
  http://localhost:8017/api/biometric/activity
# → {"steps":8500,"calories":250,...}
```

### MQTT トピックの監視

メトリクスは `hems/personal/biometrics/{provider}/` 配下に publish される。
bridge 状態は **canonical** として `hems/biometric/bridge/status`、
legacy 互換として `hems/personal/biometrics/bridge/status` も brain は併読する。

```bash
# メトリクスをリアルタイム監視
docker exec hems-mqtt mosquitto_sub -t 'hems/personal/biometrics/#' -v \
  -u hems-biometric -P <password>

# bridge 状態 (canonical)
docker exec hems-mqtt mosquitto_sub -t 'hems/biometric/bridge/status' -v \
  -u hems-biometric -P <password>
```

正常に動作していれば、以下のようなメッセージが流れる:

```
hems/personal/biometrics/healthconnect/heart_rate {"bpm":72,"resting_bpm":62}
hems/personal/biometrics/healthconnect/steps {"count":8500,"daily_goal":10000}
hems/personal/biometrics/healthconnect/sleep {"duration_minutes":420,"deep_minutes":90,...}
hems/personal/biometrics/healthconnect/hrv {"rmssd_ms":42}
hems/personal/biometrics/huami/heart_rate {"bpm":72,"resting_bpm":60}
hems/biometric/bridge/status {"connected":true,"provider":"healthconnect","active_providers":["healthconnect"]}
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

**CMF Watch Pro 2**: Health Connect (パスA) 経由で心拍数・SpO2・歩数・睡眠・カロリーを取得可能。
ストレスは CMF Watch アプリ内で確認可能だが、Health Connect への書き込みはアプリバージョンによる。

## アーキテクチャ

```
┌─────────────────────────────┐
│  スマートバンド / ウォッチ    │
│  HR / SpO2 / Sleep / Steps  │
└──────────┬──────────────────┘
           │ Bluetooth
           ▼
┌─────────────────────────────┐
│  コンパニオンアプリ           │
│  (Mi Fitness / CMF Watch)   │
│  (Android スマホ)            │
└──────┬──────────────┬───────┘
       │              │ (Xiaomi/Amazfit のみ)
       ▼              ▼
┌────────────┐  ┌──────────────┐
│  Health    │  │ Huami Cloud  │
│  Connect   │  │  Server      │
└──────┬─────┘  └──────┬───────┘
       │               │
       ▼               ▼
┌────────────┐  ┌──────────────┐
│ HEMS Health│  │ biometric-   │
│ Connect    │  │ bridge       │
│ Companion  │  │ HuamiProvider│
│ App        │  │              │
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

### CMF Watch のデータが Health Connect に来ない

1. CMF Watch アプリのバッテリー最適化を「制限なし」に設定
2. CMF Watch アプリの Health Connect 連携が有効か確認
3. Health Connect アプリ → CMF Watch → 共有データの項目がすべて許可されているか確認
4. CMF Watch アプリを一度開いてウォッチと手動同期を実行
5. CMF Watch アプリを最新バージョンにアップデート (古いバージョンは Health Connect 非対応の場合あり)

### コンパニオンアプリの同期が止まる

- Android のバッテリー最適化で HEMS Health Connect コンパニオンアプリを「制限なし」に
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

### `/api/biometric/*` が 401 になる

`HEMS_INTERNAL_TOKEN` を設定している場合、リクエストに `Authorization: Bearer <token>` を付ける:

```bash
curl -H "Authorization: Bearer ${HEMS_INTERNAL_TOKEN}" \
  http://localhost:8017/api/biometric/latest
```

未設定時は認証不要 (dev mode)。トークン値は `.env` の `HEMS_INTERNAL_TOKEN` と一致させる。

### Webhook が 401 になる

- `BIOMETRIC_WEBHOOK_SECRET` がアプリ設定と `.env` で一致しているか確認
- 現行 HEMS Health Connect コンパニオンアプリは **legacy HMAC 署名** のみ対応のため、
  `WEBHOOK_REPLAY_STRICT=true` にするとリクエストが拒否される。`false` (デフォルト) で運用すること

## 構成リファレンス

### .env 変数一覧

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `BIOMETRIC_WEBHOOK_SECRET` | (なし) | Webhook HMAC 認証シークレット。未設定時は認証無効 |
| `HEMS_INTERNAL_TOKEN` | (なし) | 内部サービス間 Bearer トークン。設定時は `/api/biometric/*` GET 系に `Authorization: Bearer` が必要 |
| `BIOMETRIC_PROVIDER` | `gadgetbridge` | デフォルトプロバイダ名。Health Connect コンパニオンアプリから送信される `provider` フィールドで上書きされる |
| `HUAMI_ENABLED` | `false` | Huami クラウド API ポーリングの有効化 |
| `HUAMI_AUTH_TOKEN` | (なし) | Huami API 認証トークン |
| `HUAMI_USER_ID` | (なし) | Huami ユーザー ID |
| `HUAMI_SERVER_REGION` | `us` | API サーバーリージョン (us/cn/eu/sg/ru) |
| `HUAMI_POLL_INTERVAL` | `900` | ポーリング間隔 (秒) |
| `BIOMETRIC_DEDUP_WINDOW` | `300` | 重複排除ウィンドウ (秒) |
| `WEBHOOK_REPLAY_STRICT` | `false` | `true` の場合、 webhook は `X-Timestamp` + `X-Nonce` ヘッダーを必須にする。現行コンパニオンアプリは未対応なので `false` を維持 |

### MQTT トピック

生体メトリクスは `hems/personal/biometrics/{provider}/` 配下に publish される。
bridge 状態は **canonical** で `hems/biometric/bridge/status`、
legacy 互換として `hems/personal/biometrics/bridge/status` も brain が併読する。

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
| `bridge/status` (canonical) | `{"connected": true, "provider": "healthconnect", "active_providers": ["healthconnect"]}` |
| `bridge/status` (legacy) | `hems/personal/biometrics/bridge/status` も互換 window で受信 |

### Webhook ペイロード形式

コンパニオンアプリが biometric-bridge に POST するデータ形式。
エンドポイントは `/api/biometric/webhook`。

#### 新プロトコル (replay 防止対応アプリ)

```json
POST /api/biometric/webhook
Content-Type: application/json
X-HEMS-Signature: sha256=<hmac_sha256_hex>
X-Timestamp: 1741186800
X-Nonce: <unique_opaque_string>

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

#### Legacy プロトコル (現行 HEMS Health Connect コンパニオンアプリ / Gadgetbridge)

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

> **注意**: `WEBHOOK_REPLAY_STRICT=true` にすると、legacy プロトコル (X-Timestamp/X-Nonce なし) は
> **401 で拒否**される。現行 HEMS Health Connect コンパニオンアプリは legacy 署名のみ対応のため、
> デフォルトの `false` のまま運用すること。

### Brain ツール

biometric-bridge のデータは Brain の以下のツールからアクセスされる:

- **`get_biometrics`**: 最新のバイオメトリクス (HR, SpO2, Steps, Stress, 疲労スコア)
- **`get_sleep_summary`**: 直近の睡眠サマリー (総時間, ステージ別, 品質スコア)
- **`get_biometric_trend`**: 生体メトリックの履歴 (時系列) と傾向 (min/max/avg 等)
- **`get_sleep_history`**: 直近 N 日分の睡眠品質スコア / 睡眠時間履歴

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
