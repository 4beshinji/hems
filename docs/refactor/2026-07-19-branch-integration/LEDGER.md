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
| 3 | 1 | 重複ブランチ削除 | `origin/refactor/upstream-port`, `origin/refactor/brain-dedup`, `origin/hardening/p0-impl`, `origin/feat/distribution` | Pending (remote) | — | ローカルは削除済み、remote 削除待ち |
| 3 | 2 | 統合済みブランチ削除 | `origin/docs/audit-2026-05-30-review-plan`, `origin/lite` | Pending (remote) | — | ローカルは削除済み、remote 削除待ち |
| 3 | 3 | ローカル backup ブランチ削除 | `backup/hems-local-20260628` | Done | — | `git branch -D backup/hems-local-20260628` |
| 4 | 1 | ドキュメント同期 | `CLAUDE.md`, `IMPLEMENTATION_MAP.md`, `env.example`, 各 canonical doc | In Progress | — | `IMPLEMENTATION_MAP.md` §1.2 に notifier/sentinel 追加済 |

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

## 備考

- Phase 1 と Phase 2 は原則独立して並行準備可能。
- ブランチ削除は、対象ブランチの変更が `main` に確実に含まれていることを `git branch --contains <commit>` で確認してから行う。
