# HEMS Documentation Index

ドキュメントグラフの**展開版**。グラフのルート(簡潔な地図)は [`../CLAUDE.md`](../CLAUDE.md) の **Documentation Map** 節。本ファイルは全 doc を Tier 別に一覧する。

各事実は **1 つの canonical home** を持つ。CLAUDE.md は概要 + ポインタのみで、詳細は下記の所有ドキュメントを参照する。

> 新規にサービス/ツール/トピックを追加するときの更新順:
> **IMPLEMENTATION_MAP → 該当 canonical doc(CLAUDE-bridges or services/\*/CLAUDE.md)→ CLAUDE.md の表 → この docs/README.md**

## Contributor Verification Notes

- 広域 pytest (`tests/ services/brain/tests/`) は過去に async SQLite 周辺で環境依存の hang が発生した履歴がある。証跡として使う場合は、実行環境、timeout、完全な command、結果を記録する。
- release 判定の canonical gate は通常環境での `make lint` と full non-integration pytest:
  `PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"`。
- filesystem audit や review-boundary 棚卸しの前は `make clean` を実行し、ignored/generated な `__pycache__/` などのノイズを落とす。

---

## Tier 0 — 常時 auto-load(オリエンテーション・ハブ)

| Doc | 役割 |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | プロジェクト全体の入口。Documentation Map / build & run / architecture 概要 / ports 表 / SoT ポインタ |
| [`../README.md`](../README.md) | ユーザー向け紹介(機能・クイックスタート・tech stack) |

## Tier 1 — service ディレクトリで auto-load(サービス固有 canonical)

| Doc | 所有スコープ |
|---|---|
| [`../services/brain/CLAUDE.md`](../services/brain/CLAUDE.md) | Brain Service(ReAct ループ・subsystem 一覧・brain tools・Chat brain server・Event Automation) |
| [`../services/voice/CLAUDE.md`](../services/voice/CLAUDE.md) | Voice I/O(plugin TTS / STT) |
| [`../services/perception/CLAUDE.md`](../services/perception/CLAUDE.md) | Perception(YOLOv11s-pose・VLM scene 分析) |
| [`../services/backend/CLAUDE.md`](../services/backend/CLAUDE.md) | 横断: Device Registry CRUD・Shopping List・Chat REST router |

補助(設計メモ、in-dir):
[`../services/brain/TASK_REMINDER.md`](../services/brain/TASK_REMINDER.md)(task queue/reminder)・
[`../services/voice/README.md`](../services/voice/README.md)(**stale** — VOICEVOX 固定設計の旧ドキュメント。現在は `services/voice/CLAUDE.md` と `env.example` を参照)・
[`../services/voice/CONTEXT_AWARE_COMPLETION.md`](../services/voice/CONTEXT_AWARE_COMPLETION.md)(dual voice 設計)・
[`../services/data-bridge/README.md`](../services/data-bridge/README.md)(**placeholder** — Phase-2 Strava/Fitbit/Garmin intake、compose 未登録)

## Tier 2 — on-demand 横断リファレンス(agent 向け)

| Doc | 役割 |
|---|---|
| [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) | **SoT**。code/compose/MQTT(§4 トピックツリー)/world model/tools/env の正確なマッピング + verification コマンド |
| [`CLAUDE-bridges.md`](CLAUDE-bridges.md) | 11 ブリッジ統合の canonical(OpenClaw/GAS/Obsidian/HA/biometric/Tapo/Zigbee/SwitchBot/weather/news/knowledge) |
| [`wiring-gap-06-data-flow-consolidation.md`](wiring-gap-06-data-flow-consolidation.md) | 2026-05-03 データ流統合計画。大半は 2026-06-11 リファクタで実装済み。未実装項目は `feature-proposals-2026-06-11.md` へ |

## Tier 3 — 人間向け setup / 運用ガイド

| Doc | 内容 |
|---|---|
| [`SMART_HOME_SETUP.md`](SMART_HOME_SETUP.md) | HA / SwitchBot / Nature Remo セットアップ・automation・LLM tools・IKEA Zigbee ペアリング |
| [`smart-home-device-guide.md`](smart-home-device-guide.md) | デバイス選定・互換性・配置・ネットワーク(SMART_HOME_SETUP の購入編) |
| [`smartband-setup.md`](smartband-setup.md) | biometric(Xiaomi/Amazfit/CMF)Gadgetbridge webhook 設定 |
| [`avatar-setup.md`](avatar-setup.md) | VRM 3D avatar・character YAML・animation |
| [`voisona-talk-setup.md`](voisona-talk-setup.md) | VoiSona Talk TTS(host app)設定 |
| [`event-automation.md`](event-automation.md) | event→action 配線(wake_up/arrival/departure/scheduled) |
| [`ha-isolation.md`](ha-isolation.md) | HA ネットワーク隔離(reverse proxy) |
| [`shopping-list.md`](shopping-list.md) | shopping list 運用 |
| [`sensor-purchasing-guide-jp.md`](sensor-purchasing-guide-jp.md) | センサー調達(国内) |
| [`sensor-purchasing-guide-aliexpress.md`](sensor-purchasing-guide-aliexpress.md) | センサー調達(AliExpress) |

