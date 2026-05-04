# Wiring Gap 06 — データ流統合リファクタ計画

2026-05-03 全データソース audit (収集 → WorldModel → LLM context → Rule → Tool → Frontend) の結果に基づく統合リファクタ計画。

**前提ドキュメント** (積み残し統合元):
- `docs/wiring-gap-01-gas-expansion.md`
- `docs/wiring-gap-02-perception-enhancement.md`
- `docs/wiring-gap-03-biometric-enhancement.md`
- `docs/wiring-gap-04-sensor-utilization.md`
- `docs/wiring-gap-05-orphan-cleanup-and-underused-data.md`
- `docs/morning-briefing-refactor-plan.md` (Wave 1-3 完了済み)

**今回の方針**:
- 旧 wiring-gap 各文書の **未実装 / 部分実装** を抜き出す
- 今回 audit で **新規発見** したギャップを合流
- 1 つの優先順位付きロードマップに統合

---

## 1. 検証済み「既出未実装 / 部分実装」一覧

| ID | 出典 | 概要 | 現状 (file:line で再検証済) |
|---|---|---|---|
| 01-P0#1 | gap-01 | free_slots の時刻露出 | `_get_digital_context:2067` で 2h+ の **個数のみ**。`HH:MM-HH:MM` リスト未露出 |
| 01-P0#2 | gap-01 | gmail_recent の subject/sender 露出 | `world_model.py:1015` 格納済、context は **件数のみ**。`get_recent_emails` (tool_registry:894) 経由で取得は可能 |
| 01-P0#4 | gap-01 | GAS event の cause_event_id | event_store に `source_type` は記録 (gap-05 で `record_world_event` 追加済) だが、`llm_decisions` 行との FK 連携なし — 因果追跡不可 |
| 01-P1#5 | gap-01 | Meeting prep rule (30 min 前の通知) | rule_engine に該当 rule 0 件 |
| 01-P1#6 | gap-01 | Overdue escalation 拡張 (24h / 72h 段階) | 単発 alert (rule_engine:786 周辺) のみ。段階 escalation 未実装 |
| 01-P1#7 | gap-01 | 新 GAS tool 群 (`gas_query_free_slots` / `gas_query_gmail` / `gas_query_sheet`) | `get_recent_emails` のみ実装済、他 2 本未実装 |
| 02-P1#3 | gap-02 | Anomaly re-evaluation rule (5 min / 30 min escalate + 再スキャン要求) | 初回 speak のみで escalate 経路なし |
| 02-P1#4-5 | gap-02 | `vlm_history` deque + `list_scene_objects` / `get_scene_timeline` tool | tool は実装済 (tool_registry:777, 796)、ただし **context への vlm_history 反映は依然なし** (現在 snapshot のみ) |
| 03-P0#1 | gap-03 | bio context の stale 段階表示 (`live/N分前/stale`) | 現状は `last_update>0` の真偽値のみで `_get_user_context:2171-2204` に出力。"何分前" の prefix なし。`bio_stale_data` rule (rule_engine:1115) は別物 (沈黙アラート) |
| 03-P0#2 | gap-03 | steps 二重 publish 削除 | **未解消** — `services/biometric-bridge/src/main.py:128` (`/steps`) と `:178` (`/activity` 内 `steps`) の両方残存 |
| 03-P1#3 | gap-03 | Rolling window storage (history deque) | データクラスに history なし |
| 03-P1#4 | gap-03 | Trend rules (`_evaluate_fatigue_streak` / `_evaluate_sleep_decline` / `_evaluate_stress_hr_coupling`) | rule_engine に 0 件 |
| 03-P1#5 | gap-03 | `get_biometric_trend` / `get_sleep_history` tool | tool_registry に 0 件 |
| 03-P2#6-8 | gap-03 | fatigue→schedule_learner / stress→VLM 要求 / HRV→fatigue 計算式 | 未着手 |
| 04-P0#2 | gap-04 | weather alerts の subscriber + 文脈露出 | `_update_weather_state:1317-1334` で受信、`_get_physical_context:1969-1986` で context 露出は **既に実装済**。**rule での消費 / EventAutomation action は依然なし** (今回 audit で新規確認) |
| 05-B-1 | gap-05 | Heavy process rule (CPU 90% × 5 min / 単一 4GB+) | top_processes は context に CPU≥80% 時のみ露出 (実装済)、 **rule 未実装** |
| 05-B-4 | gap-05 | Bridge SLA ログ + frontend SLA badge | DB schema 変更必要のため deferred |
| 05-C-1 残 | gap-05 | `list_note_tags` / `get_recent_knowledge_changes` / `list_cameras` / `get_vlm_status` / `get_activity_history` | 未実装 |
| 05-C-3 | gap-05 | MotionRetriever rejection feedback loop (ack_learner 連携) | 未実装 |

