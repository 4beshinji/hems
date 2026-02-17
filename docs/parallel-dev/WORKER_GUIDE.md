# Parallel Development Worker Guide

All concurrent workers MUST read this document before starting.
See also:
- [API_CONTRACTS.md](./API_CONTRACTS.md) — Inter-service API details
- [DISPATCH.md](./DISPATCH.md) — Current lane assignments and per-worker instructions

---

## Quick Start Checklist

1. **Read** this guide and `API_CONTRACTS.md`
2. **Identify** your assigned lane from the table below
3. **Branch** from `main`: `git checkout -b lane/{L#}-{description}`
4. **Verify** no file conflicts with other active lanes (check the ownership matrix)
5. **Test** your lane's acceptance criteria before requesting merge

---

## Lane Definitions

| Lane | Domain | Owned Directories | Do NOT Touch |
|------|--------|-------------------|--------------|
| **L1** | Edge / SensorSwarm | `edge/`, `infra/virtual_edge/` | `services/` |
| **L2** | Perception | `services/perception/`, `infra/virtual_camera/` | `services/brain/`, `services/dashboard/` |
| **L3** | Voice Service | `services/voice/` | `services/brain/`, `services/dashboard/` |
| **L4** | Dashboard (Backend + Frontend) | `services/dashboard/` | `services/wallet/`, `services/brain/` |
| **L5** | Wallet Service | `services/wallet/` | `services/dashboard/` |
| **L6** | Brain (Internal Logic) | `services/brain/src/` | other `services/` directories |
| **L7** | Infra / Docker | `infra/` (compose, scripts, mock_llm, mosquitto), `env.example` | service source code |
| **L8** | Docs / Promo | `docs/`, `README.md`, `DEPLOYMENT.md` | source code |
| **L9** | Mobile Wallet App (PWA) | `services/wallet-app/` | `services/wallet/`, `services/dashboard/` |

### Lane Coupling Map

```
L1 Edge ──MQTT──> L6 Brain ──REST──> L4 Dashboard ──REST──> L5 Wallet
                    │                   │
L2 Perception ─MQTT┘                   └──nginx──> L3 Voice

L9 Wallet App (PWA) ──REST──> L5 Wallet

L7 Infra  = docker-compose, env, scripts (shared config)
L8 Docs   = documentation only (no code)
```

---

## File Ownership Matrix

Shared files that require coordination:

| File | Owner | Rule |
|------|-------|------|
| `infra/docker-compose.yml` | **L7** | L7 is gatekeeper. Other lanes propose changes only. |
| `infra/docker-compose.edge-mock.yml` | **L7** | Same as above. |
| `services/dashboard/frontend/nginx.conf` | **L4** | New proxy paths require L4 approval. |
| `services/dashboard/frontend/src/App.tsx` | **L4** | L4 exclusive. Other lanes do not touch. |
| `CLAUDE.md` | **L8** | L8 manages. Other lanes propose additions. |
| `env.example` | **L7** | L7 manages. New env vars: notify L7. |
| `.env` | **L7** | Never committed. Local only. |

### Conflict Resolution Protocol

1. If you need to modify a file outside your lane, **create a separate commit** describing the change and tag the lane owner in your PR description.
2. If two lanes must modify the same file, the **lower-numbered lane** merges first.
3. `docker-compose.yml` changes: describe your required changes in a `# L{N} request:` comment in your PR. L7 integrates.

---

## Git Workflow

### Worktree (必須)

各ワーカーは専用の worktree で作業する。**メインディレクトリ (`Office_as_AI_ToyBox`) で `git checkout` は禁止。**

