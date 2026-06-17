# イベント自動化 設定ガイド

特定のライフイベント (起床・帰宅・外出など) を検出して、警報通知・ニュース読み上げ・天気報告・朝の挨拶を  
自動的に実行する機能。`EVENT_AUTOMATIONS` 環境変数で設定する。

## デフォルト動作

設定なしの場合、起床検知 → 気象警報通知 + 朝の挨拶 + ニュース読み上げ + 天気報告 が実行される:

```json
[{"event": "wake_up", "actions": ["weather_alert_announce", "morning_greeting", "news_briefing", "weather_report"]}]
```

## イベント一覧

| イベント | 検出条件 |
|---------|---------|
| `wake_up` | バイオメトリクスの睡眠終了 または 朝のカメラ在室検知 |
| `arrival` | HA Bridge の在室センサーが「不在→在室」に変化 |
| `departure` | HA Bridge の在室センサーが「在室→不在」に変化 |
| `scheduled` | 指定時刻 (`time` フィールドで設定) |

`wake_up` / `arrival` / `departure` は 1日1回のクールダウンがある (同じ日に重複実行されない)。  
`scheduled` は毎日指定時刻に1回実行される。

## アクション一覧

| アクション | 内容 |
|-----------|------|
| `weather_alert_announce` | 気象警報・注意報が発表されている場合に内容を発話 |
| `morning_greeting` | LLM がセンサーデータ・天気・睡眠情報を参照して自然な挨拶文を生成・発話 |
| `news_briefing` | news-bridge から最新のニュースサマリーを取得して発話 (`--profile news` 必須) |
| `weather_report` | ワールドモデルの天気情報を発話 (weather-bridge データを使用) |
| `task_planning` | LLM が本日のタスク予定を整理して発話 |
| `speak_custom` | 指定した固定文を発話 (`text` フィールドで設定) |
| `scene:*` | 指定したシーンを実行 (例: `scene:morning`) |

## 設定方法

`.env` の `EVENT_AUTOMATIONS` を JSON 配列で設定する:

```bash
# .env
EVENT_AUTOMATIONS='[
  {"event": "wake_up", "actions": ["morning_greeting", "weather_report"]},
  {"event": "arrival", "actions": ["morning_greeting"]},
  {"event": "departure", "actions": []},
  {"event": "scheduled", "time": "12:00", "actions": ["news_briefing"]},
  {"event": "scheduled", "time": "20:00", "actions": ["weather_report"]}
]'
```

### 設定例

**朝だけニュース、昼は天気、帰宅時に挨拶:**

```bash
EVENT_AUTOMATIONS='[
  {"event": "wake_up", "actions": ["weather_alert_announce", "morning_greeting", "news_briefing", "weather_report"]},
  {"event": "arrival", "actions": ["morning_greeting"]},
  {"event": "scheduled", "time": "12:00", "actions": ["weather_report"]}
]'
```

**ニュース不使用 (news-bridge なし):**

```bash
EVENT_AUTOMATIONS='[
  {"event": "wake_up", "actions": ["weather_alert_announce", "morning_greeting", "weather_report"]},
  {"event": "arrival", "actions": ["morning_greeting"]}
]'
```

**自動化を完全に無効化:**

```bash
EVENT_AUTOMATIONS='[]'
```

**時刻指定の定期ブリーフィングのみ:**

```bash
EVENT_AUTOMATIONS='[
  {"event": "scheduled", "time": "07:30", "actions": ["weather_alert_announce", "morning_greeting", "news_briefing", "weather_report"]},
  {"event": "scheduled", "time": "19:00", "actions": ["news_briefing"]}
]'
```

## 必要なプロファイル

| アクション | 必要なプロファイル |
|-----------|------------------|
| `weather_alert_announce` | なし (weather-bridge データが推奨) |
| `morning_greeting` | なし (LLM は常時利用) |
| `news_briefing` | `--profile news --profile ollama` |
| `weather_report` | なし (weather-bridge データが推奨、なくても動作) |
| `task_planning` | なし (LLM は常時利用) |
| `speak_custom` | なし |
| `scene:*` | なし (Backend のシーン機能を使用) |

```bash
# news_briefing を使う場合
docker compose --profile news --profile ollama up -d --build
```

## 各アクションの詳細

### weather_alert_announce

現在発表されている気象警報・注意報を検出し、内容を発話する。  
警報がない場合は何も発話しない。

### morning_greeting