## Tier 4 — 計画 / 監査 / 履歴

| Doc | 状態 |
|---|---|
| [`refactor/2026-06-11/PLAN.md`](refactor/2026-06-11/PLAN.md) | **completed** — 2026-06-11 リファクタ計画(W1–W5)。全 row は `LEDGER.md` で完了宣言 |
| [`refactor/2026-06-11/LEDGER.md`](refactor/2026-06-11/LEDGER.md) | **completed** — PLAN.md 2026-06-11 の実装進捗台帳。全 row done |
| [`refactor/2026-06-11/RECOMMENDED_FOLLOW_UPS.md`](refactor/2026-06-11/RECOMMENDED_FOLLOW_UPS.md) | **completed** — 実装後の品質向上・検証作業リスト。全項完了 |
| [`feature-proposals-2026-06-11.md`](feature-proposals-2026-06-11.md) | **active** — 監査由来の機能提案 12 件(未活用データの機能化・即時トリガ・新データソース・運用)。各提案に前提 Wave と工数を付記 |
| [`audit/2026-06-11/SUMMARY.md`](audit/2026-06-11/SUMMARY.md) | **active** — 最新の技術的負債・セキュリティ統合監査(誤検知の棄却記録含む) |
| [`distribution.md`](distribution.md) | **active** — 配布/オンボーディング Phase 計画。`make quickstart` / PostgreSQL 既定化 / env 既定値統一は実装済み |
| [`db-improvement-plan.md`](db-improvement-plan.md) | active(SQLite WAL / retention / schema gaps / index / DDL split) |
| [`morning-briefing-refactor-plan.md`](morning-briefing-refactor-plan.md) | **historical** — Waves 1-3 完了。後続は gap-06 / feature-proposals-2026-06-11 へ |
| [`hardening-audit-2026-04.md`](hardening-audit-2026-04.md) | **historical / superseded** — P0/P1 は 2026-06-11 W1 で実装済。未対応 P2/P3 は feature-proposals 等に移管要 |
| [`../SECURITY_AUDIT.md`](../SECURITY_AUDIT.md) | **historical** — security 監査(2026-03-07、構成変更で一部陳腐化。hardening-audit-2026-04 / audit/2026-06-11 が後継) |
| [`audit-jisei-roku-2026-05-16.md`](audit-jisei-roku-2026-05-16.md) | 監査メモ(5/16) |
| [`technical-debt-audit-2026-05-24.md`](technical-debt-audit-2026-05-24.md) → [`technical-debt-refactoring-plan-2026-05-24.md`](technical-debt-refactoring-plan-2026-05-24.md) → [`technical-debt-followups-2026-05-25.md`](technical-debt-followups-2026-05-25.md) | **completed** — 5/24-25 負債監査 → 計画 → followup。followup P1-P3 は全解決済(2026-06-11 監査で確認) |
| [`audit/2026-05-25/`](audit/2026-05-25/README.md) | **historical / superseded** — サービス単位実装監査。後継: `audit/2026-06-11/SUMMARY.md` |
| [`refactor/2026-05-25/LEDGER.md`](refactor/2026-05-25/LEDGER.md) | **historical / completed** — R0-R8 リファクタ台帳。deferred 9 行は refactor/2026-06-11 W2 へ移管済み |
| [`lite/refinement-plan.md`](lite/refinement-plan.md) | **historical** — lite ブランチ(2026-03-05 凍結)精査計画。再開時の復旧ガイド |
| [`../CHANGELOG.md`](../CHANGELOG.md) | breaking change / migration / deprecation |
| `wiring-gap-0{1,2,3,4,5}-*.md` | **CLOSED (2026-05-03)** — gap-06 に統合済。履歴参照用 |
| `pitch-slides.md` / `pitch-deck.md` / `pitch-gamma-prompt.md` / `pitch-notebooklm.txt` / `pitch-slides.pdf` / `pitch-diagrams*.mmd` | **historical** — pitch 資料(運用対象外) |