| レーン | ワーキングツリー | ブランチ |
|-------|---------------|---------|
| Main (監視/統合) | `/home/sin/code/Office_as_AI_ToyBox` | `main` |
| L3 | `/home/sin/code/soms-worktrees/L3` | `lane/L3-*` |
| L4 | `/home/sin/code/soms-worktrees/L4` | `lane/L4-*` |
| L5 | `/home/sin/code/soms-worktrees/L5` | `lane/L5-*` |
| L6 | `/home/sin/code/soms-worktrees/L6` | `lane/L6-*` |
| L7 | `/home/sin/code/soms-worktrees/L7` | `lane/L7-*` |
| L9 | `/home/sin/code/soms-worktrees/L9` | `lane/L9-*` |

**ワーカー起動時の手順:**
1. Claude Code の working directory を自分の worktree パスに設定する
2. `git branch --show-current` で正しいブランチにいることを確認
3. 他の worktree のファイルを直接編集しない

**新しいレーンを追加する場合:**
```bash
git worktree add /home/sin/code/soms-worktrees/L{N} lane/L{N}-{description}
```

**worktree を確認:**
```bash
git worktree list
```

### Branch Naming

```
lane/L1-swarm-ble-transport
lane/L2-activity-monitor-v2
lane/L3-rejection-stock-quality
lane/L4-task-card-redesign
lane/L5-demurrage-scheduler
lane/L6-react-loop-retry
lane/L7-healthcheck-all-services
lane/L8-deployment-guide
```

### Merge Order

1. **L7 (Infra)** merges first — docker-compose changes affect all services
2. **L1, L2, L3, L5** merge in any order — no cross-dependencies
3. **L6 (Brain)** merges after L1/L2 if MQTT topic changes occurred
4. **L4 (Dashboard)** merges after L5 if wallet API changed
5. **L8 (Docs)** merges last — captures final state

### Commit Convention

```
feat(L4): add task card completion animation
fix(L6): prevent duplicate speak calls in ReAct loop
refactor(L5): extract fee calculation to service layer
docs(L8): update deployment guide for ROCm 6.x
```

---

## Shared Resource Coordination

### PostgreSQL Schema Separation

| Schema | Owner | Tables |
|--------|-------|--------|
| `public` | **L4** (Dashboard) | `tasks`, `voice_events`, `users`, `system_stats` |
| `wallet` | **L5** (Wallet) | `wallets`, `ledger_entries`, `devices`, `reward_rates`, `supply_stats` |

- Dashboard and Wallet use **separate connection URLs** (`DATABASE_URL` vs `WALLET_DATABASE_URL`)
- No cross-schema joins. Communication is REST only.
- Schema migrations: coordinate with lane owner before adding columns

### MQTT Topic Hierarchy

| Pattern | Publisher | Subscriber |
|---------|-----------|------------|
| `office/{zone}/sensor/{device_id}/{channel}` | L1 (Edge) | L6 (Brain) |
| `office/{zone}/sensor/{hub}.{leaf}/{channel}` | L1 (SensorSwarm) | L6 (Brain) |
| `office/{zone}/camera/{camera_id}/status` | L2 (Perception) | L6 (Brain) |
| `office/{zone}/occupancy` | L2 (Perception) | L6 (Brain) |
| `office/{zone}/activity` | L2 (Perception) | L6 (Brain) |
| `office/{zone}/whiteboard/status` | L2 (Perception) | L6 (Brain) |
| `mcp/{device_id}/request/call_tool` | L6 (Brain) | L1 (Edge) |
| `mcp/{device_id}/response/{request_id}` | L1 (Edge) | L6 (Brain) |
| `mcp/{camera_id}/request/capture` | L2 (Perception) | L1 (Camera Edge) |
| `mcp/{camera_id}/response/{request_id}` | L1 (Camera Edge) | L2 (Perception) |
| `office/{zone}/task_report/{task_id}` | L4 (Dashboard) | L6 (Brain) |
| `{topic_prefix}/heartbeat` | L1 (Edge) | L6 (Brain) |

**Rule**: Do NOT invent new top-level MQTT topic namespaces. New topics must follow existing patterns. Coordinate with L6 if Brain needs to subscribe to new topics.

### nginx Routing (Port 80)

