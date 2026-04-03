# イベント自動化 設定ガイド

特定のライフイベント (起床・帰宅・外出など) を検出して、ニュース読み上げ・天気報告・朝の挨拶を  
自動的に実行する機能。`EVENT_AUTOMATIONS` 環境変数で設定する。

## デフォルト動作

設定なしの場合、起床検知 → 朝の挨拶 + ニュース読み上げ + 天気報告 が実行される:

```json
[{"event": "wake_up", "actions": ["morning_greeting", "news_briefing", "weather_report"]}]
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
| `morning_greeting` | LLM がセンサーデータ・天気・予定を参照して自然な挨拶文を生成・発話 |
| `news_briefing` | news-bridge から最新のニュースサマリーを取得して発話 (`--profile news` 必須) |
| `weather_report` | ワールドモデルの天気情報を発話 (weather-bridge データを使用) |

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
  {"event": "wake_up", "actions": ["morning_greeting", "news_briefing", "weather_report"]},
  {"event": "arrival", "actions": ["morning_greeting"]},
  {"event": "scheduled", "time": "12:00", "actions": ["weather_report"]}
]'
```

**ニュース不使用 (news-bridge なし):**

```bash
EVENT_AUTOMATIONS='[
  {"event": "wake_up", "actions": ["morning_greeting", "weather_report"]},
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
  {"event": "scheduled", "time": "07:30", "actions": ["morning_greeting", "news_briefing", "weather_report"]},
  {"event": "scheduled", "time": "19:00", "actions": ["news_briefing"]}
]'
```

## 必要なプロファイル

| アクション | 必要なプロファイル |
|-----------|------------------|
| `morning_greeting` | なし (LLM は常時利用) |
| `news_briefing` | `--profile news --profile ollama` |
| `weather_report` | なし (weather-bridge データが推奨、なくても動作) |

```bash
# news_briefing を使う場合
docker compose --profile news --profile ollama up -d --build
```

## 各アクションの詳細

### morning_greeting

LLM が以下の情報をもとに自然な挨拶文を生成して発話する:
- 現在の室温・湿度・CO2 (センサーがある場合)
- 天気予報 (weather-bridge がある場合)
- 今日のカレンダー予定 (GAS bridge がある場合)
- キャラクター YAML の人格設定

1回の `speak` 呼び出し上限 (70文字) に収まるよう自動的に分割される。

### news_briefing

news-bridge が最後に生成したニュースサマリー (daily または最新 urgent) を取得して読み上げる。  
長い場合は 70文字ごとに分割して順番に発話する。

news-bridge のサマリー生成時刻は `NEWS_DAILY_TIME` (デフォルト: `07:30`) で設定:

```bash
NEWS_DAILY_TIME=07:30   # .env
```

### weather_report

ワールドモデルが保持する現在の天気情報と予報を読み上げる:
- 現在の天気・気温・降水確率
- 今日・明日の予報
- 警報がある場合はそれも含む

weather-bridge が起動していない場合は「天気データがありません」と通知する。

## MQTT で手動トリガー

テスト用に任意のイベントを手動発火できる:

```bash
# 起床イベントを手動トリガー
mosquitto_pub -h localhost -p 1893 -u hems -P hems_dev_mqtt \
  -t hems/brain/event -m '{"type": "wake_up"}'

# 帰宅イベントを手動トリガー
mosquitto_pub -h localhost -p 1893 -u hems -P hems_dev_mqtt \
  -t hems/brain/event -m '{"type": "arrival"}'
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
curl http://localhost:8021/api/news/summary
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