---

## 2. 今回 audit で新規発見したギャップ

| ID | 概要 | 検証位置 |
|---|---|---|
| **G-NEW-1** | weather/alerts を **能動消費する rule / EventAutomation がゼロ** — 台風・大雨警報が context に乗るだけで自律行動も UI 表示もなし | rule_engine.py / event_automation.py / frontend |
| **G-NEW-2** | backend `Device` モデルの `link_quality` / `last_seen_reported` 列が alembic 未生成 — 既存 SQLite は手動 ALTER 必要 (gap-05 注意点で既知) | services/backend/models.py:210 / migrations/ 不在 |
| **G-NEW-3** | `personal/notes/changed` と `personal/knowledge/changed` の event 受信が rule / context 露出ゼロ — 変更検知トリガーが何にも繋がっていない | world_model.py:1685-1708 |
| **G-NEW-4** | `shopping/purchased` event log のみで rule / context 露出 / 学習どこにも流れない | main.py:439-444 |
| **G-NEW-5** | Frontend で **Weather / News / VLM scene / 体温・呼吸数 / PM2.5 / soil_moisture** が表示なし — 型は `types.ts` にあるがコンポーネント欠落 | services/frontend/src/components/ |
| **G-NEW-6** | bridge disconnect / sensor dead が UI で目立たない (warning text のみ、toast / banner / 集約 health badge なし) | frontend |
| **G-NEW-7** | アラート過去履歴 / 環境センサー 3-7 日トレンドグラフ / Device state 遷移ログがない | frontend |
| **G-NEW-8** | (派生) 旧 gap-04 P1#9 `get_sensor_history` tool は既存 (tool_registry:141) だが、long-term aggregate (時間別) を返す path は未拡張 | event_store/aggregator.py / tool_executor |

---

## 3. Wave 計画

### Wave 1 — 安全性 / 不具合修復 (P0、半日〜1日)

ユーザー影響直結。データの正確性・可観測性を取り戻す。

| # | 項目 | 対応 ID | 工数 | 効果 |
|---|---|---|---|---|
| 1.1 | weather/alerts rule 追加 | G-NEW-1 | 1.5h | 台風・大雨・地震警報を即時 speak + create_task。`severity in (warning, critical)` で分岐、24h cooldown |
| 1.2 | weather/alerts EventAutomation action `weather_alert_announce` | G-NEW-1 | 30m | morning_greeting と組合せて起床直後にも警報を読む |
| 1.3 | Frontend `WeatherAlertBanner` (dashboard 上部 sticky) | G-NEW-1, G-NEW-5 | 2h | 警報が UI で目立つ位置に出る (sticky banner + toast) |
| 1.4 | biometric `steps` 二重 publish 削除 | 03-P0#2 / G-NEW-2 (派生) | 30m | `services/biometric-bridge/src/main.py:177` の activity payload から `steps` フィールド除外、テスト追加 |
| 1.5 | backend Device alembic マイグレ生成 + 起動時 best-effort ALTER | G-NEW-2 | 1.5h | `link_quality` / `last_seen_reported` 列を既存 DB にも適用、device_health rule が静かに失敗しない |
| 1.6 | bio context の stale 段階ラベル化 | 03-P0#1 | 1h | `_get_user_context` で `< 600s` (live) / `< 3600s` (N 分前) / `>= 3600s` (stale) を prefix 付きで出力。LLM の判断を「古いデータでない」確信に変える |

