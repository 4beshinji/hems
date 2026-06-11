# HEMS Lite — 子機リファインメント計画

> **Status: HISTORICAL(2026-06-11 付記)** — `lite` ブランチは凍結中。本資料は Phase A+C(2026-05-04)時点の基準線であり、main はその後 2026-05-25 R0-R8 リファクタ等で大きく進行済み。現行の負債状況は `docs/audit/2026-06-11/SUMMARY.md`、実行計画は `docs/refactor/2026-06-11/PLAN.md` を参照。lite 再開時の復旧ガイドとして保持する。

> 作成: 2026-05-04 / 対象ブランチ: `lite` (最終 commit `39dcc43`, 2026-03-05)
> 起点ブランチ: `hardening/p0-impl` (進化先, 2026-04-30+)
> 関連: [Phase A+C ビルド改善](../../infra/base/Dockerfile)

## 1. 現状スナップショット

### lite ブランチ構成 (2026-03-05 凍結)

```
services/sentinel/        # ルール+グレーゾーン+クラウドLLM の見守りエンジン
  src/
    config.py             # 109 行  閾値+環境変数
    state.py              # 233 行  OccupantState (BiometricReading/SleepData/ActivityData/EnvironmentData/ZoneState)
    rules.py              # 443 行  RuleEngine (25+ rules across biometric/activity/environment)
    gray_zone.py          # 340 行  GrayZoneDetector (compound_anomaly/trend/contradiction/sensor_gap/behavior_deviation)
    escalation.py         # 227 行  Escalator (OpenAI/Anthropic + budget control)
    db.py                 # 131 行  SentinelDB (alerts + behavior baselines)
    main.py               # 455 行  60秒サイクル MQTT サブスク + ルール評価 + 通知
services/notifier/        # 通知ゲートウェイ (LINE/Discord/Slack/ntfy 順次送信)

infra/
  docker-compose.lite.yml         # 必須 3 (mosquitto/sentinel/notifier) + profile (biometric/perception/ha)
  mosquitto/mosquitto-lite.conf   # 7 行 (anonymous yes、ACL なし)
  mosquitto/bridge.conf.example   # 本体 HEMS への MQTT bridge (satellite mode)

env.lite.example                  # 106 行
docs/lite/README.md               # 884 行 包括ドキュメント
```

### 性能・運用特性

- 想定 HW: Raspberry Pi 4 / Skylake NUC i3
- メモリ: 170-520MB
- LLM: クラウド API (gpt-4o-mini / claude-haiku-4.5)、50 calls/day budget
- 出力: LINE / Discord / Slack / ntfy のメッセージ通知のみ (UI なし)
- 動作モード: standalone / satellite / hybrid

### 凍結後に発生したドリフト

`hardening/p0-impl` ↔ `lite` の差分:
- `593 files changed, 8451 insertions(+), 57104 deletions(-)`
- 多くは hardening ブランチ側の追加 (lite には不要なものも多い)

---

## 2. ギャップ分析: 本体から取り込みたいもの

> 凡例: 🔴 セキュリティ必須 / 🟡 高価値 / 🟢 nice-to-have

