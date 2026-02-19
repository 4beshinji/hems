# API Contracts — Inter-Service Communication

This document defines the behavioral contracts between SOMS services.
Workers use this to mock dependencies and verify integration points.

**Source of truth**: Always check the actual source files (paths noted below) for Pydantic schemas. This document focuses on *what to send, what comes back, and what happens on failure*.

---

## 1. Dashboard Backend API (`:8000`)

Source: `services/dashboard/backend/`
- Schemas: `schemas.py`
- Routers: `routers/tasks.py`, `routers/voice_events.py`, `routers/users.py`
- Models: `models.py`

### Tasks

#### `GET /tasks/`

List active tasks (filtered: excludes expired).

| Field | Value |
|-------|-------|
| Query | `skip: int = 0`, `limit: int = 100` |
| Response | `List[Task]` — `task_type` field is parsed from JSON string to `List[str]` |
| Notes | Filters out tasks where `expires_at < now()` |

#### `POST /tasks/`

Create or update a task (with duplicate detection).

| Field | Value |
|-------|-------|
| Body | `TaskCreate` — see `schemas.py` |
| Required fields | `title` |
| Key optionals | `bounty_gold` (default 10), `urgency` (default 2, range 0-4), `zone`, `location`, `task_type: List[str]` |
| Voice fields | `announcement_audio_url`, `announcement_text`, `completion_audio_url`, `completion_text` |
| Response | `Task` (full object with `id`, timestamps) |

**Duplicate detection** (sequential):
1. Stage 1: exact match on `title` + `location` where `is_completed=False`
2. Stage 2: same `zone` + overlapping `task_type` where `is_completed=False`
3. If duplicate found: **updates** existing task in-place (preserves ID for audio URL stability)

**Side effects**:
- Increments `SystemStats.tasks_created`
- Fire-and-forget: `POST wallet:8000/devices/xp-grant` (10 XP, `event_type=task_created`) — 5s timeout, logged on failure

#### `PUT /tasks/{task_id}/accept`

Assign a task to a user.

| Field | Value |
|-------|-------|
| Body | `{"user_id": int}` |
| Response | `Task` |
| Errors | 404 (not found), 400 (already completed), 400 (already assigned) |
| Side effects | Sets `assigned_to`, `accepted_at` |

#### `PUT /tasks/{task_id}/complete`

Mark a task as completed. Triggers reward payout.

| Field | Value |
|-------|-------|
| Body (optional) | `{"report_status": str, "completion_note": str}` |
| `report_status` values | `no_issue`, `resolved`, `needs_followup`, `cannot_resolve` |
| Response | `Task` |
| Error | 404 (not found) |

**Side effects** (all fire-and-forget, 5s timeout):
1. Updates `SystemStats.total_xp += bounty_xp`, `tasks_completed += 1`
2. `POST wallet:8000/devices/xp-grant` (20 XP, `event_type=task_completed`)
3. If `assigned_to` and `bounty_gold`:
   - `GET wallet:8000/devices/zone-multiplier/{zone}` → `multiplier` (fallback: `1.0`)
   - Adjusted bounty = `int(bounty_gold * multiplier)`
   - `POST wallet:8000/transactions/task-reward` with adjusted amount
4. MQTT publish to `office/{zone}/task_report/{task_id}` (JSON: task_id, title, report_status, completion_note, zone)

#### `PUT /tasks/{task_id}/reminded`

