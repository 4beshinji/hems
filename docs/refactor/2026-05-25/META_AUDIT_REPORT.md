# メタ監査レポート: 2026-05-25 リファクタ AUDIT-AUDIT

## 結論

非 deferred の refactor row は大枠では audit 所見に沿って実装され、R7.1 の `BACKEND_API_KEY` は後続 commit
`3636e18` / `f3d02e7` / `878ed3a` まで含めて補修された。ただし「全 brain→backend 呼び出しへ配線」という
後続補修の主張は現コードと一致しない。`BACKEND_API_KEY` を設定した hardening 構成では、複数の brain
経由 backend call が 401 になり得るため、R7.1 は未完了リスクを残している。

deferred 境界は `LEDGER.md` に明記されており、R3.6 / W5 / W6 は本メタ監査では実装着手対象外として扱った。
frontend/mobile 独立監査、bridge deep-audit、distribution roadmap 本体も対象外。実コードは変更していない。

## Findings

### A0

- 該当なし。

  根拠: `docs/audit/2026-05-25/SUMMARY.md` の P0=0 は、今回確認した high-risk row では覆らなかった。
  `LEDGER.md` の deferred 9 行は「非 deferred 完了」の境界として明示されている。R7.1 の未配線は運用不具合に
  つながるが、default の `BACKEND_API_KEY` unset 構成では open のため、refactor 完了判定全体の即時撤回までは
  要しない。

### A1

- R7.1 follow-up の `BACKEND_API_KEY` 配線が全 brain→backend call を覆っていない。

  根拠:
  - `404c569 feat(backend): shared-key 認証を実装(BACKEND_API_KEY)` は
    `services/backend/main.py:127-156` で dashboard routers に `verify_api_key` を適用。
  - `3636e18 feat(brain): BACKEND_API_KEY を全 brain→backend 呼び出しへ配線` は helper と主要 call-site を追加。
  - しかし現コードでは次が protected backend endpoint に header 無しで到達する:
    - `services/brain/src/task_reminder.py:48` `GET /tasks/`
    - `services/brain/src/task_reminder.py:130` `PUT /tasks/{id}/reminded`
    - `services/brain/src/tool_handlers_core.py:105-115` `POST /voice-events/`
    - `services/brain/src/tool_handlers_core.py:187-202` `POST /shopping/`
    - `services/brain/src/tool_handlers_core.py:218-222` `GET /shopping/`
    - `services/brain/src/voice_capsule/persist.py:27` `POST /mobile/voice-capsule`
    - `services/brain/src/voice_capsule/ack_learner.py:133` `GET /mobile/voice-capsule/play-log`
  - `services/backend/routers/mobile.py:56-59` applies `verify_api_key` to the admin mobile router, including
    `/mobile/voice-capsule` and `/mobile/voice-capsule/play-log`.

  影響: `BACKEND_API_KEY` を設定した compose/hardening 構成で、task reminder、LLM tool 経由の shopping/voice-event、
  voice-capsule manifest/play-log が 401 になり、ユーザー操作・reminder・mobile capsule feedback が部分的に壊れる。

  推奨 follow-up: `backend_auth_headers()` を上記 call-site に追加し、`tests/test_backend_auth_wiring.py` に
  `TaskReminder`、`CoreToolHandlers` の direct backend path、`push_manifest`、`AckLearner._fetch_play_logs` の回帰 test を
  追加する。

### A2

- `BACKEND_API_KEY` の回帰 test が「主要 helper/一部 client」止まりで、全 call-site 配線主張を検証できていない。

  根拠: `tests/test_backend_auth.py` は backend gate 自体を検証し、`tests/test_backend_auth_wiring.py` は
  `backend_auth_headers()`、`DashboardClient` snapshot、voice path 分離を検証している。一方、A1 の未配線 call-site は
  test 対象外だったため、`3636e18` の「全 brain→backend」主張をカバーできていない。

  影響: auth 配線漏れが green test のまま残る。特に helper を経由しない direct HTTP call が今後も増えた場合に
  同じ漏れを検知できない。

  推奨 follow-up: backend-bound URL を作る brain module は原則 `DashboardClient` か `backend_auth_headers()` を通す、という
  lint/test レベルの smoke を追加する。最低限、protected backend endpoint 文字列と `headers=backend_auth_headers()` の
  対応を fixture で確認する。

- 現在の `make test-quick` は完走結果を確認できなかった。

  根拠: `source .venv/bin/activate && make test-quick` は 1296 collected / 19 deselected / 1277 selected まで進み、
  backend auth tests は pass したが、その後数分間追加出力がなく、最終 pass/fail を取得できなかった。`make lint` は clean。

  影響: `LEDGER.md` の「1269 passed」主張は現在 HEAD の test count ともずれており、現時点の全体回帰確認としては
  不十分。

  推奨 follow-up: timeout 付きで `make test-quick` を再実行し、hang 箇所がある場合は該当 test を分離してから
  report/ledger の verification 数を更新する。

### A3

- `LEDGER.md` の markdown table が機械照合しづらい形に壊れている。

  根拠:
  - R2.4 の row 名 `X\|None=None` が table cell 区切りとして解釈される。
  - R7.3 行は `出所 unit` cell が欠落しており、`done` が source-unit 列に入っている。
  - その結果、単純な table parser では `done` row 数が ledger 末尾の「done 33」と一致しない。

  影響: `done <sha>` と commit の機械照合、row count、source unit の追跡性が落ちる。人手では追えるが、
  メタ監査計画が求める「ledger 全体を機械照合する」作業にノイズが入る。

  推奨 follow-up: R2.4 は `X or None` など table-safe 表記へ変更し、R7.3 に `backend` の source-unit cell を戻す。

