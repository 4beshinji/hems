# Wiring Gap 05 — Orphan Cleanup と未活用データの解消

> **CLOSED 2026-05-03**: 全項目が [`wiring-gap-06-data-flow-consolidation.md`](wiring-gap-06-data-flow-consolidation.md) に統合・解消済み (Wave 1.5 で Device 列追加、Wave 2 で C-1 残ツール群、Wave 4.1 で B-4 Bridge SLA、Wave 4.9 で C-3 MotionRetriever rejection feedback)。

2026-04-30 監査 (`docs/IMPLEMENTATION_MAP.md` ベース) で抽出された配線ギャップを「根本原因 → 解消案 → 実装ステップ」の順で整理し、Wave 計画に落とす。`wiring-gap-04` で未着手の sensor 活用は引き続き有効。本ドキュメントは weather-bridge orphan 等の **メタな配線問題** に焦点を絞る。

## 進捗 (2026-04-30)

- ✅ **A 全完了**: weather-bridge を compose に常時起動として追加 (mosquitto ACL/passwd に `hems-weather` 追加)、data-bridge に README、sentinel 削除
- ✅ **B-1 / B-2 / B-3 / B-5 / B-6 完了**
- ⏸ **B-4 (Bridge SLA ログ)** deferred: DB schema 変更 + マイグレーション必要のため別 wave (P2)
- ✅ **C-1 priority 完了**: `get_power_consumption` (Tapo) / `get_entity_status` (HA) / `list_processes` (PC) を追加。`get_tools` / `get_chat_tools` に `gas_enabled` / `tapo_enabled` 引数を追加し chat allowlist にも反映
- ✅ **C-2 完了**: low-power mode + VLM swap 中は persona rewrite を skip
- ⏸ **C-1 残り 5 ツール / C-3 MotionRetriever feedback loop** deferred (P2/P3)

実装の品質改善 (post-impl review):
- 並列化: `get_power_consumption` の全プラグ列挙を `asyncio.gather` 化 (直列 5s × N → 1 round-trip)
- `_parse_iso_ts` を `services/brain/src/brain_utils.py:parse_iso_ts` に集約 (device_dispatcher / rule_engine の重複を解消)
- service VIP rule の `Event.timestamp` fallback を簡素化

対象: `infra/docker-compose.yml`, `services/weather-bridge/`, `services/data-bridge/`, `services/sentinel/`, `services/brain/src/world_model/world_model.py`, `services/brain/src/rule_engine.py`, `services/brain/src/tool_registry.py`, `services/brain/src/tool_executor.py`, `services/brain/src/dashboard_client.py`, `services/brain/src/persona_rewriter.py`, `services/brain/src/motion_retriever.py`, 各 bridge service の HTTP API。

監査時点の verification: `docs/IMPLEMENTATION_MAP.md` 各章の `Verification` コマンドで再現可能。

---

## A. ハードオーファン (compose 未統合)

### A-1. weather-bridge — コードあるが起動しない

**現状**:
- ソース: `services/weather-bridge/{Dockerfile, requirements.txt, src/{main.py, config.py, data_poller.py, weather_client.py, mqtt_publisher.py}}` 完備
- 公開予定トピック: `hems/weather/{current,forecast,alerts}` (data_poller.py:37 ほか)
- Brain 側 consumer: `world_model.py:_update_weather_state` (1220-1275) と `tool_executor.py:_handle_get_weather` (772-792) は実装済み
- env.example: 関連変数 (`WEATHER_PROVIDER`, `JMA_AREA_CODE`, `OWM_*`) 不足 — 本監査で追加済み
- 設計書 (CLAUDE.md / README.md) には "Weather Integration" として記載

**根本原因**:
- `infra/docker-compose.yml` に `weather-bridge` service ブロックが書かれていない (profile も無い)
- 結果として `WeatherState` は常に空 → `get_weather` が "天気データなし" を返す → EventAutomation の `weather_report` action もダミー出力 → "雨予報の前にカーテン閉め" のような **予報トリガーのアクションが構造的に不可能**

**解消案 (P0, 30分)**:
1. `infra/docker-compose.yml` に下記を追加 (常時起動 — profile 無し)。気象データは GAS (Calendar/Tasks) 同様にイベント駆動アクションの前提となる「常時欲しいベースデータ」なので、optional にしない。