| # | 取り込み対象 | 理由 | 影響 | コスト |
|---|---|---|---|---|
| G1 | 🔴 mosquitto ACL ハード化 | lite は `anonymous yes`、LAN内設置でも危険 | 既存 sentinel/notifier に MQTT user 追加 | 小 |
| G2 | 🔴 mosquitto entrypoint パスワード生成 | hardcoded password 排除 | env.lite.example 改修 | 小 |
| G3 | 🟡 Phase A+C ビルド改善 (.dockerignore / hems-base / cache mount) | 子機こそビルド軽量化が効く (Pi上で再ビルドする場合) | sentinel/notifier Dockerfile を hems-base 化 | 小 |
| G4 | 🟡 Sunrise Alarm | 高齢者の起床支援 (Zigbee bedside light gradual ramp) | sentinel に sunrise_alarm.py 移植、HA bridge 連携 | 中 |
| G5 | 🟡 Schedule Learner (本体の `schedule_learner.py`) | 起床/在宅/外出パターン学習 → 異常検出精度向上 | sentinel の `behavior_deviation` を学習ベースに置換 | 中 |
| G6 | 🟡 Mobile Companion 通知チャネル | 家族の Android アプリに pre-synth 音声/通知配信 (LINE 不要化) | notifier に新プロバイダ追加 | 中 |
| G7 | 🟡 Boot-load Manager (起床前 1 回だけ heavy LLM 要約) | 朝の家族向けデイリーサマリー精度UP | escalation 別エンドポイントとして実装 | 中 |
| G8 | 🟢 PowerModeManager | Pi の sleep mode (LLM 呼び出し停止帯) | sentinel cycle に組み込み | 中 |
| G9 | 🟢 World Model 共有化 | 二重実装解消 (state.py vs world_model/) | 本体側の OccupantState 抽出 → 共有パッケージ化 | 大 |
| G10 | 🟢 weather-bridge (本体) | 環境異常 (台風接近) も通知対象に | profile 追加 | 小 |
| G11 | 🟢 news-bridge urgent news | 緊急地震速報・災害情報をエスカレーション | profile 追加 | 小 |

### lite に **取り込まない** もの (意図的に弾く)

- ReAct ループ — 軽量化の根本に反する
- Frontend (React SPA) — UI なし設計が前提
- voice-service (TTS) — 音声出力は家族側 Mobile Companion で行う
- VRM/PSD avatar — UI なし
- Brain ReAct + tool registry — Sentinel の rule + escalation で代替
- Annotators / RulePromoter — ルールは手動メンテで十分 (見守り用途は variation 少)
- Multi-LLM provider (Ollama 同梱) — クラウド API のみで OK

---

## 3. 新規追加したい lite 専用機能

| # | 機能 | 価値 | 工数 |
|---|---|---|---|
| N1 | Alpine ベースイメージ option | sentinel/notifier 173MB → 60-80MB、Pi の SD 寿命に効く | 中 |
| N2 | Daily summary via cloud LLM (1 call/day, heavy) | 家族向け朝の状況サマリー (CRITICAL なし → 「今朝も平常です」) | 中 |
| N3 | Sentinel rule の YAML 化 | env vars だらけの閾値定義を 1 ファイルに集約、設置ごとに手動編集しやすく | 中 |
| N4 | Gray Zone 重み学習 (オプション) | 個人差対応 (基準値を3週間で自動調整) | 大 |
| N5 | 自己診断 endpoint (`/diag`) | 家族が遠隔で「ちゃんと動いてる?」を確認できる小UI | 小 |
| N6 | Push 通知の冪等キー | 同一アラートの重複通知防止 (notifier 側でハッシュ管理) | 小 |
| N7 | 設置ガイド (Pi imager script) | `curl ... \| sh` で Pi 4 に丸ごと焼く `setup.sh` | 中 |

---

## 4. リファインメント Wave 計画

### B0: 準備 (作業日の最初)

```bash
git worktree add ../hems-lite lite
cd ../hems-lite
git fetch origin
# main にマージ済みの hardening 改善を確認
git log lite..origin/main --oneline | head -30
```

- main / hardening の現状確認
- B1〜の作業ブランチ `lite-refine` を `lite` から切る
- 既存テスト (`services/sentinel/tests/`) を実行してベースライン確認

成果物: なし。

---

### B1: セキュリティ + ビルド改善 (低リスク・高価値)

**目標**: lite を本体と同レベルのセキュリティに、かつ Phase A+C の build 改善を享受。

