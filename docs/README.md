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
[`../services/voice/README.md`](../services/voice/README.md)(VOICEVOX 詳細)・
[`../services/voice/CONTEXT_AWARE_COMPLETION.md`](../services/voice/CONTEXT_AWARE_COMPLETION.md)(dual voice 設計)・
[`../services/data-bridge/README.md`](../services/data-bridge/README.md)(**placeholder** — Phase-2 Strava/Fitbit/Garmin intake、compose 未登録)

## Tier 2 — on-demand 横断リファレンス(agent 向け)

| Doc | 役割 |
|---|---|
| [`IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md) | **SoT**。code/compose/MQTT(§4 トピックツリー)/world model/tools/env の正確なマッピング + verification コマンド |
| [`CLAUDE-bridges.md`](CLAUDE-bridges.md) | 11 ブリッジ統合の canonical(OpenClaw/GAS/Obsidian/HA/biometric/Tapo/Zigbee/SwitchBot/weather/news/knowledge) |
| [`wiring-gap-06-data-flow-consolidation.md`](wiring-gap-06-data-flow-consolidation.md) | **active ロードマップ**。Wave 計画。gap-01..05 を統合・supersede |

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
| [`distribution.md`](distribution.md) | active — 配布/オンボーディング Phase 計画(GHCR publish・compose 配布化・quickstart・既定修復・wizard) |
| [`db-improvement-plan.md`](db-improvement-plan.md) | active(SQLite WAL / retention / schema gaps) |
| [`morning-briefing-refactor-plan.md`](morning-briefing-refactor-plan.md) | Waves 1-3 完了(gap-06 参照) |
| [`hardening-audit-2026-04.md`](hardening-audit-2026-04.md) | security hardening 監査 |
| [`../SECURITY_AUDIT.md`](../SECURITY_AUDIT.md) | security 監査(2026-03-07) |
| [`audit-jisei-roku-2026-05-16.md`](audit-jisei-roku-2026-05-16.md) | 監査メモ(5/16) |
| [`audit/2026-05-25/`](audit/2026-05-25/README.md) | サービス単位 実装監査(命名/スコープ/可読性 + doc 乖離是正、全 16 unit)。後続リファクタの起点 |
| [`lite/refinement-plan.md`](lite/refinement-plan.md) | lite 版精査計画 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | breaking change / migration / deprecation |
| `wiring-gap-0{1,2,3,4,5}-*.md` | **CLOSED (2026-05-03)** — gap-06 に統合済。履歴参照用 |
| `pitch-slides.md` / `pitch-deck.md` / `pitch-gamma-prompt.md` / `pitch-notebooklm.txt` / `pitch-slides.pdf` / `pitch-diagrams*.mmd` | **historical** — pitch 資料(運用対象外) |