```yaml
weather-bridge:
  build: ../services/weather-bridge
  container_name: hems-weather-bridge
  environment:
    - MQTT_BROKER=mosquitto
    - MQTT_PORT=1883
    - WEATHER_PROVIDER=${WEATHER_PROVIDER:-jma}
    - JMA_AREA_CODE=${JMA_AREA_CODE:-130000}
    - JMA_DETAIL_CODE=${JMA_DETAIL_CODE:-130010}
    - OWM_API_KEY=${OWM_API_KEY:-}
    - OWM_LAT=${OWM_LAT:-35.6762}
    - OWM_LON=${OWM_LON:-139.6503}
    - HEMS_WEATHER_CURRENT_INTERVAL=${HEMS_WEATHER_CURRENT_INTERVAL:-600}
    - HEMS_WEATHER_FORECAST_INTERVAL=${HEMS_WEATHER_FORECAST_INTERVAL:-1800}
  depends_on:
    - mosquitto
  restart: unless-stopped
```

2. CLAUDE.md / README.md の "ORPHAN" 注釈を解除。
3. Smoke test: `mosquitto_sub -h localhost -p 1893 -t 'hems/weather/#' -v` で受信を確認 → ブレインの `get_weather` が forecast を返すこと。

**追加で発火する rule / action**:
- `weather_report` EventAutomation action が実データで動作
- 既存 `rule_engine.py:271-280` の気圧降下ルールが forecast と相互参照可能 (将来)
- 新ルール候補: 「降雨予報1h以内 → 洗濯物アラート」「猛暑日予報 → 朝のうちにエアコン予冷タスク」

---

### A-2. data-bridge — Phase 2 用空 scaffold

**現状**:
- ディレクトリ: `services/data-bridge/src/bridges/` 空
- env.example: Strava / Fitbit / Garmin / Intervals.icu / Mi Band / Google Calendar の env が "Phase 2: data-bridge" コメント付きで残存 (270-286)
- Brain 側 consumer: `_update_personal` (1160-1177) は呼び出し可能、ただし実際のトピック (`hems/personal/calendar/{id}/events` 等) は未配信
- Mi Band / Strava 系の生体・運動データは `biometric-bridge` が Health Connect 経由で代替収集中

**根本原因**:
- 計画段階のまま実装が止まっている。当初想定の各 SaaS API 連携 (OAuth フロー必要) のコストが大きく、Health Connect 経由で代替できる用途が多数あった
- Google Calendar は GAS bridge で代替済み

**解消案 (P0, 5分 — 整理のみ)**:
- `services/data-bridge/` を削除する代わりに `services/data-bridge/README.md` を新規作成し「将来の Strava/Fitbit/Garmin 取込用 placeholder。現在は biometric-bridge と gas-bridge で代替中」と明記
- env.example の "Phase 2: data-bridge" セクションをコメントアウトのまま残し、警告コメントを追記
- CLAUDE.md / README.md の "future: data-bridge" 表記を維持しつつ「現状未稼働」を明示 (済)
- 削除しない理由: 後で Strava/Garmin を入れる時の足場として有用

---

### A-3. sentinel — pyc だけが残る死骸

**現状**:
- `services/sentinel/src/__pycache__/{config,escalation,rules,gray_zone,state}.cpython-313.pyc` 5ファイルのみ。`.py` ソース無し
- compose 未登録、import している場所無し
- 過去のリポジトリ履歴に残骸が残ったと推測

**根本原因**:
- 機能として何かを実装中だったが廃止 → ソース削除時に `__pycache__` が漏れた
- `.gitignore` の漏れか、明示的に commit されたか。`git log -- services/sentinel/` で経緯確認可

**解消案 (P0, 5分)**:
1. `git log --all -- services/sentinel/` で履歴確認
2. ディレクトリごと削除: `git rm -rf services/sentinel/`
3. `.gitignore` に `__pycache__/` 追記漏れがあれば修正

---

## B. MQTT Publish されているが活用されていない

### B-1. PC top processes — 取り込み済みだが LLM context 未露出

**現状**:
- 公開: localcraw-bridge → `hems/pc/processes/top`
- 取込: `world_model.py:_update_pc_state` line 761-770 で `pc.top_processes: list[ProcessInfo]` に格納
- 露出: `tool_executor.py:_handle_get_pc_status` line 488-491 で `args.include_processes=true` の場合のみ返す。LLM が能動的に問い合わせない限り context に入らない
- `dashboard_client.py:194-196` で frontend には常時送信
- rule_engine: top_processes を見るルール無し