Mark task as reminded (used by Brain's TaskReminder).

| Field | Value |
|-------|-------|
| Body | None |
| Response | `Task` |
| Side effects | Updates `last_reminded_at` |

#### `GET /tasks/queue`

Get queued (pre-dispatch) tasks.

| Field | Value |
|-------|-------|
| Response | `List[Task]` where `is_queued=True`, ordered by `urgency DESC, created_at ASC` |

#### `PUT /tasks/{task_id}/dispatch`

Move task from queue to active display.

| Field | Value |
|-------|-------|
| Body | None |
| Response | `Task` |
| Side effects | Sets `is_queued=False`, `dispatched_at=now()` |

#### `GET /tasks/stats`

Dashboard statistics.

| Field | Value |
|-------|-------|
| Response | `{"total_xp": int, "tasks_completed": int, "tasks_created": int, "tasks_active": int, "tasks_queued": int, "tasks_completed_last_hour": int}` |

### Voice Events

#### `POST /voice-events/`

Record a voice event (from Brain's speak tool).

| Field | Value |
|-------|-------|
| Body | `{"message": str, "audio_url": str, "zone": str?, "tone": str}` |
| `tone` values | `neutral`, `caring`, `humorous`, `alert` |
| Response | `VoiceEvent` with `id`, `created_at` |

#### `GET /voice-events/recent`

Poll recent voice events (last 60 seconds, max 5 minutes old).

| Field | Value |
|-------|-------|
| Response | `List[VoiceEvent]` ordered by `created_at DESC` |

### Users (Stub)

#### `GET /users/` / `POST /users/`

Minimal user CRUD. Guest user seeded on startup. Mostly unused in kiosk mode.

---

## 2. Wallet Service API (`:8003`, internal via nginx at `/api/wallet/`)

Source: `services/wallet/src/`
- Schemas: `schemas.py`
- Routers: `routers/wallets.py`, `routers/transactions.py`, `routers/devices.py`, `routers/admin.py`
- Models: `models.py`

### Wallets

#### `POST /wallets/`

Create or get wallet.

| Field | Value |
|-------|-------|
| Body | `{"user_id": int}` |
| Response | `{"id": int, "user_id": int, "balance": int, "created_at": datetime, "updated_at": datetime}` |
| Notes | `balance` is in milli-units (1000 = 1.0 SOMS). Idempotent: returns existing if exists. |

#### `GET /wallets/{user_id}`

Get wallet (creates if not exists).

#### `GET /wallets/{user_id}/history`

Paginated ledger history.

| Field | Value |
|-------|-------|
| Query | `limit: int = 50` (max 200), `offset: int = 0` |
| Response | `List[LedgerEntry]` ordered by `created_at DESC` |
| Entry fields | `transaction_id` (UUID), `amount` (signed), `balance_after`, `entry_type` (DEBIT/CREDIT), `transaction_type`, `description`, `reference_id`, `counterparty_wallet_id` |

`transaction_type` values: `INFRASTRUCTURE_REWARD`, `TASK_REWARD`, `P2P_TRANSFER`, `FEE_BURN`, `DEMURRAGE_BURN`

### Transactions

#### `POST /transactions/task-reward`

Pay task bounty from system wallet (user_id=0).

| Field | Value |
|-------|-------|
| Body | `{"user_id": int, "amount": int, "task_id": int, "description": str?}` |
| Response | `{"transaction_id": UUID, "entries": List[LedgerEntry]}` (2 entries: system debit + user credit) |
| Error | 400 (insufficient system balance) |
| Notes | `reference_id = "task:{task_id}"` for idempotency |

#### `POST /transactions/p2p-transfer`

P2P transfer with fee burn.

| Field | Value |
|-------|-------|
| Body | `{"from_user_id": int, "to_user_id": int, "amount": int, "description": str?}` |
| Response | `{"transaction_id": UUID, "entries": List[LedgerEntry], "fee": TransferFeeInfo}` |
| Errors | 400 (amount <= 0), 400 (below minimum), 400 (insufficient balance) |
| Fee | 5% burned. Min transfer = `max(100, circulating * 0.001)` |
| Notes | 4 ledger entries total: 2 for transfer + 2 for fee burn |

#### `GET /transactions/transfer-fee?amount={int}`

Preview fee calculation (no side effects).

| Field | Value |
|-------|-------|
| Response | `{"fee_rate": float, "fee_amount": int, "net_amount": int, "min_transfer": int, "below_minimum": bool}` |

#### `GET /transactions/{transaction_id}`

Get transaction details. Error: 404.

### Devices

#### `POST /devices/`

Register edge device.

| Field | Value |
|-------|-------|
| Body | `{"device_id": str, "owner_id": int, "device_type": str, "display_name": str?, "topic_prefix": str?}` |
| `device_type` values | `llm_node`, `sensor_node`, `hub` |
| Response | `DeviceResponse` with `xp: int = 0` |
| Error | 409 (already registered) |

#### `GET /devices/`

List all devices ordered by `registered_at DESC`.

#### `PUT /devices/{device_id}`

Update device metadata. Error: 404.

#### `POST /devices/xp-grant`

Grant XP to all active devices in a zone.

| Field | Value |
|-------|-------|
| Body | `{"zone": str, "task_id": int, "xp_amount": int = 10, "event_type": str = "task_created"}` |
| Response | `{"devices_awarded": int, "total_xp_granted": int, "device_ids": List[str]}` |
| Notes | Matches zone from device `topic_prefix`. Called by Dashboard on task create/complete. |

#### `GET /devices/zone-multiplier/{zone}`

Get reward multiplier based on zone device XP.

| Field | Value |
|-------|-------|
| Response | `{"zone": str, "multiplier": float, "device_count": int, "avg_xp": int}` |
| Notes | Multiplier range: 1.0x (no devices or low XP) to 3.0x (high XP). Called by Dashboard on task complete. |

### Supply (Admin)

#### `GET /supply`

| Response | `{"total_issued": int, "total_burned": int, "circulating": int}` |

#### `GET /reward-rates`

List reward rates by device type. Seeded: `llm_node`, `sensor_node`, `hub`.

#### `PUT /reward-rates/{device_type}`

Update reward rate. Error: 404.

### Background Process: Demurrage

- Runs on interval (configured in monetary policy)
- Burns 2% per day from non-system wallets
- No API trigger — automatic

---

## 3. Voice Service API (`:8002`, via nginx at `/api/voice/`)

Source: `services/voice/src/`
- Main: `main.py`
- Speech: `speech_generator.py`
- TTS: `voicevox_client.py`
- Stock: `rejection_stock.py`
- Models: `models.py`

### Synthesis

#### `POST /api/voice/synthesize`

Direct text-to-speech (no LLM generation).

| Field | Value |
|-------|-------|
| Body | `{"text": str}` |
| Response | `{"audio_url": str, "text_generated": str, "duration_seconds": float}` |
| Notes | `audio_url` format: `/audio/speak_{uuid}.mp3`. Used by Brain's `speak` tool and frontend accept. |

#### `POST /api/voice/announce`

Generate announcement from task data (LLM text gen + VOICEVOX synthesis).

| Field | Value |
|-------|-------|
| Body | `{"task": {"title": str, "description": str?, "location": str?, "bounty_gold": int, "urgency": int, "zone": str?}}` |
| Response | `{"audio_url": str, "text_generated": str, "duration_seconds": float}` |
| Timeout | LLM call: 30s. Total: up to ~35s. |

#### `POST /api/voice/announce_with_completion`

Generate both announcement and completion voices.

| Field | Value |
|-------|-------|
| Body | Same as `/announce` |
| Response | `{"announcement_audio_url": str, "announcement_text": str, "announcement_duration": float, "completion_audio_url": str, "completion_text": str, "completion_duration": float}` |
| Timeout | 2x LLM calls + 2x synthesis. Total: up to ~70s. |
| Notes | Used by Brain when creating tasks. Both URLs stored in Dashboard task record. |

#### `POST /api/voice/feedback/{feedback_type}`

Generate feedback voice (e.g., `task_completed`, `task_accepted`).

| Field | Value |
|-------|-------|
| Response | `VoiceResponse` |

### Rejection Stock

#### `GET /api/voice/rejection/random`

Get pre-generated rejection voice (instant).

| Field | Value |
|-------|-------|
| Response | `{"audio_url": str, "text": str}` |
| Notes | Falls back to on-demand synthesis if stock empty (~30s vs ~10ms). |

#### `GET /api/voice/rejection/status`

| Response | `{"stock_count": int, "max_stock": int, "is_generating": bool, "needs_refill": bool}` |

#### `POST /api/voice/rejection/clear`

Clear and regenerate stock. Response: `{"status": "cleared", "stock_count": int}`.

### Audio Serving

#### `GET /audio/{filename}`

Serve generated MP3 files. Error: 404.

#### `GET /audio/rejections/{filename}`

Serve rejection stock audio. Error: 404.

### Background Process: Rejection Stock Idle Generation

- Continuously generates up to 100 rejection phrases during idle
- Pauses during active requests
- LLM text generation + VOICEVOX synthesis per phrase

---

## 4. MQTT Topic Contracts

All payloads are JSON unless noted.

### Sensor Telemetry

```
Topic:    office/{zone}/sensor/{device_id}/{channel}
Payload:  {"value": <number>}
QoS:      0
Publisher: Edge devices (L1)
Subscriber: Brain WorldModel (L6)

Channels: temperature, humidity, co2, pressure, light, motion, battery
```

### SensorSwarm (Hub-forwarded)

```
Topic:    office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}
Payload:  {"value": <number>}
Publisher: SwarmHub (L1)
Subscriber: Brain WorldModel (L6)

Device ID uses dot notation: swarm_hub_01.leaf_env_01
```

### Perception Events

```
Topic:    office/{zone}/occupancy
Payload:  {"count": int, "timestamp": str}
Publisher: OccupancyMonitor (L2)

Topic:    office/{zone}/activity
Payload:  {"activity_level": str, "details": {...}}
Publisher: ActivityMonitor (L2)

Topic:    office/{zone}/whiteboard/status
Payload:  {"has_content": bool, "timestamp": str}
Publisher: WhiteboardMonitor (L2)
```

### MCP Device Control (JSON-RPC 2.0)

```
# Brain → Edge Device
Topic:    mcp/{agent_id}/request/call_tool
Payload:  {"id": str, "method": "call_tool", "params": {"tool_name": str, "arguments": {...}}}

# Edge Device → Brain
Topic:    mcp/{agent_id}/response/{request_id}
Payload:  {"id": str, "result": {...}} or {"id": str, "error": {"message": str}}
Timeout:  10s (mcp_bridge.py)
```

### MCP Camera Capture

```
# Perception → Camera
Topic:    mcp/{camera_id}/request/capture
Payload:  {"id": str, "resolution": "VGA"|"QVGA"|"SVGA"|"XGA"|"UXGA", "quality": int}

# Camera → Perception
Topic:    mcp/{camera_id}/response/{request_id}
Payload:  {"image": "<base64-encoded JPEG>"}
Timeout:  10s
```

### Task Reports

```
Topic:    office/{zone}/task_report/{task_id}
Payload:  {"task_id": int, "title": str, "report_status": str, "completion_note": str, "zone": str}
Publisher: Dashboard Backend (L4) on task completion
Subscriber: Brain WorldModel (L6) — creates task_report Event for LLM context

report_status values: no_issue, resolved, needs_followup, cannot_resolve
```

### Heartbeat

```
Topic:    {topic_prefix}/heartbeat
Payload:  {"timestamp": str, "uptime": int}
Interval: 60s
Publisher: All edge devices (L1)
Subscriber: Brain (L6)
```

### Brain Subscriptions

Brain subscribes to: `office/#`, `mcp/+/response/#`

---

## 5. Cross-Service Call Patterns

### Brain → Dashboard (REST)

Source: `services/brain/src/dashboard_client.py`

| Call | Method | Behavior on Failure |
|------|--------|---------------------|
| Create task | `POST /tasks/` | Log warning, skip voice announcement |
| Get active tasks | `GET /tasks/` | Return empty list |
| Mark reminded | `PUT /tasks/{id}/reminded` | Log warning, continue |

Brain uses a shared `aiohttp.ClientSession` injected at startup.
Dashboard URL configured via env: `DASHBOARD_API_URL` (default: `http://backend:8000`).

### Brain → Voice (REST)

Source: `services/brain/src/tool_executor.py`

| Call | Method | Behavior on Failure |
|------|--------|---------------------|
| Announce task | `POST /api/voice/announce_with_completion` | Task created without voice |
| Speak (ephemeral) | `POST /api/voice/synthesize` | Log warning, voice event still recorded |

Voice URL configured via env: `VOICE_SERVICE_URL` (default: `http://voice-service:8000`).

### Dashboard → Wallet (REST)

Source: `services/dashboard/backend/routers/tasks.py`

| Call | Method | Timeout | Behavior on Failure |
|------|--------|---------|---------------------|
| XP grant (task created) | `POST /devices/xp-grant` | 5s | Fire-and-forget, logged |
| XP grant (task completed) | `POST /devices/xp-grant` | 5s | Fire-and-forget, logged |
| Zone multiplier | `GET /devices/zone-multiplier/{zone}` | 5s | Fallback to `1.0x` |
| Task reward | `POST /transactions/task-reward` | 5s | Fire-and-forget, logged |

Wallet URL configured via env: `WALLET_SERVICE_URL` (default: `http://wallet:8000`).

**All wallet calls are fault-tolerant**: Dashboard functions correctly even when Wallet service is down.

### Dashboard → MQTT

Source: `services/dashboard/backend/routers/tasks.py`

| Event | Topic | When |
|-------|-------|------|
| Task completion report | `office/{zone}/task_report/{task_id}` | On `PUT /tasks/{id}/complete` |

---

## 6. Error Handling & Timeouts

| Caller → Callee | Timeout | Retry | Fallback |
|------------------|---------|-------|----------|
| Brain → Dashboard | `aiohttp` default | No | Log + skip |
| Brain → Voice (synthesize) | `aiohttp` default | No | Log + record voice event without audio |
| Brain → Voice (announce) | ~35s (LLM 30s + synth) | No | Task created without voice |
| Brain → Edge (MCP) | 10s | No | Return error to LLM |
| Dashboard → Wallet (XP) | 5s | No | Fire-and-forget, logged |
| Dashboard → Wallet (reward) | 5s | No | Fire-and-forget, logged |
| Dashboard → Wallet (multiplier) | 5s | No | Default to `1.0x` |
| Voice → LLM | 30s | No | Fallback text template |
| Voice → VOICEVOX | `aiohttp` default | No | 500 error |
| Perception → Camera (MCP) | 10s | No | Return None, skip frame |

### Graceful Degradation Summary

| Service Down | Impact |
|-------------|--------|
| Wallet | Dashboard works. No rewards, multiplier defaults to 1.0x. |
| Voice | Brain works. Tasks created without voice. |
| Dashboard | Brain logs warnings, cannot create/query tasks. |
| MQTT | Brain cannot receive sensor data or control devices. |
| LLM (Ollama) | Brain cycles fail. Voice uses fallback text templates. |
| VOICEVOX | Voice synthesis fails. Rejection stock depletes. |
| PostgreSQL | Services fall back to SQLite (Dashboard, Wallet). |

---

## 7. Database Schema Boundaries

### Dashboard (Schema: `public`)

Source: `services/dashboard/backend/models.py`

```
tasks           — 19+ columns (title, bounty, urgency, voice URLs, assignment, report)
voice_events    — message, audio_url, zone, tone
users           — username, display_name (stub in kiosk mode)
system_stats    — singleton: total_xp, tasks_completed, tasks_created
```

### Wallet (Schema: `wallet`)

Source: `services/wallet/src/models.py`

```
wallets         — user_id (unique), balance (milli-units)
ledger_entries  — double-entry: transaction_id, amount, balance_after, entry_type, transaction_type
devices         — device_id (unique), owner_id, device_type, xp, topic_prefix
reward_rates    — device_type (unique), rate_per_hour
supply_stats    — singleton: total_issued, total_burned, circulating
```

**No cross-schema access**. All inter-service data exchange is via REST APIs.

---

## 8. Mocking Guide by Lane

### L1 (Edge) — Mock: nothing external

Edge devices are self-contained. Test with virtual edge emulator.

### L2 (Perception) — Mock: MQTT broker, Camera MCP

- MQTT: use local Mosquitto or mock publish/subscribe
- Camera: use `infra/virtual_camera/` RTSP server or MCP response stub

### L3 (Voice) — Mock: LLM API, VOICEVOX

- LLM: use `infra/mock_llm/` (responds to requests without `tools` field)
- VOICEVOX: hard to mock (binary audio). Run actual container or skip synthesis tests.

### L4 (Dashboard) — Mock: Wallet API, MQTT

- Wallet: stub HTTP responses or let calls timeout (dashboard handles gracefully)
- MQTT: use Mosquitto or skip task report publishing

### L5 (Wallet) — Mock: nothing external

Wallet is a self-contained ledger. No outbound calls.

### L6 (Brain) — Mock: LLM, Dashboard, Voice, MQTT, Edge (MCP)

- LLM: use `infra/mock_llm/` (tool-call mode: responds to requests with `tools` field)
- Dashboard: run actual backend with SQLite, or stub REST responses
- Voice: stub `/api/voice/synthesize` → `{"audio_url": "/audio/test.mp3", "text_generated": "test", "duration_seconds": 1.0}`
- MQTT: use local Mosquitto + virtual edge
- Full integration: `python3 infra/tests/integration/integration_test_mock.py`

### L7 (Infra) — Mock: nothing

Infra testing is `docker compose config` + service boot checks.

### L8 (Docs) — Mock: nothing

Documentation only. Verify links and technical accuracy.
