# HEMS Lite — 軽量見守り衛星ノード

遠隔地の独居高齢者・子供の見守りに特化した、HEMS の軽量サテライト版。
Raspberry Pi 4 や Skylake Core i3 NUC 程度のハードウェアで動作する。

## 目次

- [コンセプト](#コンセプト)
- [クイックスタート](#クイックスタート)
- [アーキテクチャ](#アーキテクチャ)
- [サービス構成](#サービス構成)
- [3段階判定システム](#3段階判定システム)
- [ルール一覧](#ルール一覧)
- [グレーゾーン検出](#グレーゾーン検出)
- [LLMエスカレーション](#llmエスカレーション)
- [通知プロバイダ](#通知プロバイダ)
- [本体HEMS連携](#本体hems連携)
- [設定リファレンス](#設定リファレンス)
- [データベース](#データベース)
- [MQTTトピック](#mqttトピック)
- [リソース要件](#リソース要件)
- [テスト](#テスト)
- [トラブルシューティング](#トラブルシューティング)

---

## コンセプト

```
本体 HEMS (自宅)                    HEMS Lite (遠隔地)
┌─────────────────┐                ┌──────────────────────────┐
│ Ollama (LLM)    │                │ mosquitto (MQTT)         │
│ Brain (ReAct)   │◄── MQTT ──────│ sentinel (ルール + AI)   │
│ Backend (API)   │    bridge      │ notifier (通知)          │
│ Frontend (React)│                │ biometric-bridge (opt)   │
│ Voice (TTS)     │                │ perception (opt)         │
└─────────────────┘                └──────────────────────────┘
                                             │
                                   ┌─────────┴──────────┐
                                   │ LINE / Discord /    │
                                   │ Slack / ntfy        │
                                   │ (家族・介護者が確認) │
                                   └────────────────────┘
```

**本体HEMS との違い:**

| 項目 | HEMS (本体) | HEMS Lite |
|------|------------|-----------|
| LLM | Ollama/OpenAI (毎サイクル) | クラウドAPI (グレーゾーン時のみ) |
| 判定 | ReActループ (LLM駆動) | ルールエンジン + グレーゾーン検出 |
| UI | React SPA ダッシュボード | なし (メッセージアプリ通知) |
| DB | SQLite/PostgreSQL (full) | SQLite (アラート/履歴のみ) |
| TTS | 5バックエンド対応 | なし |
| RAM | 2-8GB+ | 170-520MB |
| 対象 | 単身者の自宅管理 | 遠隔見守り (高齢者/子供) |
| 動作 | 単独 | 単独 / 衛星 / ハイブリッド |

---

## クイックスタート

### 前提条件

- Docker & Docker Compose
- 通知先アカウント (LINE / Discord / Slack / ntfy のいずれか)
- (任意) LLM API キー (OpenAI or Anthropic)

### 1. 環境設定

```bash
git clone <repo> && cd hems
git checkout lite

cp env.lite.example .env
```

`.env` を編集して最低限以下を設定:

```bash
SITE_ID=grandma-house
SITE_NAME=おばあちゃんの家

# 通知先 (最低1つ)
LINE_NOTIFY_TOKEN=your-token
# または
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/xxx

# グレーゾーンAI判定 (任意)
LLM_PROVIDER=openai
LLM_API_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

### 2. 起動

```bash
# 最小構成 (sentinel + notifier + MQTT)
cd infra && docker compose -f docker-compose.lite.yml up -d --build

# バイオメトリクス (Gadgetbridge スマートバンド) 追加
docker compose -f docker-compose.lite.yml --profile biometric up -d --build

# カメラ人体検知追加
docker compose -f docker-compose.lite.yml --profile perception up -d --build

# Home Assistant 追加
docker compose -f docker-compose.lite.yml --profile ha up -d --build

# 全部入り
docker compose -f docker-compose.lite.yml \
  --profile biometric --profile perception --profile ha \
  up -d --build
```

### 3. 確認

```bash
# ログ確認
docker logs -f hems-lite-sentinel
docker logs -f hems-lite-notifier

# 通知テスト (notifier に直接リクエスト)
curl -X POST http://localhost:8019/api/notify \
  -H 'Content-Type: application/json' \
  -d '{"level":"HIGH","title":"テスト通知","body":"HEMS Liteからのテスト通知です。","source":"test"}'

# ヘルスチェック
curl http://localhost:8019/api/health
```

---

## アーキテクチャ

### データフロー

```
  センサー群                      MQTT                    Sentinel
  ─────────                    ────────                 ──────────
  スマートバンド ──webhook──► biometric-bridge ──pub──►│           │
  (Gadgetbridge)                                      │  State    │
                                                      │  Update   │
  IPカメラ ──capture──► perception ──pub──►            │     │     │
  (RTSP/HTTP)                                         │     ▼     │
                                                      │  Rule     │──► Notifier ──► LINE
  温湿度センサー ──pub──► mosquitto ──sub──►           │  Engine   │              Discord
  (ESP32/Zigbee)                                      │     │     │              Slack
                                                      │     ▼     │              ntfy
  Home Assistant ──ws──► ha-bridge ──pub──►            │  Gray     │
                                                      │  Zone     │
                                                      │  Detector │
                                                      │     │     │
                                                      │     ▼     │
                                                      │  LLM      │
                                                      │  Escalate │
                                                      │  (cloud)  │
                                                      └───────────┘
```

### 処理サイクル (60秒間隔)

```
[1] MQTT キュー排出 → OccupantState 更新
     ↓
[2] RuleEngine.evaluate(state)
     ├── CRITICAL/HIGH/NORMAL/INFO アラート → 通知送信
     └── 閾値超えなし → 次へ
     ↓
[3] GrayZoneDetector.evaluate(state)
     ├── グレーゾーン検出あり → LLMエスカレーション
     │    ├── NOTIFY → 通知送信
     │    ├── WATCH  → ログのみ
     │    └── IGNORE → ログのみ
     └── 検出なし → 何もしない
     ↓
[4] sleep(60秒)
```

---

## サービス構成

### 必須サービス (3つ)

| サービス | コンテナ名 | ポート | 役割 |
|---------|-----------|-------|------|
| mosquitto | hems-lite-mqtt | 1893 | MQTTブローカー |
| sentinel | hems-lite-sentinel | - | 見守りエンジン |
| notifier | hems-lite-notifier | 8019 | 通知ゲートウェイ |

### オプション (profile)

| サービス | Profile | コンテナ名 | ポート | 役割 |
|---------|---------|-----------|-------|------|
| biometric-bridge | `biometric` | hems-lite-biometric | 8017 | スマートバンド連携 |
| perception | `perception` | hems-lite-perception | 8018 | カメラ人体検知 |
| ha-bridge | `ha` | hems-lite-ha-bridge | 8016 | Home Assistant連携 |

---

## 3段階判定システム

Sentinel は 3 段階の判定パイプラインでアラートを処理する。

### 第1段階: ルールエンジン (ローカル、即時、コスト0)

明確な閾値超過を検出する確定的ルール。LLM不要。

- 入力: `OccupantState` (MQTT経由のリアルタイムデータ)
- 出力: `Alert` (level, rule_id, title, body, source)
- 処理時間: <1ms
- コスト: 0

### 第2段階: グレーゾーン検出 (ローカル、即時、コスト0)

個々は正常範囲だが、組み合わせやパターンとして懸念される状況を検出。

- 入力: `OccupantState` + 24時間の履歴データ
- 出力: `GrayZoneEvent` (pattern, signals, confidence)
- 処理時間: <10ms
- コスト: 0

### 第3段階: LLMエスカレーション (クラウドAPI、判断のみ)

グレーゾーンイベントをクラウドLLMに送信し、通知すべきか判断を委ねる。

- 入力: `GrayZoneEvent` + 現在の状態サマリー
- 出力: `EscalationResult` (NOTIFY / WATCH / IGNORE)
- 処理時間: 1-5秒 (API待ち)
- コスト: ~$0.01/回 (gpt-4o-mini), ~$0.003/回 (claude-haiku-4-5)
- 予算制限: 日次上限 (デフォルト50回/日)

**Graceful degradation**: LLM APIキー未設定、予算枯渇、API障害時は第1段階のルールのみで動作する。グレーゾーンはログに記録されるが通知されない。

---

## ルール一覧

### CRITICAL (即時通知、クールダウンなし)

| ID | 条件 | 通知タイトル | ソース |
|----|------|------------|--------|
| C1 | SpO2 < 88% | 血中酸素が危険レベル | biometric |
| C2 | HR < 40bpm | 心拍数が危険に低下 | biometric |
| C3 | HR > 150bpm | 心拍数が危険に上昇 | biometric |
| C4 | 臥位 + 活動量急落 (直前に活動あり) | 転倒の可能性 | activity |
| C5 | 人不検知 > 120分 | 長時間不検知 | activity |

**C4 転倒検知の仕組み:**
1. 現在姿勢が `lying` (臥位)
2. 活動レベルが 0.05 未満
3. 臥位開始から 120秒以内 (最近倒れた)
4. 直近の活動履歴に 0.3 以上の活動があった (動いていたのに突然倒れた)

### HIGH (5分クールダウン)

| ID | 条件 | 通知タイトル | ソース |
|----|------|------------|--------|
| H1 | 88% <= SpO2 < 92% | 血中酸素が低下 | biometric |
| H2 | 120 < HR <= 150bpm | 心拍数上昇 | biometric |
| H3 | 40 <= HR < 45bpm | 心拍数低め | biometric |
| H4 | 室温 > 32度 or < 10度 | 室温危険 | environment |
| H5 | 深夜 (02:00-05:00) に歩行検知 | 深夜の活動検知 | activity |
| H6 | 日中 (6-21h) 臥位 > 3時間 | 長時間臥位 | activity |
| H7 | 体温 > 37.5度 | 体温上昇 | biometric |
| H8 | 呼吸数 > 25回/分 | 呼吸数上昇 | biometric |
| env_co2_crit | CO2 > 1500ppm | CO2危険 | environment |

### NORMAL (30分クールダウン)

| ID | 条件 | 通知タイトル | ソース |
|----|------|------------|--------|
| N1 | 座位 > 90分 | 長時間座位 | activity |
| N2 | ストレス > 80 | ストレス高め | biometric |
| N_fatigue | 疲労 > 70 | 疲労蓄積 | biometric |
| N_hrv | HRV < 20ms | HRV低下 | biometric |
| env_co2_high | CO2 > 1000ppm | CO2上昇 | environment |
| env_humidity | 湿度 > 70% or < 30% | 湿度異常 | environment |
| env_temp_warn | 28 < 室温 <= 32 or 10 <= 室温 < 16 | 室温注意 | environment |

### INFO (日次サマリーにのみ含む)

| ID | 条件 | 内容 |
|----|------|------|
| I1 | 睡眠 < 5h or > 11h | 睡眠時間異常 |
| I2 | 20時以降、歩数 < 1000 | 活動量少なめ |
| I3 | 睡眠品質 < 40/100 | 睡眠品質低下 |

### クールダウン機構

各ルールにはクールダウンが設定されており、同一アラートが短期間に繰り返し通知されることを防ぐ。

| レベル | クールダウン | 理由 |
|-------|------------|------|
| CRITICAL | 0秒 | 即時、何度でも通知 |
| HIGH | 300秒 (5分) | 状況確認の猶予 |
| NORMAL | 1800秒 (30分) | 環境の自然回復を待つ |
| INFO | 86400秒 (24時間) | 日次サマリーのみ |
| GRAY_ZONE | 600秒 (10分) | 同一パターンの連続エスカレーション防止 |

---

## グレーゾーン検出

GrayZoneDetector は 5 種類のパターンを検出する。

### 1. compound_anomaly (複合軽度異常)

個々の値は閾値以下だが、複数の指標が同時に閾値の 70% 以上にある場合。

**検出ロジック:**
- 各バイタル指標を `値 / 閾値` で比率計算
- 比率が `GRAY_ZONE_FACTOR` (0.7) 以上の指標を「ウォーム」とカウント
- ウォームシグナルが `GRAY_ZONE_MIN_SIGNALS` (2) 以上で発火

**例:** HR=100bpm (閾値120の83%), stress=65 (閾値80の81%), fatigue=55 (閾値70の79%)
→ 3つのウォームシグナル → `compound_anomaly` 発火

**対象指標:**
- 心拍数 (HR_HIGH=120との比)
- ストレス (STRESS_HIGH=80との比)
- 疲労 (FATIGUE_HIGH=70との比)
- SpO2 (SPO2_LOW=92付近の±3%)
- HRV (HRV_LOW=20の1.5倍以下)
- 座位時間 (SEDENTARY_ALERT_MINUTES * 0.7 以上)

### 2. trend (緩やかな悪化傾向)

24時間の履歴を前半1/3と後半1/3に分割し、有意な変化を検出。

| 指標 | 発火条件 |
|------|---------|
| 心拍数 | 後半平均が前半平均の 115% 以上 |
| SpO2 | 後半平均が前半平均 - 2%pt 以下 |
| ストレス | 後半平均が前半平均の 130% 以上 |

最低 6 データポイントが必要 (少量データでは発火しない)。

### 3. contradiction (矛盾シグナル)

センサー間の整合性が取れない状況。

| パターン | 条件 |
|---------|------|
| 日中臥位 + 高HR | 6-22時に `lying` + HR > 90bpm |
| 高活動 + 低HR | activity_level > 0.5 + HR < 55bpm |
| 在室 + バイタル途絶 | person_count > 0 + HR データ 30分以上古い |

### 4. sensor_gap (データ欠落)

接続済みセンサーからのデータが途絶した場合。

| センサー | 発火条件 |
|---------|---------|
| biometric-bridge | HR データが 30分以上更新なし |
| perception | activity データが 10分以上更新なし |

### 5. behavior_deviation (行動パターン逸脱)

学習した日常パターンからの逸脱。

| パターン | 条件 | 必要データ |
|---------|------|----------|
| 起床時刻逸脱 | 通常起床時刻 + 90分を超えても臥位 | 3日以上の起床データ |
| HR基準値逸脱 | 安静時HRが基準値 ± 25% 以上 | 20回以上の安静時HR |

**基準値学習:**
- 起床時刻: 5-12時に `standing/walking` + `sleep.stage=awake` を記録 (14日ローリング)
- 安静時HR: `sitting/lying` + `activity_level < 0.2` + HR 50-100bpm の EMA (alpha=0.05)

---

## LLMエスカレーション

### プロバイダ設定

**OpenAI (推奨: gpt-4o-mini):**
```bash
LLM_PROVIDER=openai
LLM_API_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

**Anthropic (推奨: claude-haiku-4-5):**
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
LLM_MODEL=claude-haiku-4-5-20251001
```

### コスト見積もり

| モデル | 1回あたり | 50回/日 | 30日 |
|-------|----------|---------|------|
| gpt-4o-mini | ~$0.01 | ~$0.50 | ~$15 |
| claude-haiku-4-5 | ~$0.003 | ~$0.15 | ~$4.5 |

### 予算制御

| パラメータ | デフォルト | 説明 |
|-----------|----------|------|
| `LLM_DAILY_BUDGET` | 50 | 日次API呼び出し上限 (0時リセット) |
| `LLM_ESCALATION_COOLDOWN` | 600秒 | 同一パターンの再エスカレーション間隔 |

予算枯渇時:
- グレーゾーンはログに記録される (`level=GRAY`)
- LLMは呼ばれず、通知はされない
- ルールベースの閾値アラート (第1段階) は影響なし

### LLMプロンプト

システムプロンプトでLLMに以下を指示:
- 高齢者/脆弱者の安全を優先
- 時刻・活動コンテキストを考慮
- 医学的診断は行わず「確認してください」と提案
- JSON形式で `verdict` / `level` / `reason` / `message` を返す

LLMに送信されるコンテキスト (最小):
```
Time: 2026-03-05 14:32 (Wednesday)

Gray zone detected: compound_anomaly
Description: 複数の指標が閾値付近: HR=105bpm (閾値の88%), stress=68 (閾値の85%)
Signals: ["HR=105bpm (閾値の88%)", "stress=68 (閾値の85%)"]
Confidence: 86%

Current state:
Biometrics: HR=105bpm, SpO2=96%, stress=68, fatigue=50
Activity: posture=sitting, level=0.15, persons=1, posture_held=45min, steps=2100
Zone[living_room]: temp=24.5C, humidity=55%

Should the caregiver be notified?
```

LLMの応答例:
```json
{
  "verdict": "WATCH",
  "level": "NORMAL",
  "reason": "心拍数とストレスが高めですが、座位45分でまだ範囲内。次回チェックで継続なら通知。",
  "message": ""
}
```

---

## 通知プロバイダ

### 対応プラットフォーム

| プロバイダ | 環境変数 | 取得方法 |
|-----------|---------|---------|
| LINE Notify | `LINE_NOTIFY_TOKEN` | https://notify-bot.line.me/ で発行 |
| Discord | `DISCORD_WEBHOOK_URL` | チャンネル設定 → 連携サービス → ウェブフック |
| Slack | `SLACK_WEBHOOK_URL` | Slack App → Incoming Webhooks |
| ntfy | `NTFY_TOPIC` + `NTFY_SERVER` | https://ntfy.sh/ (セルフホスト可) |

複数プロバイダを同時設定可能。設定されたすべてのプロバイダに並行送信される。

### 通知レベルフィルタ

`NOTIFY_MIN_LEVEL` で即時通知の最低レベルを設定:

| 設定値 | 即時通知されるレベル | 用途 |
|-------|-------------------|------|
| `CRITICAL` | CRITICAL のみ | 最重要のみ (通知最小) |
| `HIGH` (デフォルト) | CRITICAL + HIGH | 推奨 |
| `NORMAL` | CRITICAL + HIGH + NORMAL | 詳細通知 |
| `INFO` | すべて | デバッグ用 |

### 通知フォーマット例

**LINE Notify:**
```
[CRITICAL] 心拍数が危険に上昇
---
心拍数が160bpmです（閾値: 150bpm）。
Zone: living_room
Site: おばあちゃんの家
```

**Discord (embed):**
- 色付きサイドバー (赤=CRITICAL, 橙=HIGH, 青=NORMAL, 緑=INFO)
- タイトル、説明、Zone/Source フィールド

**Slack (blocks):**
- ヘッダーブロック + セクションブロック + コンテキスト

**ntfy:**
- Priority 5 (CRITICAL) / 4 (HIGH) / 3 (NORMAL) / 2 (INFO)
- タグ付き (rotating_light, warning, etc)

### 日次サマリー

`DAILY_SUMMARY_ENABLED=true` + `DAILY_SUMMARY_TIME=08:00` で毎朝8時に送信。

```
[おばあちゃんの家] 日次レポート (03/05)

HR: 72bpm
SpO2: 97%
Sleep: 7.2h (quality: 78/100)
Steps: 3241
living_room: 22.3C / 48%

Alerts (24h): HIGH: 1
  14:32 [HIGH] 心拍数上昇
LLM budget remaining: 48
```

---

## 本体HEMS連携

### 動作モード

| モード | `HEMS_LITE_MODE` | 動作 |
|-------|-----------------|------|
| スタンドアロン | `standalone` | LINE/Discord等に通知のみ。本体HEMSとの接続なし |
| 衛星 | `satellite` | 全データをMQTT bridgeで本体HEMSに転送 + 通知 |
| ハイブリッド | `hybrid` | 通常はスタンドアロン。CRITICALは本体にもエスカレーション |

### 衛星モード設定

1. `infra/mosquitto/bridge.conf.example` を `bridge.conf` にコピー
2. 本体HEMSの MQTT ホスト/認証情報を設定
3. `mosquitto-lite.conf` に `include_dir /mosquitto/config/bridge.conf` を追加

```conf
# bridge.conf
connection hems-main
address main-hems.example.com:1893
remote_username hems-lite-bridge
remote_password YOUR_PASSWORD

# ローカルトピックを hems-lite/{SITE_ID}/ プレフィックス付きで転送
topic hems/personal/biometrics/# out 1 "" hems-lite/grandma-house/
topic office/# out 1 "" hems-lite/grandma-house/
```

本体HEMS側では `hems-lite/+/#` を subscribe してWorldModelに統合可能。

---

## 設定リファレンス

### 全環境変数一覧

#### サイト設定

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `SITE_ID` | `hems-lite` | サイト識別子 (MQTT, 通知に使用) |
| `SITE_NAME` | `HEMS Lite` | 表示名 (通知に使用) |
| `HEMS_LITE_MODE` | `standalone` | 動作モード: standalone / satellite / hybrid |
| `TZ` | `Asia/Tokyo` | タイムゾーン |

#### MQTT

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `MQTT_HOST` | `mosquitto` | MQTTブローカーホスト |
| `MQTT_PORT` | `1883` | MQTTポート |
| `MQTT_USER` | (空) | MQTT認証ユーザー |
| `MQTT_PASS` | (空) | MQTTパスワード |
| `HEMS_PORT_MQTT` | `1893` | ホスト公開ポート |

#### Sentinel (見守りエンジン)

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `SENTINEL_CYCLE_INTERVAL` | `60` | 評価サイクル間隔 (秒) |
| `NOTIFY_MIN_LEVEL` | `HIGH` | 即時通知の最低レベル |
| `DAILY_SUMMARY_ENABLED` | `true` | 日次サマリー送信 |
| `DAILY_SUMMARY_TIME` | `08:00` | サマリー送信時刻 |
| `SENTINEL_DB_PATH` | `/data/sentinel.db` | SQLiteパス |
| `LOG_LEVEL` | `INFO` | ログレベル |

#### LLMエスカレーション

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `LLM_PROVIDER` | `openai` | LLMプロバイダ: openai / anthropic |
| `LLM_API_URL` | (空) | OpenAI互換エンドポイント |
| `LLM_API_KEY` | (空) | OpenAI APIキー |
| `LLM_MODEL` | `gpt-4o-mini` | モデル名 |
| `ANTHROPIC_API_KEY` | (空) | Anthropic APIキー |
| `LLM_DAILY_BUDGET` | `50` | 日次API呼び出し上限 |
| `LLM_ESCALATION_COOLDOWN` | `600` | 同一パターンの再エスカレーション間隔 (秒) |

#### バイタル閾値

| 変数 | デフォルト | レベル | 説明 |
|------|----------|-------|------|
| `HR_CRITICAL_HIGH` | `150` | CRITICAL | 心拍数上限 (危険) |
| `HR_CRITICAL_LOW` | `40` | CRITICAL | 心拍数下限 (危険) |
| `SPO2_CRITICAL` | `88` | CRITICAL | SpO2下限 (危険) |
| `HR_HIGH` | `120` | HIGH | 心拍数上限 |
| `HR_LOW` | `45` | HIGH | 心拍数下限 |
| `SPO2_LOW` | `92` | HIGH | SpO2下限 |
| `STRESS_HIGH` | `80` | NORMAL | ストレス上限 |
| `BODY_TEMP_HIGH` | `37.5` | HIGH | 体温上限 |
| `RESPIRATORY_RATE_HIGH` | `25` | HIGH | 呼吸数上限 |
| `HRV_LOW` | `20` | NORMAL | HRV下限 (ms) |
| `FATIGUE_HIGH` | `70` | NORMAL | 疲労スコア上限 |

#### 環境閾値

| 変数 | デフォルト | レベル | 説明 |
|------|----------|-------|------|
| `TEMP_HIGH` | `32` | HIGH | 室温上限 (危険) |
| `TEMP_LOW` | `10` | HIGH | 室温下限 (危険) |
| `TEMP_WARN_HIGH` | `28` | NORMAL | 室温上限 (注意) |
| `TEMP_WARN_LOW` | `16` | NORMAL | 室温下限 (注意) |
| `HUMIDITY_HIGH` | `70` | NORMAL | 湿度上限 (%) |
| `HUMIDITY_LOW` | `30` | NORMAL | 湿度下限 (%) |
| `CO2_HIGH` | `1000` | NORMAL | CO2上限 (ppm) |
| `CO2_CRITICAL` | `1500` | HIGH | CO2上限 (危険) |

#### 活動監視

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `SEDENTARY_ALERT_MINUTES` | `90` | 座位アラート (分) |
| `ABSENCE_ALERT_MINUTES` | `120` | 不在検知アラート (分) |
| `NIGHT_ACTIVITY_START` | `02:00` | 深夜活動検知開始 |
| `NIGHT_ACTIVITY_END` | `05:00` | 深夜活動検知終了 |
| `LYING_DAYTIME_MINUTES` | `180` | 日中臥位アラート (分) |

#### グレーゾーン

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `GRAY_ZONE_FACTOR` | `0.7` | 閾値に対する「ウォーム」判定倍率 |
| `GRAY_ZONE_MIN_SIGNALS` | `2` | compound_anomaly の最小シグナル数 |
| `TREND_WINDOW_HOURS` | `24` | 傾向分析のウィンドウ (時間) |
| `PATTERN_DEVIATION_MINUTES` | `90` | 行動パターン逸脱の閾値 (分) |

#### 通知プロバイダ

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `LINE_NOTIFY_TOKEN` | (空) | LINE Notify トークン |
| `DISCORD_WEBHOOK_URL` | (空) | Discord Webhook URL |
| `SLACK_WEBHOOK_URL` | (空) | Slack Incoming Webhook URL |
| `NTFY_TOPIC` | (空) | ntfy トピック名 |
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy サーバーURL |

---

## データベース

Sentinel は SQLite に以下の 3 テーブルを保持する。

### alerts テーブル

```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,       -- Unix timestamp
    level TEXT NOT NULL,            -- CRITICAL/HIGH/NORMAL/INFO/GRAY
    rule_id TEXT NOT NULL,          -- C1, H2, N1, gray_compound_anomaly, etc.
    title TEXT NOT NULL,            -- 通知タイトル
    body TEXT NOT NULL,             -- 通知本文
    source TEXT NOT NULL,           -- biometric/activity/environment/gray_zone/gray_zone_llm
    zone TEXT DEFAULT '',           -- ゾーンID
    data_json TEXT DEFAULT '{}',    -- 付帯データ (JSON)
    notified INTEGER DEFAULT 0,    -- 通知送信済み (0/1)
    escalated INTEGER DEFAULT 0,   -- LLMエスカレーション済み (0/1)
    llm_verdict TEXT DEFAULT '',   -- NOTIFY/WATCH/IGNORE
    llm_reason TEXT DEFAULT ''     -- LLMの判定理由
);
```

### daily_summary テーブル

```sql
CREATE TABLE daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,      -- YYYY-MM-DD
    summary_json TEXT NOT NULL,     -- サマリー全文 (JSON)
    sent INTEGER DEFAULT 0         -- 送信済み (0/1)
);
```

### metrics_history テーブル

```sql
CREATE TABLE metrics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    metric TEXT NOT NULL,           -- bio_heart_rate, env_living_room_temperature, etc.
    value REAL NOT NULL,
    zone TEXT DEFAULT ''
);
```

データ保持期間: デフォルト 90 日 (`SentinelDB.prune_old_data()` で設定可能)。

---

## MQTTトピック

Sentinel が subscribe するトピック:

| パターン | 用途 |
|---------|------|
| `hems/personal/biometrics/#` | バイタルデータ (HR, SpO2, stress, etc.) |
| `office/+/camera/+/status` | カメラ検知 (人数, 姿勢) |
| `office/+/activity/+` | 活動レベル |
| `office/+/sensor/#` | 環境センサー (温湿度, CO2, etc.) |
| `hems/+/bridge/status` | ブリッジ接続状態 |
| `hems/perception/bridge/status` | Perception接続状態 |
| `hems/home/#` | Home Assistant デバイス状態 |

### メッセージ形式例

```json
// hems/personal/biometrics/gadgetbridge/heart_rate
{"bpm": 72, "timestamp": 1709625600}

// hems/personal/biometrics/gadgetbridge/sleep
{"stage": "deep", "duration_hours": 7.2, "quality_score": 78}

// office/living_room/camera/cam01/status
{"person_count": 1, "posture": "sitting", "activity_level": 0.15, "posture_duration_sec": 2700}

// office/living_room/sensor/esp32_01/temperature
{"value": 24.5}
```

---

## リソース要件

### 最小構成 (Raspberry Pi 4, 2GB)

| サービス | RAM | CPU |
|---------|-----|-----|
| mosquitto | ~20MB | <1% |
| sentinel | ~80MB | 1-2% |
| notifier | ~40MB | <1% |
| **合計** | **~140MB** | **~3%** |

### バイオメトリクス付き (Raspberry Pi 4, 2GB)

| サービス | RAM | CPU |
|---------|-----|-----|
| mosquitto | ~20MB | <1% |
| sentinel | ~80MB | 1-2% |
| notifier | ~40MB | <1% |
| biometric-bridge | ~50MB | <1% |
| **合計** | **~190MB** | **~3%** |

### 全部入り (NUC Core i3, 4GB+)

| サービス | RAM | CPU |
|---------|-----|-----|
| mosquitto | ~20MB | <1% |
| sentinel | ~80MB | 1-2% |
| notifier | ~40MB | <1% |
| biometric-bridge | ~50MB | <1% |
| perception (nano) | ~300MB | 10-15% |
| ha-bridge | ~80MB | 1-2% |
| **合計** | **~570MB** | **~15%** |

### LLMコスト

| 設定 | 概算月額 |
|------|---------|
| LLM無し (ルールのみ) | $0 |
| gpt-4o-mini, 50回/日 | ~$15/月 |
| claude-haiku-4-5, 50回/日 | ~$4.5/月 |
| gpt-4o-mini, 20回/日 | ~$6/月 |

---

## テスト

```bash
# 仮想環境作成
uv venv .venv && source .venv/bin/activate
uv pip install pytest aiosqlite httpx loguru paho-mqtt aiohttp

# 全テスト実行
python -m pytest tests/lite/ -v

# 個別テスト
python -m pytest tests/lite/test_rules.py -v        # ルールエンジン
python -m pytest tests/lite/test_gray_zone.py -v     # グレーゾーン検出
python -m pytest tests/lite/test_escalation.py -v    # LLMエスカレーション
```

テスト内容 (38件):
- ルールエンジン: 各レベル (CRITICAL/HIGH/NORMAL/INFO) の発火/非発火確認
- グレーゾーン: 複合異常、傾向、矛盾、センサーギャップ、クールダウン
- エスカレーション: JSON解析 (正常/異常/Markdown), 予算管理, API未設定

---

## トラブルシューティング

### 通知が来ない

1. `docker logs hems-lite-notifier` でプロバイダエラーを確認
2. `curl http://localhost:8019/api/health` でアクティブプロバイダを確認
3. テスト通知を送信:
   ```bash
   curl -X POST http://localhost:8019/api/notify \
     -H 'Content-Type: application/json' \
     -d '{"level":"HIGH","title":"テスト","body":"テスト通知"}'
   ```
4. `NOTIFY_MIN_LEVEL` が `HIGH` 以下であることを確認

### グレーゾーンが検出されない

- LLM APIキーが設定されていなくてもグレーゾーン「検出」は動作する (エスカレーションのみスキップ)
- `docker logs hems-lite-sentinel` で `Gray zone logged` / `Gray zone NOTIFY` を確認
- `LOG_LEVEL=DEBUG` で詳細ログを有効化

### MQTT接続失敗

- `docker logs hems-lite-mqtt` でブローカーログを確認
- 認証が有効な場合 `MQTT_USER` / `MQTT_PASS` を確認
- ポート競合: `HEMS_PORT_MQTT` を変更

### Perception が遅い (RPi)

- `HEMS_PERCEPTION_INTERVAL` を 30-60秒に設定
- nano モデル (`yolo11n-pose.pt`) がデフォルトで使用されることを確認
- `HEMS_PERCEPTION_CONFIDENCE` を 0.3-0.4 に下げてみる

### LLM予算が早く枯渇する

- `LLM_DAILY_BUDGET` を増やす (コスト注意)
- `LLM_ESCALATION_COOLDOWN` を 1200 (20分) に増やす
- `GRAY_ZONE_MIN_SIGNALS` を 3 に増やして compound_anomaly の感度を下げる
- `GRAY_ZONE_FACTOR` を 0.8 に増やして「ウォーム」判定を厳しくする

---

## ファイル構成

```
services/sentinel/
├── Dockerfile
├── requirements.txt
└── src/
    ├── main.py           # エントリーポイント、MQTT購読、メインループ
    ├── config.py          # 全環境変数、閾値定義
    ├── state.py           # OccupantState (バイタル/活動/環境/履歴)
    ├── rules.py           # RuleEngine (閾値判定 → Alert)
    ├── gray_zone.py       # GrayZoneDetector (5パターン → GrayZoneEvent)
    ├── escalation.py      # Escalator (LLM API → EscalationResult)
    └── db.py              # SentinelDB (SQLite永続化)

services/notifier/
├── Dockerfile
├── requirements.txt
└── src/
    ├── main.py            # FastAPI サーバー (POST /api/notify)
    └── providers/
        ├── base.py        # NotifyProvider ABC
        ├── line.py        # LINE Notify
        ├── discord.py     # Discord Webhook
        ├── slack.py       # Slack Incoming Webhook
        └── ntfy.py        # ntfy.sh

infra/
├── docker-compose.lite.yml     # Lite専用 Docker Compose
└── mosquitto/
    ├── mosquitto-lite.conf     # Lite用 MQTT設定
    └── bridge.conf.example     # 本体HEMS連携テンプレート

env.lite.example                # 環境変数テンプレート

tests/lite/
├── test_rules.py               # ルールエンジンテスト (20件)
├── test_gray_zone.py           # グレーゾーンテスト (8件)
└── test_escalation.py          # エスカレーションテスト (10件)
```