**根本原因**:
- 「proactive にプロセス一覧を context に入れるとプライバシー懸念 + token を浪費」という当初設計
- ただし「Chrome が 8GB 食ってる」「Slack で CPU 90%」のような状況での提案には欠かせない情報

**解消案 (P1, 1h)**:
1. `world_model.py:_get_digital_context` (1926-2032) の PC 節 (CPU 使用率 90% 超 or Memory 90% 超のとき) に top 3 processes を追記:
   ```python
   if pc.cpu.usage_percent > 80 and pc.top_processes:
       top3 = ", ".join(f"{p.name}({p.cpu_percent:.0f}%)" for p in pc.top_processes[:3])
       parts.append(f"  上位プロセス(CPU): {top3}")
   ```
2. 同様に Memory 高負荷時に `mem_mb` ベースで top 3 を追加
3. **Heavy process rule** を `rule_engine.py` に追加:
   - 単一プロセスが CPU 90% 以上を 5分継続 → speak "{name} がCPUを{N}%占有しています。閉じても大丈夫ですか？"
   - 単一プロセスが 4GB 以上消費 → speak "{name} が{N}GBメモリを使っています。再起動を検討してください"
   - cooldown: per-process 30min
4. 既存テストに dataclass 追加分のスナップショットテストを追加

---

### B-2. Service edge events — 即時サイクル発火はするが urgency 識別なし

**現状**:
- 公開: localcraw-bridge → `hems/services/{name}/event` (Gmail unread 増加, GitHub PR レビュー要求等)
- 取込: `_update_service_state` line 877-885 が `services_state.events` に Event 追加
- サイクル発火: `main.py:481-498` の `current[__services__]` 比較で event count 変化 → `_cycle_triggered.set()` (即時起動)
- LLM context: `_get_digital_context` で recent events として表示
- urgency 識別: 全イベント severity=0 で同列扱い

**根本原因**:
- localcraw 側で sender / 件名のメタ情報を payload に乗せているが、Brain 側で重要連絡先 / プロジェクトの優先度を学習していない
- 全 unread を平等に扱うため「上司・家族からのメール」と「メルマガ」が区別できない

**解消案 (P1, 4h)**:
1. **設定ベース approach (簡易)**: env で重要連絡先を定義
   ```
   HEMS_GMAIL_VIP_SENDERS=boss@example.com,family@example.com
   HEMS_GITHUB_VIP_REPOS=org/critical-repo
   ```
2. localcraw-bridge 側で event 発行時に `vip: true/false` を含める (送信者照合)
3. `_update_service_state` で `payload.get("vip", False)` を見て severity=2 / event_type="service_vip_event" に変換
4. `rule_engine.py` に vip event rule:
   - severity 2 のサービスイベント → 即時 speak (cooldown 5min)
5. **学習ベース approach (将来)**: Brain `Annotators` の RulePromoter を流用して頻繁に手動で開くメールの sender を「重要」に昇格

実装優先度: 1-4 のみで充分体感できる。学習版は次 wave。

---

### B-3. VLM model_swap — フラグ参照のみ、履歴・失敗カウント無し

**現状**:
- 公開: perception → `hems/perception/vlm/model_swap` (モデル切替イベント)
- 取込: `_update_vlm` line 1010-1105 内で `vlm_model_swap_active` フラグ更新
- 利用: `main.py:666-670` で active 中は LLM パスをスキップして rule-based mode
- 履歴: 全く記録されない (swap 開始/完了タイムスタンプ・失敗カウントなし)

**根本原因**:
- "rule fallback に切り替える" というシンプルな目的のためだけに導入された minimum viable な実装
- swap が 30s で完了する想定 → 過剰設計を避けた
- ただし VLM モデル swap がスタック → ブレインが永続的に LLM を呼べなくなる障害が発生した場合に検知できない

**解消案 (P2, 2h)**:
1. `data_classes.py` に `VLMSwapStats` dataclass 追加 (`world_model/data_classes.py` 末尾近く):
   ```python
   @dataclass
   class VLMSwapStats:
       last_swap_start_ts: float = 0
       last_swap_end_ts: float = 0
       last_swap_duration_sec: float = 0
       success_count: int = 0
       failure_count: int = 0
       longest_swap_sec: float = 0
   ```
2. `WorldModel.__init__` に `self.vlm_swap_stats = VLMSwapStats()` を追加
3. `_update_vlm` で swap 開始/完了/失敗時にカウンター更新
4. `rule_engine.py` 新ルール: swap > 60s 持続 → severity 2 で create_task("VLM切替が長時間スタック")
5. 30 cycle に 1 回程度 dashboard へ swap stats を push