LLM が以下の情報をもとに自然な挨拶文を生成して発話する:

- 現在の時刻
- 現在の室温・湿度・CO2 (センサーがある場合)
- 天気予報 (weather-bridge がある場合)
- 睡眠データ (biometric-bridge がある場合)
- キャラクター YAML の人格設定

1回の `speak` 呼び出し上限 (70文字) に収まるよう自動的に分割される。

### news_briefing

news-bridge が最後に生成したニュースサマリー (daily または最新 urgent) を取得して読み上げる。  
長い場合は 70文字ごとに分割して順番に発話する。

news-bridge のサマリー生成時刻は `NEWS_DAILY_HOUR` / `NEWS_DAILY_MINUTE` (デフォルト: `7` / `30`) で設定:

```bash
NEWS_DAILY_HOUR=7
NEWS_DAILY_MINUTE=30
```

### weather_report

ワールドモデルが保持する現在の天気情報と予報を読み上げる:

- 現在の天気・気温・降水確率
- 今日・明日の予報
- 警報がある場合はそれも含む

weather-bridge が起動していない場合は「天気データがありません」と通知する。

### task_planning

LLM が本日のタスクリストを整理し、優先順位や推奨開始時刻を添えて発話する。  
タスク情報は Backend から取得する。

### speak_custom

指定した固定文をそのまま発話する。イベントに `text` フィールドを追加して使う:

```json
{"event": "scheduled", "time": "22:00", "actions": ["speak_custom"], "text": "そろそろ寝る時間ですよ"}
```

### scene:*

`scene:` プレフィックスに続くシーン名を Backend 経由で実行する。  
例えば `scene:morning` は Backend に登録された `morning` シーンをトリガーする。

```json
{"event": "wake_up", "actions": ["scene:morning"]}
```

## Boot Load (事前生成ブリーフィング)

起床イベント (`wake_up`) 検知時、一部のアクションは検出前にあらかじめ音声を生成・キャッシュしておくことで、  
発話開始までの待ち時間を短縮する。

事前生成される内容:

- `weather_alert_announce` (警報がある場合)
- `morning_greeting`
- `news_briefing`
- `weather_report`

これらは `EVENT_AUTOMATIONS` の `wake_up` アクションに含まれていれば、Brain が起床検出の可能性を察知した段階で  
非同期に生成を開始する。Boot Load 対象外のアクション (`task_planning` / `speak_custom` / `scene:*` など) は、  
イベント検出後に通常通り生成・実行される。

## MQTT での手動トリガー

現状、イベント自動化を手動で発火するための MQTT トピック (`hems/brain/event` など) は未実装である。  
Brain が購読している MQTT トピックは `hems/brain/reload-character` と `hems/brain/guest-mode` のみ。

テストで自動化を発火させる場合は、該当するイベント検出条件 (バイオメトリクス、カメラ在室、HA 在室センサー、  
または `scheduled` の時刻) を再現するか、Brain 内部のイベント処理を直接呼び出す必要がある。

なお、以下のように `mosquitto_pub` のパスワード例を `.env` の `MQTT_PASS` に置き換えて使用する:

```bash
mosquitto_pub -h localhost -p 1893 -u hems -P <MQTT_PASS> \
  -t hems/brain/guest-mode -m '{"enabled": true}'
```

## クールダウン仕様

誤検知による連続発火を防ぐため以下のクールダウンが設定されている:

| イベント | クールダウン |
|---------|------------|
| `wake_up` | 1日1回 (日付が変わるまで再発火しない) |
| `arrival` | 1日1回 |
| `departure` | 1日1回 |
| `scheduled` | 1日1回 (時刻ごと) |

## トラブルシューティング

**自動化が実行されない**

```bash
# Brain ログでイベント検出を確認
docker logs hems-brain | grep -E "event|automation|wake_up|arrival"
```

**ニュースが読み上げられない**

```bash
# news-bridge の状態確認
docker logs hems-news-bridge | tail -30

# news-bridge が起動しているか確認
curl http://localhost:8021/api/news/latest
```

**朝の挨拶の内容が変わらない**  
→ LLM がセンサーデータにアクセスできているか確認。センサーが接続されていない場合は  
  固定的な挨拶文になることがある。センサーの MQTT 接続を確認すること。

**scheduled イベントが時刻通りに動かない**  
→ コンテナのタイムゾーンが正しいか確認:

```bash
docker exec hems-brain date
# .env: TZ=Asia/Tokyo
```