**検証**:
```bash
# 1.1-1.3
mosquitto_pub -t hems/weather/alerts -m '{"alerts":[{"severity":"warning","title":"大雨警報","area":"東京"}]}'
docker logs hems-brain | grep -E "weather_alert"
# Frontend: dashboard top に banner 表示

# 1.4
curl -X POST http://localhost:8017/api/biometric/webhook -d '{"steps": 5000}'
mosquitto_sub -t 'hems/personal/biometrics/+/+' -v -C 5
# expected: steps が /steps だけ、/activity payload に含まれないこと

# 1.5
sqlite3 data/hems.db ".schema device" | grep -E "link_quality|last_seen_reported"

# 1.6
docker logs hems-brain | grep -E "HR.*\(live\)|HR.*分前\)"
```

---

### Wave 2 — LLM 文脈・行動拡張 (P1、1-2日)

LLM が能動的に判断できる材料を増やし、proactive 行動の幅を広げる。

| # | 項目 | 対応 ID | 工数 |
|---|---|---|---|
| 2.1 | `gmail_recent` を context に subject/sender で露出 (VIP_SENDERS と併用、最大 5 件、subject 60 字 truncate) | 01-P0#2 | 1h |
| 2.2 | `free_slots` の時刻露出 (`14:00-16:30` 形式で先頭 3 スロット) | 01-P0#1 | 30m |
| 2.3 | `vlm_history` を context に常時 1 行要約 (最近 3 snapshot のオブジェクト union + 最新 description) | 02-P1#4 | 1.5h |
| 2.4 | Meeting prep rule (30 min 前 speak + brightness 70% + 静音推奨)、event id 単位 1 回 cooldown | 01-P1#5 | 1.5h |
| 2.5 | Overdue escalation の段階化 (初回情報 speak / 24h priority 昇格 / 72h 削除候補提示) | 01-P1#6 | 1h |
| 2.6 | Anomaly re-evaluation rule (5 min 解消なし → escalate / 30 min → `hems/perception/vlm/request` で再スキャン) | 02-P1#3 | 1.5h |
| 2.7 | Heavy process rule (CPU 90% × 5min / 単一プロセス 4GB+ → speak、per-process 30 min cooldown) | 05-B-1 | 1h |
| 2.8 | `gas_query_free_slots(date_range_hours)` / `gas_query_sheet(name, max_rows)` tool 追加 | 01-P1#7 | 1.5h |
| 2.9 | C-1 残ツール群: `list_note_tags` / `get_recent_knowledge_changes` / `list_cameras` / `get_vlm_status` / `get_activity_history` | 05-C-1 残 | 2.5h |

**検証**:
```bash
# 2.1
docker logs hems-brain | grep -E "Gmail.*\[.*\]"
# 2.2
docker logs hems-brain | grep -E "free: \d{2}:\d{2}-\d{2}:\d{2}"
# 2.3-2.6
mosquitto_pub -t 'hems/perception/vlm/zone1' -m '{"anomalies":["unusual"]}'
# expected: 5min 後に escalate が出る

# 2.7 (mock)
mosquitto_pub -t hems/pc/processes/top -m '{"processes":[{"name":"chrome","cpu_percent":92,"mem_mb":4500}]}'
# 5min 後に speak
```

---

### Wave 3 — 生体トレンド / Frontend 表出 / Causality (P2、2-3日)

長期傾向の活用と、ユーザーが UI で全データソースに触れられる状態を作る。