---

### B-4. `*/bridge/status` — bridge_connected boolean のみ、SLA 履歴なし

**現状**:
- 公開: 各 bridge → `hems/{ha,gas,obsidian,switchbot,perception,biometric,news,knowledge,tapo}/bridge/status` (一部実装に揺れあり)
- 取込: `_update_*_state` 系で `bridge_connected = bool(payload.get("connected"))`
- 履歴: いつ落ちたか / 復帰したか / 連続障害日数の記録なし

**根本原因**:
- 「ヘルスチェックは現在の状態だけ知れればよい」という当初仮定
- 結果として「最近 GAS が頻繁に切れる → polling 間隔を広げる / API quota チェック」のような自己適応ができない

**解消案 (P2, 3h)**:
1. `event_store/models.py` に `BridgeStatusLog` テーブル追加:
   ```python
   class BridgeStatusLog(Base):
       __tablename__ = "bridge_status_log"
       id = Column(Integer, primary_key=True)
       service = Column(String, index=True)
       state = Column(String)  # connected | disconnected | error
       error_message = Column(Text, nullable=True)
       ts = Column(Float, index=True)
   ```
2. `event_store/writer.py` に `record_bridge_status(service, state, error)` 追加
3. `world_model.py` の各 `_update_*_state` で connected 値変化時のみ `event_writer.record_bridge_status` を呼ぶ
4. backend に `/bridge_status/sla` API 追加 (過去 7d / 30d 稼働率)
5. dashboard frontend に SLA badge 表示
6. rule_engine: 過去 24h で 5回以上断絶 → speak "{service} が頻繁に切れています。設定を確認してください" (1日 1回 cooldown)

---

### B-5. Z2M battery / linkquality / last_seen — ほぼ完全スルー

**現状**:
- Z2M payload: `{state, battery, linkquality, last_seen, voltage, ...}` を device 単位で送信
- `_update_zigbee_state` (1127-1158) は `_SKIP_KEYS = {"zone", "linkquality", "battery", "voltage", "update", "update_available", "last_seen", "elapsed", "state", "power_on_behavior"}` で battery 等を **明示的に skip**
- `device_dispatcher.parse_mqtt` (line 110, 174) が `battery_pct=payload.get("battery")` を Observation 経由で `DeviceRegistry` に格納 (経路1)
- DeviceRegistry: `battery_pct` 保持、`get_status_summary` で `battery_pct < 20` を低バッテリー警告表示 (line 151-172)
- linkquality / last_seen: **どこにも保存されない**
- rule_engine: battery を見るルール無し → "電池切れる前にタスク作成" ができない

**根本原因**:
- 当初設計で zigbee の sensor channel routing と device metadata を分離するため `_SKIP_KEYS` を導入したが、battery 系もそこに含まれた
- DeviceRegistry には流れているので「全く知らない」わけではないが、低バッテリー時の能動アクションが無い
- linkquality は無線リンク品質 (LQI) で、低い場合は接続不安定 → 早めの中継器配置のヒントになる

**解消案 (P1, 2.5h)**:
1. `device_registry.py` の `Device` に `link_quality: int | None`, `last_seen_ts: float | None` を追加
2. `device_dispatcher.parse_mqtt` の Z2M ハンドラで `link_quality=payload.get("linkquality")` `last_seen_ts=parse_iso(payload.get("last_seen"))` を Observation に乗せる
3. `device_registry.update_from_observation` で両者を保存
4. `get_status_summary` を拡張:
   - `battery_pct < 20` → 既存の低バッテリー警告
   - `link_quality < 50` → 信号弱警告 (Z2M LQI スケール 0-255、50 以下が unstable)
   - `last_seen_ts` が 1日以上前 → "デバイス応答なし"警告
5. `rule_engine.py` 新ルール:
   - battery_pct ≤ 10 で 1 回限定 (cooldown 7日) → create_task "{device} 電池切れ間近 (残り{N}%)"
   - last_seen 24h 以上 → create_task "{device} 反応なし — 確認/再ペアリング"
6. (オプション) DB マイグレーション: backend の `Device` モデル (services/backend/models.py:210) にも同フィールド追加

---

### B-6. Per-Gmail thread detail — list は受信、context は件数のみ

