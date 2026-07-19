# 再実装ブランチ統合計画 — 2026-07-19

## 背景

`main` から分岐した 6 本のリモートブランチと 1 本のローカルバックアップブランチを調査した結果、以下の状況が判明した。

- **4 本**は内容が `main` に再実装済み（重複ブランチ）
- **1 本**（`origin/docs/audit-2026-05-30-review-plan`）には RTMO perception 変更と 2026-05-30 レビュー計画が未統合
- **1 本**（`origin/lite`）には `notifier`/`sentinel` サービス群が未統合
- **ローカル backup** は `main` に完全マージ済み

本計画は、重複ブランチを廃棄しつつ、未統合の価値ある変更を `main` へ取り込む手順を定める。

## 目的

1. 再実装済みの陳腐ブランチを削除し、リポジトリの散らばりを解消する。
2. RTMO perception 変更と 2026-05-30 レビュー計画を `main` に統合する。
3. `lite` サービス群（`notifier` / `sentinel`）を `main` 上で新規ブランチとして再構成する。
4. すべての統合で `make lint` / `make test-quick` ゲートを維持する。

## ブランチ分類

| ブランチ | 最終コミット日 | main との差分 | 推奨アクション | 根拠 |
|---|---|---|---|---|
| `origin/refactor/upstream-port` | 2026-05-25 | ahead 212 / behind 239 | **削除** | 2026-05-25 リファクタ・監査の実施ブランチ。R0–R8 / BACKEND_API_KEY 配線等は `main` に別コミットで実装済み |
| `origin/refactor/brain-dedup` | 2026-04-17 | ahead 82 / behind 239 | **削除** | frontend ダッシュボード/Android 等の内容は `main` で再実装済み。独自ファイルは obsolete か old integration tests |
| `origin/hardening/p0-impl` | 2026-05-20 | ahead 108 / behind 239 | **削除** | P0 hardening / CLAUDE.md 再構成等は `main` に実装済み |
| `origin/feat/distribution` | 2026-05-25 | ahead 3 / behind 134 | **削除** | 2026-05-25 監査・配布ロードマップは `main` に統合・更新済み |
| `origin/docs/audit-2026-05-30-review-plan` | 2026-06-09 | ahead 5 / behind 134 | **cherry-pick 2 commits** | RTMO perception 変更（AGPL-3.0 YOLOv11 回避）と 2026-05-30 レビュー計画が未統合 |
| `origin/lite` | 2026-03-05 | ahead 2 / behind 206 | **main から新規 feature branch へ再移植** | `notifier` / `sentinel` / lite compose が未統合。ブランチ自体は 206 commits 遅れで rebase 不可 |
| `backup/hems-local-20260628` | 2026-06-12 | 0 / merged | **削除** | `main` に完全マージ済み |

## Phase 1 — RTMO perception 統合

### 対象ブランチ
`origin/docs/audit-2026-05-30-review-plan`

### 取り込むコミット

| ハッシュ | サブジェクト | 種別 | 理由 |
|---|---|---|---|
| `e3845d76` | `docs(audit): 2026-05-30 de-bloat レビュー計画 30 セッション` | Doc | `main` にないレビュー計画ディレクトリを追加 |
| `e0ef833a` | `feat: perception updates (activity/vlm/detector) + NOTICE/tests` | Code | YOLOv11 → RTMO 置き換え、NOTICE、テスト追加 |

### 手順

1. `main` から統合ブランチを作成
   ```bash
   git checkout main
   git pull origin main
   git checkout -b integrate/rtmo-perception
   ```
2. 2 コミットを cherry-pick
   ```bash
   git cherry-pick e3845d76
   git cherry-pick e0ef833a
   ```
3. コンフリクトが発生する場合は以下を優先する
   - `services/perception/requirements.txt`: `main` のレイアウトを維持しつつ、`ultralytics` を削除し `onnxruntime` / `tqdm` を追加する
   - `env.example`: ブランチ版を丸ごと採用しない。追加が必要な変数のみ手動で追記する
   - `pyproject.toml`: `services/perception/tests` を `testpaths` に追加する（すでに含まれていればそのまま）
4. 変更を確認
   ```bash
   git diff --stat main
   git diff main -- services/perception/requirements.txt env.example
   ```

### 取り込むファイル

- `docs/audit/2026-05-30-review/` (README.md, LEDGER.md, REVIEW_PLAN.md, notes/.gitkeep)
- `docs/audit/README.md`（存在しなければ）
- `services/perception/NOTICE`
- `services/perception/src/detector.py`
- `services/perception/src/activity_tracker.py`
- `services/perception/src/vlm_scheduler.py`
- `services/perception/src/main.py`
- `services/perception/src/config.py`
- `services/perception/Dockerfile`
- `services/perception/tests/test_detector.py`
- `services/perception/CLAUDE.md`（必要に応じて）

### 検証ゲート

```bash
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common .venv/bin/python -m pytest \
  services/perception/tests tests/test_perception.py tests/test_vlm.py \
  -v --tb=short
```

## Phase 2 — lite サービス群の再移植

### 対象ブランチ
`origin/lite`

### 方針
ブランチは `main` から 206 commits 遅れているため、rebase/merge は現実的でない。`main` から新規 feature branch を作成し、必要なファイルだけを移植する。