| ファイル | 操作 |
|---|---|
| `infra/mosquitto/mosquitto-lite.conf` | `anonymous false` に変更、`acl_file /mosquitto/config/acl-lite.txt` 追加 |
| `infra/mosquitto/acl-lite.txt` (新規) | hardening 側 `acl.txt` の sentinel/notifier 専用サブセット |
| `infra/mosquitto/entrypoint-lite.sh` (新規) | 本体側 `entrypoint.sh` を sentinel/notifier 用にスリム化 |
| `infra/docker-compose.lite.yml` | mosquitto エントリ更新 (entrypoint, MQTT_PASS env) / sentinel に MQTT_USER=hems-lite-sentinel 追加 |
| `services/sentinel/src/main.py` | MQTT username/password 認証対応 (環境変数読み込み) |
| `services/sentinel/Dockerfile` | `FROM hems-base:py3.11` 化 + cache mount |
| `services/sentinel/.dockerignore` | 新規 (Phase A の bridge 版同等) |
| `services/notifier/Dockerfile` | 同上 |
| `services/notifier/.dockerignore` | 新規 |
| `infra/base/Dockerfile` | (Phase C で作成済み) — 流用 |
| `env.lite.example` | `MQTT_PASS=` 追加 (?は強制) |

**チェックポイント**:
- 既存 sentinel/notifier テストが PASS
- `docker compose -f docker-compose.lite.yml up -d` が anonymous なしで動く
- `mosquitto_pub -u 別user` でアクセス拒否されることを手動確認

**ROI**: 高 (子機 set up 失敗リスクの本質的低減)

---

### B2: Sunrise Alarm + Mobile Companion 通知

**目標**: 子機の "見守り" を一歩進めて、能動的な家族支援機能を追加。

#### B2-a: Sunrise Alarm

| ファイル | 操作 |
|---|---|
| `services/sentinel/src/sunrise_alarm.py` (新規) | hardening の `services/brain/src/sunrise_alarm.py` から HA bridge 依存部分を抽出 |
| `services/sentinel/src/main.py` | sunrise_alarm を初期化、起床予測時刻 -2hr から段階的 publish |
| `infra/docker-compose.lite.yml` | `--profile ha` の有効化フラグを sentinel 環境変数に追加 |
| `env.lite.example` | `SUNRISE_ALARM_DEVICE`, `SUNRISE_ALARM_START_SEC`, `SUNRISE_ALARM_END_SEC` |

**前提条件**: lite に ha-bridge profile が既存 → そのまま活かせる。

#### B2-b: Mobile Companion 通知プロバイダ

| ファイル | 操作 |
|---|---|
| `services/notifier/src/providers/mobile_companion.py` (新規) | hardening 側の `services/backend/routers/mobile.py` クライアント実装。HMAC 署名付き webhook POST |
| `services/notifier/src/providers/__init__.py` | 登録 |
| `services/notifier/src/main.py` | env で provider 自動選択 |
| `env.lite.example` | `MOBILE_COMPANION_URL`, `MOBILE_COMPANION_HMAC_KEY`, `MOBILE_COMPANION_DEVICE_ID` |

**懸念**: Mobile Companion の HMAC 仕様 (`backend/auth.py:verify_mobile_device`) が変わると lite 側もメンテ要 → 共有 schema/contract を `apps/healthconnect-companion/SCHEMA.md` あたりに固定化する。

**ROI**: 高 (LINE Notify 廃止予定なので Discord/ntfy 以外の "親家族向け" 通知パスが必要)

---

### B3: Schedule Learner + Boot-load Daily Summary

**目標**: グレーゾーン検出の精度向上 (個人差吸収) + 朝の家族向け 1 通サマリー。

| ファイル | 操作 |
|---|---|
| `services/sentinel/src/schedule_learner.py` (新規) | 本体 `schedule_learner.py` から HA/biometric 依存部抽出 (lite は biometric profile 必須) |
| `services/sentinel/src/gray_zone.py` | `behavior_deviation` を schedule_learner ベースに書き換え (現状はハードコード閾値) |
| `services/sentinel/src/daily_summary.py` (新規) | DAILY_SUMMARY_TIME に 1 call の heavy LLM 呼び出し (現状は rule-only summary のみ) |
| `services/sentinel/src/main.py` | daily summary を別 cron task として登録、escalation budget とは別計上 |
| `services/sentinel/src/db.py` | `daily_summaries` テーブル追加 (生成済み summary を 30 日保持) |
| `env.lite.example` | `DAILY_SUMMARY_LLM_MODEL` (heavy 用、cheap 用と分離) |