**現状**:
- gas-bridge `hems/gas/gmail/recent` 配信 → `world_model.py:965` `gs.gmail_recent = payload.get("threads", [])` に格納
- LLM context 露出: `_get_digital_context` で件数のみ
- `rule_engine.py:_evaluate_gas_rules` は `gas.gmail_summary.unread_count` ベースのアラートはあるが、threads 内の sender / subject を見るロジック無し
- 既存ツール: 一覧取得用ツールが無い (LLM は能動的に取れない)

**根本原因**:
- 個別メール内容は Gmail UI で見るため Brain で扱う必要は無い、という当初判断
- ただし「重要送信者からの未読が 30 分以上残っている」のような指摘は context に detail がないと出来ない

**解消案 (P2, 2h)**:
1. ツール `get_recent_emails(limit, sender_contains=None, subject_contains=None)` を `tool_registry.py` / `tool_executor.py` に追加 (gas profile gated)
2. world_model から `gs.gmail_recent[:limit]` をフィルタして返却。subject / from / snippet (50字) / thread_id を返す
3. (任意) B-2 で導入する VIP_SENDERS と組み合わせて、`_get_digital_context` で「VIP からの未読: N件 ({sender_short})」を 1 行追加

---

## C. 軽量な機能配線拡張

### C-1. Bridge HTTP API → ツール化漏れ

下記は HTTP では取れるが LLM ツール化されていない。すべて読み取り系で副作用なし、profile に紐づけて公開する。

| Bridge | Endpoint | 提案ツール名 | 必要 profile | 想定用途 |
|--------|----------|-------------|--------------|----------|
| ha-bridge | `GET /api/device/{entity_id}` | `get_entity_status` | ha | 単一エンティティの即時クエリ (バッテリ・接続状態) |
| biometric-bridge | `GET /api/biometric/activity` | `get_activity_history` | biometric | 過去N日分の活動量履歴 |
| obsidian-bridge | `GET /api/notes/tags` | `list_note_tags` | obsidian | タグ別ノート探索 |
| switchbot-bridge | `GET /api/devices/{id}/status` | (`describe_device` で代替済) | — | (`list_devices` + `describe_device` で吸収可能) |
| tapo-bridge | `GET /api/devices/{ref}/status` | `get_power_consumption` | tapo | **瞬時電力 W 取得** — 累計しか LLM context に来ていない |
| perception | `GET /api/perception/cameras` | `list_cameras` | perception | カメラ構成・解像度・FPS の確認 |
| perception | `GET /api/perception/vlm/status` | `get_vlm_status` | perception | VLM モデル名 / 最終分析時刻 |
| knowledge-bridge | `GET /api/knowledge/recent` | `get_recent_knowledge_changes` | knowledge | 直近変更ドキュメント |
| localcraw-bridge | `GET /api/pc/processes` | `list_processes` | localcraw | フィルタ付きプロセス一覧 |

**根本原因**: 必要に応じて段階的にツール追加してきたが、ある時点でカバレッジ全件レビューを行っていない。

**解消案 (P1, 各 30分)**: tool_registry.py + tool_executor.py に schema + dispatch を追加。bridge 側の追加実装は不要 (既存エンドポイントを叩くのみ)。`describe_device` で代替可能なものは追加しない (= switchbot status は skip)。

優先度高: `get_power_consumption` (Tapo の電力計測こそ Tapo を選んだ理由) > `get_entity_status` > `list_processes`。

---

### C-2. PERSONA_REWRITE_ENABLED の自動制御

**現状**: env 固定。`PowerModeManager.is_low_power` 中も rewrite が走り 1-3s 余計にかかる。

**根本原因**: PowerMode 機構導入時に PersonaRewriter まで切替対象を拡げていない。

**解消案 (P2, 30分)**:
- `Brain._run_rule_actions` (main.py:518-539) の persona_rewrite ガード条件に `not self.power_mode_manager.is_low_power` を追加
- 低消費電力モード時は素のメッセージで発話 (応答性優先)
- LLM Stage 2 (tool_executor._handle_speak の overlay) も同様に low_power 時はスキップ

---

### C-3. MotionRetriever フィードバックループ

**現状**:
- `motion_retriever.py` の serendipity scoring に `usage decay` (使用回数) は実装済み
- mobile companion の `ack_learner` (voice_capsule/ack_learner.py) はユーザーの音声 ack パターンを学習しているが、motion 選定にフィードしていない
- 結果として「ユーザーが嫌って早めに ack した発話に紐づくモーション」が再選択され続ける