### 移植するファイル

```
services/notifier/
  Dockerfile
  requirements.txt
  src/main.py
  src/providers/__init__.py
  src/providers/base.py
  src/providers/discord.py
  src/providers/line.py
  src/providers/ntfy.py
  src/providers/slack.py

services/sentinel/
  Dockerfile
  requirements.txt
  src/config.py
  src/db.py
  src/escalation.py
  src/gray_zone.py
  src/main.py
  src/rules.py
  src/state.py

docs/lite/README.md
env.lite.example
infra/docker-compose.lite.yml
infra/mosquitto/mosquitto-lite.conf
infra/mosquitto/bridge.conf.example
tests/lite/
```

### 移植しないファイル

- `config/characters/ene.yaml`（`main` では `ena.yaml` として統合済み）
- `services/backend/routers/points.py`、frontend の `XPPanel.tsx`（XP/points システムは `main` では削除）
- `services/openclaw-bridge/*`（OpenClaw は外部リポジトリ `../../localcraw` へ移行済み）
- `infra/tests/*`（古い e2e テスト。`main` の `tests/integration/` を優先）
- 古い frontend ページ（`physical/page.tsx` 等）

### 手順

1. `main` から新規 feature branch を作成
   ```bash
   git checkout main
   git checkout -b integrate/lite-services
   ```
2. `origin/lite` から上記「移植するファイル」のみを取得
   ```bash
   git checkout origin/lite -- services/notifier services/sentinel docs/lite env.lite.example \
     infra/docker-compose.lite.yml infra/mosquitto/mosquitto-lite.conf \
     infra/mosquitto/bridge.conf.example tests/lite
   ```
3. `services/notifier/src/main.py` / `services/sentinel/src/main.py` を `main` の `services/_common/hems_common/` パターン（`MqttPublisher`、`bridge_lifespan`、`verify_internal_token` 等）に合わせて調整する
4. 不要ファイルが混入していないか確認
   ```bash
   git status --short
   git diff --cached --name-only
   ```

### 検証ゲート

```bash
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common .venv/bin/python -m pytest \
  tests/lite/ -v --tb=short
# ビルド確認
DOCKER_BUILDKIT=1 docker build -t hems-notifier:dev services/notifier
DOCKER_BUILDKIT=1 docker build -t hems-sentinel:dev services/sentinel
# compose 構文確認
cd infra && docker compose -f docker-compose.lite.yml config
```

## Phase 3 — ブランチクリーンアップ

Phase 1 と Phase 2 が `main` へマージされてから実行する。

```bash
# ローカル
git branch -d backup/hems-local-20260628

# リモート
for b in refactor/upstream-port refactor/brain-dedup hardening/p0-impl feat/distribution \
         docs/audit-2026-05-30-review-plan lite; do
  git push origin --delete "$b"
done
```

## 統合順序

1. **Phase 1（RTMO perception）**を先に実施する。変更範囲が限定され、独立している。
2. **Phase 2（lite services）**は並行して準備可能だが、`main` へのマージは Phase 1 後でも問題ない。
3. **Phase 3（ブランチ削除）**は両方がマージ済みになってから行う。

## リスクと対策

| リスク | 対策 |
|---|---|
| RTMO cherry-pick で `requirements.txt` コンフリクト | `main` のレイアウトを維持し、RTMO 用の依存のみ追加 |
| `env.example` が古い branch 版で上書きされる | cherry-pick 後に `env.example` の diff を確認し、手動で必要な行のみ追加 |
| lite サービスが `hems_common` パターンに追従していない | 移植時に `MqttPublisher` / `bridge_lifespan` / `verify_internal_token` を適用 |
| 統合後に test count が落ちる | 各 Phase 完了後に `make test-quick` を実行し、baseline を下回らないことを確認 |
| ブランチ削除の誤り | 削除前に `main` 上で統合コミットが存在することを `git branch --contains` で確認 |

## ドキュメント同期チェックリスト

- [ ] `docs/audit/2026-05-30-review/` を追加後、`docs/audit/README.md` または `CLAUDE.md` の audit index からリンクする
- [ ] RTMO 変更に伴い `services/perception/CLAUDE.md` / `docs/IMPLEMENTATION_MAP.md` §perception を更新する
- [ ] lite サービス追加後、`docs/IMPLEMENTATION_MAP.md` §services / env カバレッジに `notifier` / `sentinel` を追加する
- [ ] `env.lite.example` の変数を `docs/IMPLEMENTATION_MAP.md` または `env.example` コメントに反映する（必要に応じて）
- [ ] 本計画の `LEDGER.md` に各 Phase の進捗を記録する

## ロールバック方針

- 各 Phase は独立ブランチで作業する。gate 失敗時はブランチを破棄し、原因を修正した上で新しいブランチからやり直す。
- `main` へのマージは fast-forward ではなくマージコミットを作成し、Phase 単位で revert 可能にする。

---

## 参照

- 調査レポート: 本計画と同ディレクトリの調査メモ（`analysis-notes.md` 等）または本計画の `LEDGER.md`
- 関連監査: `docs/audit/2026-07-18/README.md`
- 関連リファクタ: `docs/refactor/2026-07-18/PLAN.md`