**ROI**: 中-高 (家族の "毎朝チェック" 体験が変わる)

---

### B4: 環境異常 + 緊急ニュース連携

**目標**: 設置地域の災害・天候異常も sentinel 経由で家族に通知。

| ファイル | 操作 |
|---|---|
| `infra/docker-compose.lite.yml` | weather-bridge / news-bridge を新 profile (`weather`, `news`) として追加 |
| `services/sentinel/src/rules.py` | 新ルール `weather_alert` (heat stroke risk: 室温×湿度), `urgent_news` (緊急地震速報) |
| `services/sentinel/src/state.py` | `WeatherData`, `NewsState` 追加 |

**ROI**: 中 (高齢者の熱中症は実際に多い)

---

### B5: Alpine + 配布スクリプト + ドキュメント

**目標**: 設置ハードルを下げる。

| ファイル | 操作 |
|---|---|
| `services/sentinel/Dockerfile.alpine` (新規) | Alpine ベース、glibc 依存 deps を確認 (paho-mqtt は OK、httpx は要 musl-cryptography) |
| `services/notifier/Dockerfile.alpine` (新規) | Alpine ベース |
| `infra/base/Dockerfile.alpine` (新規) | `python:3.11-alpine` ベースの hems-base-alpine:py3.11 |
| `infra/docker-compose.lite-alpine.yml` (新規) | alpine 版を選択する compose override |
| `scripts/install-lite.sh` (新規) | Pi に curl|sh で実行できる ワンライナー setup (Docker install → clone → bootstrap → notification provider 対話セットアップ) |
| `docs/lite/README.md` | Alpine option, schedule learner, daily summary, install script を追記 |
| `docs/lite/INSTALL_PI.md` (新規) | Pi 4 / Pi 5 専用設置ガイド (SD imager 推奨設定込み) |

**ROI**: 中 (試用ハードル激減 = 採用率に効く)

---

## 5. ビルド / CI 戦略

### Build dependency

lite ブランチは hems-base 採用後、以下のシーケンス:
```bash
docker compose -f docker-compose.lite.yml --profile bootstrap build base
docker compose -f docker-compose.lite.yml up -d --build
```

### Makefile 追加 target

```make
docker-build-lite: docker-base
    @for svc in sentinel notifier; do \
        docker build -t hems-$$svc:dev services/$$svc; \
    done
```

### CI matrix 拡張

`.github/workflows/ci.yml` の docker-build matrix に sentinel/notifier 追加 (lite ブランチに対しては別 workflow か、main 統合時に有効化する `if: contains('main', 'lite')`)。

---

## 6. 重要な意思決定ポイント (実装前にユーザー確認)

| ID | 質問 | 推奨デフォルト |
|---|---|---|
| Q1 | lite を main に rebase すべきか / 独立保持すべきか? | **独立 (`lite` ブランチをそのまま継続)。** main マージは lite-refine を主体的にメンテする予定がある時のみ。 |
| Q2 | World Model 共有化 (G9) を実施するか? | **しない。** 二重実装の負債は受容、lite OccupantState の単純さを保つ。 |
| Q3 | sentinel に hems-base を入れるか / lite 専用 lite-base を作るか? | **hems-base を流用。** 共通 deps (paho-mqtt/aiohttp/httpx etc.) は重複していて lite 専用 base のメリット薄い。 |
| Q4 | Mobile Companion 通知 (G6/B2-b) を notifier provider に統合 / 別 service として分離? | **provider に統合。** notifier はそもそも multi-channel dispatcher なので適合。 |
| Q5 | Daily summary (B3) を「家族へ毎朝送る」「異常時のみ送る」「サイレントログのみ」のどれにするか? | **異常時 + 週次の "今週も無事でした" レポート。** 毎朝送ると通知疲労 → 無視されるリスク。 |
| Q6 | Alpine 化 (B5/N1) の優先度は? | **後回し。** Pi 4/5 は今や 8GB RAM が標準で 173MB → 80MB のメリットが薄い。Pi Zero 2 W ターゲットなら必須。 |
| Q7 | sentinel テスト 38 件は今でも green か? | **B0 で確認。** 2 ヶ月放置で deps drift があると地味に落ちる可能性 (pip-audit で確認)。 |

