# 再実装ブランチ統合 LEDGER — 2026-07-19

本 LEDGER は [`PLAN.md`](PLAN.md) の進捗を追跡する。1 row = 1 統合作業単位。

| Phase | # | 作業内容 | 対象ブランチ/ファイル | 状態 | コミット | 検証結果 |
|---|---|---|---|---|---|---|
| 0 | 0 | ブランチ調査と統合計画立案 | `origin/*`, `backup/*` | Done | `PLAN.md` 作成 | — |
| 1 | 1 | RTMO perception 統合ブランチ作成 | `integrate/rtmo-perception` | Done | — | — |
| 1 | 2 | `e3845d76` cherry-pick（2026-05-30 review docs） | `docs/audit/2026-05-30-review/`, `docs/audit/README.md` | Done | `b309601` | — |
| 1 | 3 | `e0ef833a` cherry-pick（RTMO perception 変更） | `services/perception/*`, `pyproject.toml` | Done | `888122e` | — |
| 1 | 4 | `requirements.txt` / `env.example` 手動解決 | `services/perception/requirements.txt`, `env.example` | Done | — | branch 版を採用 |
| 1 | 5 | RTMO 統合の lint / test gate | perception tests | Done | — | `76 passed, 2 skipped` |
| 1 | 6 | `main` へマージ | `integrate/rtmo-perception` → `main` | Done | `54d5034` | — |
| 2 | 1 | lite サービス統合ブランチ作成 | `integrate/lite-services` | Done | — | — |
| 2 | 2 | notifier / sentinel / lite ファイルを `main` へ移植 | `services/notifier/`, `services/sentinel/`, `infra/docker-compose.lite.yml`, etc. | Done | `e4953d4` | sentinel モジュールを `sentinel.*` パッケージ化 |
| 2 | 3 | `hems_common` パターンへの適合調整 | `services/sentinel/src/main.py` | Done | `e4953d4` | `MqttPublisher` + canonical `hems/sensors/*` topics |
| 2 | 4 | lite サービスの lint / test / build gate | `tests/lite/`, Docker build, compose config | Done | — | `38 passed`; Docker build ×2 OK; compose config OK |
| 2 | 5 | `main` へマージ | `integrate/lite-services` → `main` | Done | `3f02308` | — |
| 3 | 1 | 重複ブランチ削除 | `origin/refactor/upstream-port`, `origin/refactor/brain-dedup`, `origin/hardening/p0-impl`, `origin/feat/distribution` | Done | — | `git push origin --delete ...` |
| 3 | 2 | 統合済みブランチ削除 | `origin/docs/audit-2026-05-30-review-plan`, `origin/lite` | Done | — | `git push origin --delete ...` |
| 3 | 3 | ローカル backup ブランチ削除 | `backup/hems-local-20260628` | Done | — | `git branch -D backup/hems-local-20260628` |
| 4 | 1 | ドキュメント同期 | `CLAUDE.md`, `IMPLEMENTATION_MAP.md`, `env.example`, 各 canonical doc | Done | — | commit `469885d` |
| 5 | 1 | `main` へ push | `origin/main` | Done | — | `git push origin main` (6 commits) |
| 6 | 1 | 現行 Core E2E harness / Make target | `infra/scripts/integration_test.py`, `Makefile` | Done | this commit | PostgreSQL + Mock LLM Core: 31/31 passed |
| 6 | 2 | merge 後 runtime / test isolation 不整合修正 | Backend migration、Brain startup/event store/task dedup、service module isolation | Done | this commit | PostgreSQL integration 2 passed、full gate 2426 passed / 3 skipped |
| 6 | 3 | Lite / Perception runtime E2E と Compose 同期 | `hems_common.mqtt`, Lite E2E、Perception Compose | Done | this commit | Lite 5/5 passed、Perception health `model_loaded=true` |

## ゲート結果記録欄

### Phase 1 gate

```bash
# 実行予定
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common .venv/bin/python -m pytest \
  services/perception/tests tests/test_perception.py tests/test_vlm.py \
  -v --tb=short
```

結果:

```
make lint: ruff check passed, ruff format --check passed
perception focused pytest: 76 passed, 2 skipped in 3.39s
```

全 test suite 実行時 (`tests/` + `services/brain/tests/`) は `2370 passed, 3 skipped, 48 deselected, 1 failed, 11 errors` となった。失敗/エラーは `tests/security/test_unauth_coverage.py::test_no_unprotected_dashboard_routes` と `services/biometric-bridge/src/main.py` モジュールの fixture 解決問題であり、RTMO perception 統合とは無関係な既存の pre-existing 問題と判断した。

### Phase 2 gate

```bash
# 実行予定
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common .venv/bin/python -m pytest \
  tests/lite/ -v --tb=short
DOCKER_BUILDKIT=1 docker build -t hems-notifier:dev services/notifier
DOCKER_BUILDKIT=1 docker build -t hems-sentinel:dev services/sentinel
cd infra && docker compose -f docker-compose.lite.yml config
```

結果:

```
make lint: ruff check passed, ruff format --check passed
tests/lite: 38 passed in 0.11s
Docker build: hems-notifier:dev, hems-sentinel:dev 成功
docker compose -f docker-compose.lite.yml config: OK
```

全 test suite 実行時は `2408 passed, 3 skipped, 48 deselected, 1 failed, 11 errors`。失敗/エラーは Phase 1 と同一の pre-existing 問題（security auth test + biometric bridge webhook fixtures）で、lite 統合による追加の失敗はなし。

### Phase 6 gate

2026-07-25 にマージ後の実コンテナ検証を実施した。次の統合時不整合を修正した。

- Alembic revision ID が PostgreSQL の `alembic_version.version_num VARCHAR(32)` を超えて fresh migration が失敗する。
- Brain が implicit detector の生成前に `AutomationEngine` へ参照を渡して起動失敗する。
- PostgreSQL event store が参照先 table より先に FK table を作り、文字列 timestamp を asyncpg へ渡す。
- Backend の完了済み task を Brain が active task として扱う。
- Sentinel が MQTT 接続前に登録した subscription を接続後に購読しない。
- Core / Lite Compose が旧 YOLO model 名と RTMO cache path を混在させる。
- Perception / Brain / biometric bridge の同名 `main` / `config` module が pytest 全体実行時に衝突する。
- SQLite router fixture が engine を破棄せず、event loop 終了後に aiosqlite worker warning を出す。

実行結果:

```text
Core runtime E2E:          31/31 passed
Lite runtime E2E:           5/5 passed
Focused pytest:           152 passed, 2 skipped
PostgreSQL integration:     2 passed
Full non-integration:    2426 passed, 3 skipped, 49 deselected
Perception image/runtime:   build OK, health model_loaded=true
ruff check/format:          passed
```

## 備考

- Phase 1 と Phase 2 は原則独立して並行準備可能。
- ブランチ削除は、対象ブランチの変更が `main` に確実に含まれていることを `git branch --contains <commit>` で確認してから行う。