| Path Prefix | Upstream | Owner |
|-------------|----------|-------|
| `/` | SPA (`index.html`) | L4 |
| `/api/wallet/` | `wallet:8000` | L5 |
| `/api/voice/` | `voice-service:8000` | L3 |
| `/api/` | `backend:8000` | L4 |
| `/audio/` | `voice-service:8000` | L3 |

Adding new route prefixes: coordinate with L4 (nginx.conf owner).

### Docker Compose Service Ports

| Port | Service | Container | Owner |
|------|---------|-----------|-------|
| 80 | Frontend (nginx) | `soms-frontend` | L4 |
| 1883 | MQTT | `soms-mqtt` | L7 |
| 5432 | PostgreSQL | `soms-postgres` | L7 |
| 8000 | Dashboard Backend | `soms-backend` | L4 |
| 8001 | Mock LLM | `soms-mock-llm` | L7 |
| 8002 | Voice Service | `soms-voice` | L3 |
| 8003 | Wallet Service (internal) | `soms-wallet` | L5 |
| 11434 | Ollama | `soms-ollama` | L7 |
| 50021 | VOICEVOX | `soms-voicevox` | L3 |

---

## Lane Acceptance Criteria

### L1 — Edge / SensorSwarm

- [ ] `edge/` firmware compiles (MicroPython linting or PlatformIO build)
- [ ] Virtual edge emulator boots: `docker compose -f infra/docker-compose.edge-mock.yml up virtual-edge`
- [ ] MQTT telemetry payloads match `{"value": X}` format
- [ ] MCP JSON-RPC 2.0 request/response cycle works

### L2 — Perception

- [ ] Test scripts pass: `python3 services/perception/test_activity.py`, `test_discovery.py`
- [ ] MQTT publish topics match documented patterns
- [ ] No import dependencies on `services/brain/` or `services/dashboard/`

### L3 — Voice Service

- [ ] Service starts: `docker compose up voice-service voicevox`
- [ ] `POST /api/voice/synthesize` returns audio URL
- [ ] Rejection stock generation works in background
- [ ] No breaking changes to existing API response schemas

### L4 — Dashboard

- [ ] Frontend builds: `cd services/dashboard/frontend && npm run build`
- [ ] Backend starts: `uvicorn main:app` with SQLite fallback
- [ ] Task CRUD endpoints respond correctly
- [ ] Wallet service calls degrade gracefully when wallet is down

### L5 — Wallet Service

- [ ] Service starts with PostgreSQL or SQLite fallback
- [ ] Double-entry ledger balances: sum(debits) == sum(credits)
- [ ] Supply stats update correctly on transactions
- [ ] P2P transfer fee burn works (5% rate)

### L6 — Brain

- [ ] Integration test: `python3 infra/tests/integration/integration_test_mock.py`
- [ ] ReAct loop terminates within `REACT_MAX_ITERATIONS` (5)
- [ ] No duplicate tool calls within a single cycle
- [ ] Speak calls respect zone cooldown (5 min)

### L7 — Infra

- [ ] `docker compose -f infra/docker-compose.yml config` validates
- [ ] All services start: `docker compose up -d`
- [ ] No port conflicts
- [ ] Edge mock compose works independently

### L8 — Docs

- [ ] Markdown renders correctly (no broken links)
- [ ] Technical claims verified against source code
- [ ] No source code modifications

---

## Current State References

| Document | Purpose |
|----------|---------|
| `docs/handoff/CURRENT_STATE.md` | Latest session state, uncommitted changes, issue tracker |
| `docs/TASK_SCHEDULE.md` | Development roadmap and task priorities |
| `docs/architecture/wallet-separation.md` | Wallet/dashboard separation design |
| `docs/SYSTEM_OVERVIEW.md` | High-level architecture |
| `CLAUDE.md` | Build commands, architecture reference, conventions |

### Known Issues

ISSUES.md 全32件解決済み。DISPATCH.md の Issue トラッカーを参照。
