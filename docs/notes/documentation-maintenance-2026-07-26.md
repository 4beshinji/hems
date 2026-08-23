# Documentation cleanup / maintenance memo — 2026-07-26

> **スナップショット**: 2026-07-26。これは棚卸しと後続作業のメモであり、文書の移動・削除、コード変更、コミットはこの時点では行わない。

## 1. 棚卸しの範囲と結論

作業開始時点の調査済み基線（Markdown 系 130 件 / 28,083 行、文書資産 136 件 / 2.62 MiB）を起点に、`docs/README.md` の索引、各ディレクトリの実体、文書冒頭の status / historical notice、相互リンクを突合した。

- 変更前の `docs/README.md` のローカル Markdown リンク **49/49 は実在**した。今回メモへのリンクを 1 件追加した後も **50/50** が実在し、リンク切れはない。
- Tier 4 は計画・監査・履歴を同じ階層に置く設計で、明示された status は概ね実体と一致する。ただし「全 doc を一覧する」という目的に対して、最近追加された計画ディレクトリと研究資産は個別発見性が不足している。
- 索引に個別行がない主な実体は、`audit/2026-05-30-review/`、`refactor/2026-07-19-branch-integration/`、`notes/upstream-port-plan.md`、`refactor/2026-07-18/` の design note、`research/closed-loop-assets/` の Phase 2–5 と補助ノートである。これはリンク切れではなく、索引粒度と実体の差分である。
- `audit/2026-05-30-review/LEDGER.md` は全 30 セッションが `todo` の計画台帳であり、実行済み監査と誤認しない。`refactor/2026-07-19-branch-integration/LEDGER.md` は統合済みの履歴記録である。

## 2. 維持する現行 SoT

| スコープ | 現行 SoT | 維持方針 |
|---|---|---|
| プロジェクト入口 / 文書グラフ | [`../../CLAUDE.md`](../../CLAUDE.md)、[`../README.md`](../README.md) | 概要とポインタに限定し、詳細を重複記載しない |
| code ↔ compose ↔ MQTT ↔ tools ↔ env | [`../IMPLEMENTATION_MAP.md`](../IMPLEMENTATION_MAP.md) | 実装・トピック・環境変数を変更したら最初に同期する |
| ブリッジ統合 | [`../CLAUDE-bridges.md`](../CLAUDE-bridges.md) | 11 ブリッジの canonical 名、topic、認証、設定を所有する |
| サービス内部 | [`../../services/brain/CLAUDE.md`](../../services/brain/CLAUDE.md)、[`../../services/backend/CLAUDE.md`](../../services/backend/CLAUDE.md)、[`../../services/voice/CLAUDE.md`](../../services/voice/CLAUDE.md)、[`../../services/perception/CLAUDE.md`](../../services/perception/CLAUDE.md) | サービスの責務・API・運用手順は各 service doc に置く |
| Backend 永続化 / migration | `services/backend/migrations/versions/`（詳細は Implementation Map §2.3） | runtime DDL や計画文書を SoT とみなさない |
| Device Registry | Backend `models.Device` = 永続 SoT、Brain registry = TTL 付き runtime cache | 二層を統合せず、境界を変えた時だけ両方の canonical doc を更新する |
| setup / 運用 | `docs/SMART_HOME_SETUP.md`、`docs/event-automation.md`、各 Tier 3 guide | 実際の compose / env / API と検証してから更新する |
| 現行の修正計画 | [`../audit/2026-07-18/README.md`](../audit/2026-07-18/README.md)、[`../refactor/2026-07-18/PLAN.md`](../refactor/2026-07-18/PLAN.md) と LEDGER | P0/P1 の進行中記録。完了判定を過去計画から推測しない |

`wiring-gap-06-data-flow-consolidation.md` と `feature-proposals-2026-06-11.md` はロードマップ / 提案であり、実装仕様の SoT ではない。`research/closed-loop-assets/` も同様に研究・将来計画として保持し、未実装の設計を現行機能として説明しない。

## 3. 後続の archive 移行候補

移動先ディレクトリの作成や移動自体は別作業で行う。以下は status と inbound link を確認した後に、優先度順に候補化する。

### P0 — 明確に履歴化された資料（発見性の改善効果が大きい）