| # | 項目 | 対応 ID | 工数 |
|---|---|---|---|
| 3.1 | `BiometricState.history: dict[metric, deque[(ts,value)]]` 追加 (HR maxlen 1440 / fatigue,sleep,stress 14 日分) | 03-P1#3 | 1.5h |
| 3.2 | Trend rules: `_evaluate_fatigue_streak` (3 日連続 ≥70) / `_evaluate_sleep_decline` (7 日比 -15%) / `_evaluate_stress_hr_coupling` (15 min stress>70 + HR baseline +20%) | 03-P1#4 | 2.5h |
| 3.3 | Trend tools: `get_biometric_trend(metric, window_hours)` / `get_sleep_history(days)` | 03-P1#5 | 1h |
| 3.4 | Frontend: `WeatherCard` (current + forecast 24h + alerts 履歴) | G-NEW-5 | 2.5h |
| 3.5 | Frontend: `NewsBanner` (urgent 即表示 + daily 折り畳み) | G-NEW-5 | 2h |
| 3.6 | Frontend: `UserStateCard` 拡張 — 体温 / 呼吸数 を追加 | G-NEW-5 | 30m |
| 3.7 | Frontend: `ZoneEnvironmentCard` 拡張 — pm25 / soil_moisture を追加 (rule 動作中だが UI 欠落) | G-NEW-5 | 30m |
| 3.8 | Frontend: `VLMSceneCard` (description + objects + 履歴 last 5) | G-NEW-5 | 2h |
| 3.9 | Frontend: `BridgeHealthBadge` 集約表示 (各 bridge の bridge_connected を一目で) | G-NEW-6 | 1.5h |
| 3.10 | GAS event の cause_event_id (event_store) | 01-P0#4 | 1.5h |
| 3.11 | personal/notes/changed と personal/knowledge/changed の utilizer (ambient_speaker / morning_briefing 言及 / context 1 行追加) | G-NEW-3 | 1.5h |

---

### Wave 4 — 観測性・履歴・長期 (P2-P3、3-5日)

| # | 項目 | 対応 ID | 工数 |
|---|---|---|---|
| 4.1 | Bridge SLA ログ (`BridgeStatusLog` テーブル + 7d/30d 稼働率 API + 過去 24h で 5回断絶 → speak rule) | 05-B-4 | 4h |
| 4.2 | Frontend: 環境センサー 3-7 日トレンドグラフ (TimeSeriesChart 拡張) | G-NEW-7 | 2.5h |
| 4.3 | Frontend: Device state 遷移ログ (last 24h timeline) | G-NEW-7 | 2h |
| 4.4 | Frontend: alert 過去履歴 panel (suppressed_alerts + voice_events をマージ) | G-NEW-7 | 2h |
| 4.5 | shopping/purchased event を ShoppingClassifier に流し、購買周期学習 | G-NEW-4 | 2.5h |
| 4.6 | `get_sensor_history` を hourly_aggregates 経由の long-term path に拡張 (24h+ 範囲) | G-NEW-8 | 1.5h |
| 4.7 | fatigue → schedule_learner.wake_offset 反映 / stress 急上昇 → vlm/request | 03-P2#6-7 | 3h |
| 4.8 | HRV を fatigue_score 計算式に追加 (HR 20% + HRV 15% + sleep 35% + stress 30%) | 03-P2#8 | 1h |
| 4.9 | MotionRetriever rejection feedback loop (ack_learner 連携) | 05-C-3 | 4h |

---

## 4. 依存関係 (並行実行可否)

```
Wave 1: 1.1 → 1.2 (1.1 の rule 出力 alert を action に流す)
        1.3 (frontend, 独立)
        1.4 (独立)
        1.5 (独立)
        1.6 (独立)

Wave 2: 2.1, 2.2, 2.3 (context 改修、独立並行可)
        2.4, 2.5, 2.6 (rule 追加、独立並行可)
        2.7 (rule、独立)
        2.8, 2.9 (tool 追加、独立並行可)

Wave 3: 3.1 → 3.2 → 3.3 (trend は history に依存)
        3.4-3.9 (frontend、独立並行可)
        3.10, 3.11 (event_store / context、独立)

Wave 4: 4.1 (Wave 3.9 の SLA badge UI に接続)
        他は概ね独立
```

