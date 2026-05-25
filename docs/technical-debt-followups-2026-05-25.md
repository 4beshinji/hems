# Technical Debt Follow-ups — 2026-05-25

Source: follow-up from `docs/technical-debt-refactoring-plan-2026-05-24.md` execution.

## Summary

The refactoring plan is complete, but the execution surfaced several follow-up smells. None block the completed plan, and the verified gates passed after the changes:

- `make lint`
- `PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"`
  - Result: `1257 passed, 2 skipped, 19 deselected`

The items below should be handled as separate cleanup/reliability work. They are intentionally not folded into the completed refactoring plan.

## P1 — Worktree Is Too Broad For One Review

**Smell**: The repository has a very large dirty worktree spanning docs, infra, backend, many bridge services, Brain, scripts, and tests. The completed refactoring plan files are staged as review units, but many unrelated modified files remain unstaged.

**Evidence**:

- `git status --short` shows staged plan/review-unit files plus many unrelated modified files.
- Untracked files still outside the completed plan include:
  - `AGENTS.md`
  - `services/brain/src/brain_runtime.py`
  - `services/brain/src/brain_startup.py`

**Risk**:

- Reviewers cannot easily distinguish intentional refactor changes from unrelated work.
- A future commit could accidentally mix runtime/bootstrap changes with the already-large split-module refactor.

**Recommended action**:

- Commit or shelve the staged refactoring-plan review units first.
- Audit the remaining unstaged files by ownership area before staging anything else.
- Treat `brain_runtime.py` and `brain_startup.py` as their own startup/runtime extraction review, with dedicated tests.

## P1 — Staging Is Being Used As A Review Boundary, Not A Commit Boundary

**Smell**: The plan now defines review units and the corresponding files are staged, but no commits exist yet to preserve those boundaries.

**Evidence**:

- Staged files include the four intended review units:
  - `tool_schemas/` + `tool_registry.py`
  - `tool_handlers_*` + `tool_executor.py` + `tool_dispatch.py`
  - `world_model/*_updates.py` / `context_builder.py` / `mqtt_router.py` / `presence.py`
  - `rules/` + `rule_engine.py`
- The same index also includes supporting docs and follow-up tests.

**Risk**:

- If additional staging happens later, the review-unit boundary can blur again.
- A single large commit may still be hard to review even though the plan documents review units.

**Recommended action**:

- Prefer splitting staged work into commits matching the review units documented in `docs/technical-debt-refactoring-plan-2026-05-24.md`.
- If keeping one commit, include the review-unit list in the commit body.

## P1 — Sandbox Assumptions Changed During Execution

**Smell**: The audit said sandbox broad pytest should not be trusted because it had previously hung around async SQLite. In this run, the documented broad pytest gate completed successfully in the current environment.

**Evidence**:

- Full non-integration pytest completed with `1257 passed, 2 skipped, 19 deselected`.
- Earlier audit text still correctly says the official green signal should be normal-environment execution, but current sandbox behavior is no longer a hard blocker.

**Risk**:

- Future agents may overgeneralize either direction: always distrusting local pytest, or assuming all sandbox runs are reliable.

**Recommended action**:

- Update contributor notes to say broad pytest has historically been environment-sensitive.
- Record the exact command, timeout, and result whenever using it as evidence.
- Keep the normal-environment gate as canonical for release decisions.

## P2 — Generated Cache Files Still Appear On Disk

**Smell**: Python `__pycache__/` files exist under split-module directories.

**Evidence**:

- Examples observed under:
  - `services/brain/src/rules/__pycache__/`
  - `services/brain/src/tool_schemas/__pycache__/`
  - `services/brain/src/world_model/__pycache__/`
- They are ignored by `.gitignore`.

**Risk**:

- Low direct risk because they are ignored, but they add noise to filesystem scans and can confuse manual audits.

**Recommended action**:

- Leave them untracked.
- Consider adding a non-destructive cleanup target for generated Python cache files if developer workflows keep surfacing them.

## P2 — `get_chat_tools` Had Action Tool Leakage

**Smell**: Chat read-only tool selection included `control_actuator`, a mutating command.

**Evidence**:

