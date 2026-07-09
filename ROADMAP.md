# hems ロードマップ

> 本ドキュメントは [`../ROADMAP.md`](../ROADMAP.md)（上位ロードマップ）の下位計画です。
>
> 目的: 個人・単身者向けのパーソナル AI ホームアシスタントとして、環境センサー・生体情報・スマートデバイス・PC/サービス監視・スケジュールから意思決定を補助・自動化するための充足・不足を整理し、改善ロードマップを示す。

---

## 1. 現状サマリー

| 項目 | 内容 |
|---|---|
| **ドメイン** | パーソナルホーム AI アシスタント |
| **成熟度** | 開発中〜高度なプロトタイプ |
| **主要な充足点** | 豊富なセンサー/API/画像/生体データ、ReAct + Rule + AutomationEngine、ScheduleLearner/AckLearner/RulePromoter、VRM アバター、CI/CD、多数のブリッジ群 |
| **主要な不足点** | `require_confirm` 未実装、data-bridge 空、モバイル Android 未完了、未活用データフロー多数、セキュリティ未対応（無認証・平文）、ドリフト検知・自動再学習不足 |

---

## 2. 4 軸評価

| 軸 | スコア | コメント |
|---|---|---|
| 情報源の充実度 | 4/5 | 環境/生体/PC/スマホ/スマートデバイス/天気/ニュース/知識と非常に豊富。data-bridge 空が欠損 |
| 意思決定ループ完成度 | 3/5 | 生活リズムループは閉じている。HITL（`require_confirm`）・ロールバック・学習自動反映が不足 |
| シミュレータ・デジタルツイン活用度 | 2/5 | mock LLM / virtual edge は開発用。物理モデル/what-if シミュレータなし |
| 共通化・統合余地 | 3/5 | SOMS 系と重複多し。`business-ops` の audit/consent/RBAC、SOMS の anomaly/inventory 等を流用可能 |

---

## 3. 重点課題と優先アクション

### 短期（1〜2 ヶ月）

- `services/data-bridge/` を実装し、Strava/Fitbit/Garmin/Intervals.icu 等の生体・運動データ取込を開始する
- `services/mobile-android/` と `apps/healthconnect-companion/` の完成を進め、QR 登録 API とのアプリ連携を完了させる
- `services/backend/models.py` の `Device` モデルに不足している `link_quality` / `last_seen_reported` 列の Alembic migration を生成する
- `business-ops` の `comms-bridge` または `auto_JA` の `notification_router` を流用し、Discord/Slack/Email 通知チャネルを追加する

### 中期（3〜6 ヶ月）

- `AutomationRule.require_confirm` フィールドを `AutomationEngine` で参照し、重大自動アクション前の HITL 承認を実装する
- `soms` / `business-ops` の `anomaly` サービスを導入し、時系列異常検知を追加する
- `pose-work/packages/perception_kit/anonymizer.py` を流用し、カメラ証拠の匿名化を強化する
- `services/brain/src/world_model/sensor_validation.py` の範囲検証に加え、統計的外れ値除去・長期ドリフト監視を実装する

### 長期（6 ヶ月〜）

- 室内環境の熱力学/CO₂ 拡散/在室行動モデル等の物理ベースデジタルツインを構築する
- 承認/棄却/完了/weather alert/notes/knowledge/shopping purchased 等の未活用データフローを rule/context/学習に統合する
- 閾値・ルール・プロンプトを実行結果から自動更新する学習ループを構築する

---

## 4. 関連ドキュメント・ファイル

- 上位ロードマップ: [`../ROADMAP.md`](../ROADMAP.md)
- 全体像: `README.md`, `CLAUDE.md`, `docs/IMPLEMENTATION_MAP.md`
- 大規模リファクタ監査: `docs/audit/2026-06-11/SUMMARY.md`
- 配布計画: `docs/distribution.md`
- 未活用データフロー: `docs/wiring-gap-06-data-flow-consolidation.md`, `docs/feature-proposals-2026-06-11.md`
- セキュリティ監査: `docs/hardening-audit-2026-04.md`
- Brain コア: `services/brain/src/main.py`, `services/brain/src/brain_cognitive.py`, `services/brain/src/automation_engine.py`, `services/brain/src/rule_engine.py`
- WorldModel: `services/brain/src/world_model/world_model.py`, `services/brain/src/world_model/sensor_fusion.py`, `services/brain/src/world_model/sensor_validation.py`