---

## 7. 推奨着手順序とラフタイムライン

| Wave | 想定工数 | 期待 outcome |
|---|---|---|
| B0 | 1-2 時間 | worktree 環境 + ベースラインテスト pass 確認 |
| B1 | 半日 | セキュリティ硬化 + ビルド時間 30 秒 → 5 秒 |
| B2-a (Sunrise) | 半日 | Zigbee bedside ライト段階点灯 (要 HA 連携設置) |
| B2-b (Mobile Companion) | 半日 | LINE 不要化、家族 Android アプリへ通知 |
| B3 (Schedule + Daily) | 1 日 | グレーゾーン精度UP + 家族向け朝サマリー |
| B4 (Weather + News) | 半日 | 熱中症リスク・緊急地震速報を通知化 |
| B5 (Alpine + Install) | 1-1.5 日 | Pi へのワンライナー設置、配布準備完了 |
| **Total** | **3.5-4.5 日** | |

最小有効サブセット (1 日で済ませたいとき): **B0 → B1 → B2-b** のみで「セキュア + Mobile Companion 通知の lite」が完成。

---

## 8. リスク / 既知の地雷

- **lite と本体の deps version drift**: 2 ヶ月で fastapi / pydantic 等の minor version が動いている → B1 で hems-base 化した瞬間に lite 内コードが互換性で詰まる可能性。テストカバー確認必須。
- **MQTT bridge の auth**: lite ↔ 本体 HEMS の MQTT bridge (`bridge.conf.example`) は本体側の hardening 後 ACL を考慮して書き換える必要あり。本体側 acl.txt に `hems-lite-bridge` user を追加。
- **escalation budget の永続化**: 現状 in-memory → 子機再起動で reset される。Pi はアップデートで頻繁に再起動するので **B1 のついでに** SQLite に persist しないと予算超過事故が起きる (G2 にも追加するか別チケット)。
- **Mobile Companion の HMAC schema 変更**: 本体と並行進化させる必要。`docs/lite/MOBILE_CONTRACT.md` で固定化 (B2-b 内で作成)。
- **Sunrise alarm の Zigbee bedside ライト未存在**: `lite` 設置先が Zigbee 環境を持たない場合、B2-a は no-op。設置時の事前ヒアリングシート化を B5 のドキュメントで対応。

---

## 9. 完了の定義 (Definition of Done)

各 Wave の DoD:

- [ ] B1: lite branch で `docker compose -f docker-compose.lite.yml up -d --build` が anonymous なしで起動、`mosquitto_sub -u hems-lite-sentinel` で sentinel topic を購読できる。
- [ ] B2-a: 模擬 wake_up イベントから Zigbee `set_brightness` ramping コマンドが MQTT に publish されることを sniff で確認。
- [ ] B2-b: `mosquitto_pub -t hems/lite/test_alert -m '{...}'` から Mobile Companion app に push が届く。
- [ ] B3: 21 日のダミーデータで schedule_learner が起床時間 baseline を学習、+90 分逸脱で `behavior_deviation` 発火。
- [ ] B4: 室温 32°C + 湿度 75% で `heat_stroke_risk` ルール発火、緊急地震速報 mock で urgent news rule 発火。
- [ ] B5: `curl https://raw.githubusercontent.com/.../scripts/install-lite.sh | sh` で fresh Pi に sentinel + notifier が立ち上がる。

---

## 10. このプランファイルのライフサイクル

- 作成: 2026-05-04 (B0 着手前)
- 更新トリガ: 各 Wave 完了時、Q1-Q7 の決定が確定した時
- 廃棄: B5 完了 + lite 0.2 リリースタグを切った時 (`docs/lite/CHANGELOG.md` へ統合)

---

> **次のアクション**: `lite` ブランチに切り替えて B0 を実施するタイミングが来たら、本ファイルを Q1-Q7 の決定で更新してから着手する。