**チーム作業時の suggested split**:
- Backend (brain) 担当: 1.1/1.2/1.4-1.6, 2.1-2.9, 3.1-3.3/3.10/3.11, 4.1/4.5-4.8
- Frontend 担当: 1.3, 3.4-3.9, 4.2-4.4
- Infra (DB migration) 担当: 1.5, 4.1, 4.9

---

## 5. 影響と前提

- **DB schema 変更** は 1.5 (Device 列) と 3.1 (BiometricState.history は in-memory なので不要) と 4.1 (BridgeStatusLog 新規テーブル) と 3.10 (event_store に cause_event_id 列) で発生。SQLite default で alembic を導入するか、`DROP TABLE` 再作成スクリプトを併用するかは Wave 1.5 着手時に判断。
- **LLM context 文字数** は Wave 2 で 200-400 字程度膨張する見込み。`_get_digital_context` / `_get_user_context` の length cap を 1500 字 → 1800 字に拡張、もしくは zone ごと max_chars を導入 (gap-01 既知リスクと同様)。
- **GAS quota** は wave 全体で polling cadence を変えないため安全 (1100/20000 計算)。
- **Frontend bundle size** は WeatherCard / NewsBanner / VLMSceneCard 追加で +20KB 程度。lazy load 推奨。
- **Frontend types.ts は型既定済**: weather / news / VLM scene の型は既に存在 — 新規追加は表示コンポーネントのみで API は再利用可。

---

## 6. 既知のリスク

- **G-NEW-2 (alembic 未生成)**: 既存運用環境では Wave 1.5 適用前に DB バックアップ必須。`hems_backend_data` volume 退避 → migration 試行 → 失敗時は restore できる手順を Wave 1.5 着手時に準備。
- **2.7 heavy process rule**: dev / test 環境で Chrome / Slack / VS Code が常に CPU 高負荷でフォルス・ポジティブが頻発する可能性。`HEMS_PROC_HEAVY_EXCLUDE` env で除外プロセス名リスト導入を併用。
- **3.2 trend rules**: 運用初期 (履歴 7 日未満) は trend 判定が不安定。最低 N サンプル (HR=30、fatigue=3 日、sleep=7 日) を gate に含める (gap-03 既知リスク踏襲)。
- **3.4 WeatherAlertBanner**: 警報多発期 (台風シーズン) で UI が常時占拠される懸念 → severity=warning 以下は折り畳み + critical のみ常時表示。
- **4.5 shopping/purchased**: 学習が誤解を生む (一度買っただけで「定期購入」扱いされる) リスク → 周期判定は最低 3 回以上の購入履歴を gate に。

---

## 7. 検証チェックリスト (Wave 完了時)

```bash
# Wave 1 後
mosquitto_pub -t hems/weather/alerts -m '{"alerts":[{"severity":"critical","title":"大雨特別警報"}]}'
docker logs hems-brain | grep weather_alert  # rule + action 確認
sqlite3 data/hems.db ".schema device" | grep -E "link_quality|last_seen_reported"  # 1.5
mosquitto_sub -t 'hems/personal/biometrics/+/+' -v -C 10  # 1.4 (steps が /steps のみ)

# Wave 2 後
docker logs hems-brain | grep -E "Gmail.*\[.*\]|free: \d{2}:\d{2}|objects:"

# Wave 3 後
sqlite3 data/hems_brain.db "select count(*) from llm_decisions where cause_event_id is not null"  # 3.10
# Frontend: dashboard で WeatherCard / NewsBanner / VLMSceneCard / 体温・呼吸数 / pm25 / soil 表示

# Wave 4 後
sqlite3 data/hems_brain.db "select service, count(*) from bridge_status_log where state='disconnected' group by service"
# Frontend: BridgeHealthBadge / 3-7 日トレンドグラフ / Device 遷移ログ
```

---

## 8. 旧 wiring-gap docs との関係

完了後、各 wiring-gap-XX に「**全項目が wiring-gap-06 に統合・解消済み**」のヘッダーを追加して chronological closure を残す。`MEMORY.md` の `project_wiring_gap_05.md` 参照は `project_wiring_gap_06.md` に置換。

---

最終更新: 2026-05-03