**根本原因**: feature 設計時にフィードバックループを別 wave に切ってあった。

**解消案 (P3, 4h — 大きい)**:
1. `ack_learner` から発話 ID 単位の rejection 率を取得
2. 発話 ID と motion ID のマッピングを記録 (1 発話に複数 motion 候補を選ぶため、選定時の seed を保存)
3. `MotionRetriever.score()` に rejection penalty 項を追加
4. テスト: synthetic ack pattern で penalty が効くことを確認

優先度低 — 機能的に動いており、生活体験への影響は小さい。

---

## Wave 計画

### Wave 1 (P0, 半日 — 即実施推奨)

| 項目 | 工数 | 効果 |
|------|------|------|
| A-1 weather-bridge を compose に追加 | 30min | 天気予報ベースの全アクションが解禁 |
| A-2 data-bridge に README.md 追加して整理 | 5min | 死蔵フォルダの意図明示 |
| A-3 sentinel ディレクトリ削除 | 5min | リポジトリ衛生 |
| 動作確認 + ドキュメント更新 (CLAUDE.md ORPHAN 注釈解除) | 30min | — |

### Wave 2 (P1, 1日 — 短期)

| 項目 | 工数 | 効果 |
|------|------|------|
| B-1 PC top processes を context + rule に組込 | 1h | 高負荷時のプロセス特定提案 |
| B-2 Service edge event の VIP urgency | 4h | 重要メールの即時通知 |
| B-5 Z2M battery / link_quality / last_seen | 2.5h | 電池切れ予兆・ペアリング切れ検知 |
| C-1 Tool 追加 (Tapo 電力 + PC processes + HA 単一 entity) | 2h | LLM の情報取得幅が広がる |

### Wave 3 (P2, 1-2日 — 中期)

| 項目 | 工数 | 効果 |
|------|------|------|
| B-3 VLM swap stats | 2h | swap スタック障害の検知 |
| B-4 Bridge SLA ログ + frontend badge | 3h | ヘルスチェックの定量化 |
| B-6 get_recent_emails ツール | 2h | per-thread 確認手段 |
| C-1 残り (list_note_tags / get_recent_knowledge_changes / list_cameras / get_vlm_status / get_activity_history) | 2.5h | 各 bridge の readonly endpoint をツール化 |
| C-2 PERSONA_REWRITE 自動制御 | 30min | 低消費電力時のレイテンシ改善 |

### Wave 4 (P3, 後回し)

| 項目 | 工数 | 効果 |
|------|------|------|
| C-3 MotionRetriever フィードバックループ | 4h | 嫌われたモーションの自動回避 |

---

## 検証手順 (Wave 完了後の確認)

各 Wave 完了時に下記を実行し、`docs/IMPLEMENTATION_MAP.md` 各章の Verification と整合させる。

```bash
# Wave 1 後
docker compose up -d --build weather-bridge
mosquitto_sub -h localhost -p 1893 -t 'hems/weather/#' -v        # ペイロード受信
docker exec hems-brain python -c "from world_model import WorldModel; ..."  # WeatherState 充填確認
ls services/data-bridge/README.md && [ ! -d services/sentinel ]  # cleanup 確認

# Wave 2 後
docker logs hems-brain | grep "上位プロセス"                      # B-1
mosquitto_pub -t 'hems/services/gmail/event' -m '{"vip":true,...}' # B-2
sqlite3 data/hems.db "SELECT * FROM device WHERE battery_pct<20"  # B-5

# Wave 3 後
sqlite3 data/hems.db "SELECT service, COUNT(*) FROM bridge_status_log WHERE state='disconnected' GROUP BY service"  # B-4
```

---

## 既知のリスク

- A-1: weather-bridge 追加で常時起動サービスが 1 つ増える (リソース ~30MB)。compose default profile に入れると `--profile` 指定なしの最小構成にも入るので、当面は profile=`weather` を切るほうが保守的かもしれない。判断はユーザー指示待ち。
- B-2: VIP_SENDERS を env で hard-code すると秘密情報が `.env` に残る。`config/vip_contacts.yaml` への外出しが望ましい。
- B-5: DB スキーマ変更 (battery / link_quality / last_seen) は alembic マイグレーション必須。SQLite default なので `alembic upgrade head` で完結する想定。
- C-1: ツールが増えると LLM の tool selection 精度が落ちるリスク。chat allowlist (`get_chat_tools`) の見直しを Wave 完了時に行う。

---

最終更新: 2026-04-30