- `wiring-gap-01`〜`wiring-gap-05` — `CLOSED (2026-05-03)`、内容は gap-06 に統合済み。
- `docs/audit/2026-05-25/` と `docs/audit/2026-06-11/SUMMARY.md` — 後続監査で再検証済みの snapshot。後者は Android / mobile 境界の未完事項を含むため、移行前に後継リンクを明記する。
- `docs/refactor/2026-05-25/` と `docs/refactor/2026-06-11/` の完了台帳・設計ノート — server-side scope の完了記録。2026-07-18 の監査・計画が現行の follow-up であることを残す。
- `hardening-audit-2026-04.md`、`SECURITY_AUDIT.md`、`morning-briefing-refactor-plan.md`、`technical-debt-*.md`、`lite/refinement-plan.md` — 各ファイルに historical / superseded notice があり、内容を書き換えず保存する。
- pitch 資料（`pitch-*.md`、`pitch-*.txt`、`pitch-*.pdf`、`pitch-diagrams*.mmd`） — 運用対象外の説明資料。

### P1 — 完了記録だが、移行前に status を確定する資料

- `refactor/2026-07-19-branch-integration/` — main への統合と検証は完了。統合の再現性・監査証跡として保持し、現行仕様へのリンクを切り替えてから archive 化する。
- `notes/upstream-port-plan.md` — 冒頭に historical notice がある。旧 upstream 作業の進捗記録であり、本文中の「multi-session work の SoT」という表現を現行 SoT と混同しないよう、移行時に案内リンクを残す。
- `audit/2026-05-30-review/` — 台帳は未着手 (`todo`) の計画。実行を再開しないなら「未実行の計画」として保存し、実行するなら active audit として索引・台帳を先に同期する。

### P2 — archive に急いで移さない資料

- `research/closed-loop-assets/` の Phase 0〜5 と補助研究ノート — 将来提案として利用価値があるため `research/` に保持する。実装済みと読める status が付いた行だけを、実装状況確認後に addendum で明確化する。
- `docs/db-improvement-plan.md`、`docs/distribution.md`、`docs/feature-proposals-2026-06-11.md`、`docs/lite/README.md` — active または運用計画として現行参照があり、archive 対象ではない。

## 4. リンク更新と保存方針

1. このメモへのポインタを Tier 4 に追加する（今回実施）。既存の歴史資料の本文は機械的に書き換えない。
2. archive 移行を行う時は、先に `rg -n '対象ファイル名|旧相対パス' --glob '*.md' .` で inbound link、CLAUDE / plan / ledger / script 参照を洗い出す。
3. 移動は `git mv` で履歴を保持し、`docs/archive/README.md` 相当のカタログに旧 status、日付、後継 SoT、移行理由を記録する。移行先が決まるまで重複コピーや削除を行わない。
4. 参照元を新パスへ更新し、元の status notice は原則そのまま残す。旧パスを外部利用している可能性がある場合は、redirect / stub の要否を個別判断する。
5. active docs では canonical 名（例: OpenClaw と legacy `localcraw`）を維持し、歴史資料の旧名称を現行仕様へ一括置換しない。

索引の次回更新では、`audit/2026-05-30-review/`、`refactor/2026-07-19-branch-integration/`、`notes/upstream-port-plan.md` を Tier 4 の status 付き行として追加し、research 資産はディレクトリ単位で「提案 / 非 SoT」と明記する。

## 5. 優先度付き検証チェックリスト

### P0 — 参照破壊を防ぐ

- [x] 変更前の `docs/README.md` のローカルリンク 49 件を実体と照合（49/49 OK）。メモ追加後は 50/50 OK。
- [ ] archive 対象ごとに inbound link を `rg` で列挙し、移動前後で差分がないことを確認する。
- [ ] 新旧索引、`CLAUDE.md`、`IMPLEMENTATION_MAP.md`、service CLAUDE の相対リンクを再検査する。

### P1 — 現行仕様との乖離を防ぐ

- [ ] `make clean` 後に `services/` / `infra/docker-compose*.yml` / `env.example` と Implementation Map のサービス・env・topic 表を突合する。
- [ ] 2026-07-18 audit / refactor の P0/P1 が完了した時は、該当 ledger と `docs/README.md` の status を同じ変更で更新する。
- [ ] Android / biometric の end-to-end 状態は 2026-07-18 の報告を優先し、2026-06-11 の「全 row 完了」を範囲外まで拡張して解釈しない。
- [x] ドキュメント変更後に `git diff --check` と `git status --short` を実行し、意図しない generated file がないことを確認した。

### P2 — リリース / 定期メンテナンス

- [x] docs-only 変更でも `make lint` を実行した（ruff check / format check とも PASS）。広域 pytest を証跡にする場合は、`docs/README.md` 記載の timeout 付き canonical command、環境、結果を記録する。
- [ ] 月次で索引と filesystem の差分（新規 directory、status notice のない計画、リンク切れ）を棚卸しする。
- [ ] 移行後は archive カタログから現行 SoT へ辿れること、historical 文書が運用手順として誤読されないことをレビューする。