- Fixed by moving the allowlist to `CHAT_ALLOWED_TOOL_NAMES` and removing `control_actuator`.
- Guarded by `tests/test_tool_registry.py::test_chat_tools_do_not_include_mutating_actions`.

**Risk**:

- Similar action/read-only drift can recur as new tools are added.

**Recommended action**:

- Keep all new chat-exposed tools read-only by default.
- When adding a new mutating tool, add it to the negative set in `test_chat_tools_do_not_include_mutating_actions`.

## P2 — RuleEngine Facade Still Owns Runtime Orchestration State

**Smell**: Rule domain mixins are split, but shared runtime state still lives in `RuleEngine`.

**Evidence**:

- Facade-owned state includes:
  - `_cooldowns`
  - `_voc_high_since`
  - `_low_pressure_since`
  - `_low_light_since`
  - `_high_light_since`
  - `_heavy_proc_since`
  - `_device_cache`
- This is now intentionally documented in the completed plan and covered by tests.

**Risk**:

- Further domain extraction can accidentally duplicate or bypass shared state.

**Recommended action**:

- Do not move shared state opportunistically.
- If this is refactored later, create a small runtime/state object and migrate one tracker family at a time.

## P2 — Heavy Process Tracker Had A Real GC Bug

**Smell**: The heavy-process sustained tracker only garbage-collected disappeared processes when `pc.top_processes` was non-empty.

**Evidence**:

- Exposed by `tests/test_rule_engine_sustained.py::test_heavy_process_cpu_sustained_triggers_and_gc_removes_stale_process`.
- Fixed in `services/brain/src/rule_engine.py`.

**Risk**:

- Similar sustained trackers may have reset/GC edge cases not covered by existing domain tests.

**Recommended action**:

- Keep reset-path tests for any new sustained tracker.
- When adding a tracker dict, test both trigger and recovery/disappearance behavior.

## P2 — Historical Docs Still Contain Old Names By Design

**Smell**: Old docs still contain `localcraw` and `services/openclaw-bridge` references.

**Evidence**:

- Historical notices were added to:
  - `SECURITY_AUDIT.md`
  - `docs/wiring-gap-05-orphan-cleanup-and-underused-data.md`
  - `docs/pitch-notebooklm.txt`
  - `docs/pitch-diagrams.mmd`
  - `docs/notes/upstream-port-plan.md`

**Risk**:

- Search results can still surface old names and mislead future cleanup work.

**Recommended action**:

- Do not mechanically rewrite historical docs.
- Prefer adding notices to any additional historical docs discovered later.
- Keep active docs as the source of truth for OpenClaw/localcraw canonical/alias behavior.

## P2 — Eval Artifacts Are Intentionally Tracked, But Policy Must Be Maintained

**Smell**: `infra/eval/eval.log` and `infra/eval/results/*` are tracked outputs.

**Evidence**:

- `infra/eval/README.md` now documents that these are retained historical artifacts.

**Risk**:

- Future eval runs may replace benchmark history accidentally or grow the repo with large machine-specific logs.

**Recommended action**:

- Update tracked eval artifacts only with explicit model/scenario evaluation changes.
- If eval output becomes too large or host-specific, move new output to an ignored directory in a separate hygiene change.

## P3 — Plan Completion Depends On Staged State

**Smell**: The plan’s “review unit tracking” completion is represented by git index state, which is local and can be lost or changed before commit.

**Evidence**:

- The review-unit files are staged at the time of completion.
- The plan itself documents review-unit file groups.

**Risk**:

- If the index is reset, the plan remains complete in docs, but the local staging proof disappears.

**Recommended action**:

- Commit the staged review units soon.
- If not committing immediately, preserve the staged file list in the PR description or commit plan.

## P1 — `BACKEND_API_KEY` Enforcement Is Not Wired To The Brain Client

**Smell**: The refactor pass R7.1 (`feat(backend): shared-key 認証を実装`, commit `404c569`) added a working shared-key gate on every dashboard router, but the brain's REST client was never updated to send that key. Enabling the documented env var silently breaks brain→backend.

**Evidence**:

- `services/backend/auth.py` `verify_api_key` enforces `Authorization: Bearer <BACKEND_API_KEY>` on all dashboard routers when `BACKEND_API_KEY` is set (verified at runtime: no key → 401, wrong key → 401, correct key → 200).
- `services/brain/src/dashboard_client.py` sends `_internal_headers()` (which reads a *different* env var, `HEMS_INTERNAL_TOKEN`) on only 2 of ~30 calls (`create_task`, `voice-events`). All snapshot POSTs (`pc/services/knowledge/gas/biometric/perception/home/news/weather/zones/brain/devices/timeseries`) and the device heartbeat/list GETs send no auth header.
- `env.example:90` already promises "(clients — frontend/brain — must then send the header)", but no brain code fulfills it. `HEMS_INTERNAL_TOKEN` ≠ `BACKEND_API_KEY`, so even the 2 authenticated calls 401 unless the two vars happen to be set identically.

**Risk**:

- Default deployment is unaffected (`BACKEND_API_KEY` unset → open, LAN-trusted), so this is not a regression — but the feature is a trap: following the env.example guidance to harden the backend immediately locks out the brain (28+ snapshot endpoints 401), degrading the dashboard to stale data with no obvious error beyond brain-side connection logs.
- The frontend (nginx/React) is in the same position — it was not verified to send the key either.

**Recommended action**:

- Add a single `BACKEND_API_KEY` → `Authorization: Bearer` header to `dashboard_client._internal_headers()` (or a dedicated helper applied to every `self.session` call), reading the same env var the backend gate uses.
- Decide whether `HEMS_INTERNAL_TOKEN` (chat proxy, `routers/chat.py:38`) and `BACKEND_API_KEY` should unify or stay distinct; document the split if kept.
- Verify the frontend sends the key before recommending `BACKEND_API_KEY` for any non-LAN exposure.
- Until wired, treat `BACKEND_API_KEY` as effectively unusable and note that in `env.example`.

**Resolution (2026-05-25)**: Wired end-to-end. Scope was widened from "dashboard_client only" to *all* brain→backend callers after auditing the surface — a dashboard_client-only fix would have left `classifier-cache` / `shopping` / `automations` / `timeline` / `devices` / `scenes` / `tasks-queue` callers 401ing, i.e. a partial trap.

- **Shared helper**: `backend_auth_headers()` added to `services/brain/src/brain_constants.py` — returns `{"Authorization": "Bearer <BACKEND_API_KEY>"}` when set, `{}` when unset (reads env each call for hot-reload). Distinct from `HEMS_INTERNAL_TOKEN` (voice/stt); the split is **kept**, not unified, and documented in `env.example`.
- **Applied to every `verify_api_key`-gated brain→backend call** across 12 files (~41 sites): `dashboard_client.py` (21), `event_automation.py`, `scene_executor.py`, `automation_engine.py`, `annotator/{cache,rule_promoter,shopping_classifier}.py`, `task_scheduling/queue_manager.py`, `timeline/generator.py`, `device_dispatcher.py` (only the `/devices/*` calls — bridge dispatch untouched), `voice_capsule/{builder,ack_learner}.py`. Voice-service calls keep `_internal_headers()`; `/mobile/*` calls (`voice_capsule/persist.py`, `ack_learner` play-log) are left alone — they use `verify_mobile_device` (per-device key), a separate scheme.
- **Frontend**: `services/frontend/nginx.conf` `/api/` location now injects `Authorization: Bearer ${BACKEND_API_KEY}` (mirrors the existing `/api/voice/` + `/api/stt/` `HEMS_INTERNAL_TOKEN` injection).
- **Compose plumbing**: `BACKEND_API_KEY` was previously plumbed into *no* service (so the gate could never activate). Added `BACKEND_API_KEY=${BACKEND_API_KEY:-}` to the `brain`, `backend`, and `frontend` services in `infra/docker-compose.yml`.
- **Regression test**: `tests/test_backend_auth_wiring.py` — helper unset/set, dashboard call carries the bearer, and the key does **not** leak onto the voice path.
- **Gates**: `ruff check .` + `ruff format --check .` clean; full non-integration suite `1275 passed, 2 skipped, 19 deselected`.