## 妥当と判断した範囲

- audit pass と refactor pass の境界: `docs/audit/2026-05-25/SUMMARY.md` はコード無改変の監査/doc 乖離是正として
  記述され、`docs/refactor/2026-05-25/PLAN.md` が実コード反映フェーズを分離している。
- high-risk rows:
  - R0.1 `2a77241`: `_llm_review` は `LLMResponse.content` / error guard へ移行し、専用 test を追加。
  - R1.3 `ac35b9e`: 当初の dead state 除去から live 化へ方針変更し、docs と test を伴っている。
  - R3.1 `1dd119b`: `_ALLOWED_ACTIONS` は dispatcher SoT へ寄せられている。
  - R3.2 `8a5cf71`: provider tool-call 整形は `brain_utils` へ共通化されている。
  - R4.1 `83bf149`: queue/scene/speech の per-call session は共有 session 方向へ整理されている。
  - R7.2 `cd47442`: backend migration の bare except は narrow/logging へ寄せられている。
  - R8.2 `7da0623`: VoiSona 固有 health hook は provider 側へ移されている。
- R7.1 後続補修:
  - `3636e18` で brain 側 helper と多数の backend-bound call に header が追加された。
  - `f3d02e7` で frontend nginx と compose の `brain` / `backend` / `frontend` env 配線が追加された。
  - `878ed3a` で follow-up doc と `env.example` が更新された。
  - ただし A1 の未配線 call-site が残るため、補修完了とは判定しない。
- deferred 境界: R3.6、R5.1-R5.6、R6.1-R6.2 は `LEDGER.md` で高 blast-radius tail として明示されており、
  本報告では残リスクとして扱うが、非 deferred 完了判定の対象外とした。

## 検証

- `git status --short`: 実行開始時点で `docs/refactor/2026-05-25/META_AUDIT_PLAN.md` が untracked。
- `git log --oneline --decorate --max-count=100`: `404c569`、`3636e18`、`f3d02e7`、`878ed3a` を含む relevant commits を確認。
- `git show --stat --oneline`:
  `2a77241`、`ac35b9e`、`1dd119b`、`8a5cf71`、`83bf149`、`404c569`、`3636e18`、`f3d02e7`、
  `878ed3a`、`cd47442`、`7da0623` を確認。
- `rg` / `nl -ba`: `BACKEND_API_KEY`、backend protected routers、brain backend-bound call-site、nginx/compose/env 配線を確認。
- `source .venv/bin/activate && make lint`: pass。`ruff check .` clean、`ruff format --check .` は 327 files formatted。
- `source .venv/bin/activate && make test-quick`: inconclusive。1296 collected / 19 deselected / 1277 selected までは確認。
  backend auth tests は pass したが、完走結果は取得できなかった。

## Follow-up

- 実コード修正が必要:
  - A1 の missing `BACKEND_API_KEY` headers を修正する。
  - auth wiring の focused tests を direct backend call-site まで広げる。
- docs のみで閉じるもの:
  - `LEDGER.md` の R2.4 / R7.3 table 破損を修正する。
  - verification 欄の test count を現在の完走結果に合わせて更新する。
- deferred tail:
  - R3.6 threshold 一本化、W5 god-function 分割、W6 namespace 脱結合は引き続き deferred。依存方向と blast radius が大きく、
    本メタ監査では未実装 finding ではなく明示済み残リスクとして扱う。

## 是正状況 (follow-up 実施)

本レポート作成後、A1 / A2 / A3 を同 session で是正した。

- **A1 (実コード)**: 未配線の 7 call-site すべてに `backend_auth_headers()` を追加。
  - `services/brain/src/task_reminder.py` — `GET /tasks/`、`PUT /tasks/{id}/reminded`(+ `brain_constants` import)
  - `services/brain/src/tool_handlers_core.py` — `POST /voice-events/`、`POST /shopping/`、`GET /shopping/`(+ import)
  - `services/brain/src/voice_capsule/persist.py` — `POST /mobile/voice-capsule`(+ import)
  - `services/brain/src/voice_capsule/ack_learner.py` — `GET /mobile/voice-capsule/play-log`(import 既存)
  - sweep スクリプトで brain 側の全 backend-bound URL call が `backend_auth_headers()` を伴うことを確認(残漏れ 0)。
- **A2 (test)**: `tests/test_backend_auth_wiring.py` に direct call-site の回帰 test を追加。
  `TaskReminder`(GET/PUT + unset)、`CoreToolHandlers`(shopping POST/GET、speak の voice-event log と synth path 分離)、
  `push_manifest`、`AckLearner._fetch_play_logs` を bearer 配線で検証。当該 file は 14 passed。
- **A3 (docs)**: `LEDGER.md` の R2.4 を pipe-free 表記(`型注釈 =None 引数を Optional 明示`)へ、
  R7.3 に欠落していた `backend` source-unit cell を復元。全 43 table row が 7 cell でパースできることを確認。
- **verification (是正後)**: `make lint` clean。`make test-quick` は **1283 passed, 2 skipped, 19 deselected**(65s、exit 0)で完走。
  本レポート作成時に inconclusive だった hang は再現せず、A2 で指摘した「完走結果未取得」は解消。`LEDGER.md` の test count も更新済み。
  これにより R7.1(`BACKEND_API_KEY` 全 brain→backend 配線)は補修完了と判定できる。
