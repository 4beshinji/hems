# 04. Credit Economy & Dashboard

## 1. Concept: Human-in-the-Loop (HITL) as a Service
SOMS acknowledges that not all office tasks can be automated by robots. The credit economy bridges this "last mile" by incentivizing humans to perform physical actions (e.g., closing windows, refilling coffee beans) through a bounty system.

## 2. Economic Model

### 2.1 Double-Entry Ledger
The Wallet Service (`services/wallet/`) implements a **double-entry bookkeeping** system:
- **System Wallet** (user_id=0): Issues credits. Allowed negative balance.
- **User Wallets**: Receive bounty on task completion. Cannot go negative.
- **Transactions**: Every transfer creates paired DEBIT + CREDIT ledger entries with a shared `transaction_id`.
- **Idempotency**: `reference_id` (e.g., `"task:42"`) prevents double payments.
- **Deadlock Prevention**: Wallet IDs are locked in ascending order (`FOR UPDATE`).

### 2.2 Bounty System
LLM Brain sets bounty dynamically via `create_task` tool:

| Difficulty | Bounty Range |
|-----------|-------------|
| Easy (coffee refill, etc.) | 500 - 1,000 |
| Medium (printer repair, etc.) | 1,000 - 2,000 |
| Heavy (deep cleaning, etc.) | 2,000 - 5,000 |

### 2.3 Device XP
Devices accumulate XP when tasks are created/completed in their zone:
- Task creation: +10 XP per device in zone
- Task completion: +20 XP per device in zone
- Dynamic reward multiplier: `1.0 + (xp/1000) * 0.5` (cap 3.0x)
- Zone matching: `topic_prefix LIKE 'office/{zone}/%'`

For full details, see `docs/CURRENCY_SYSTEM.md`.

## 3. Dashboard Infrastructure

### 3.1 Technology Stack
- **Frontend**: React 19 + TypeScript 5.9 + Vite 7.3 + Tailwind CSS 4 + Framer Motion 12 + Lucide Icons
- **Backend**: Python FastAPI (async) + SQLAlchemy + asyncpg
- **Database**: PostgreSQL 16 (Docker) with SQLite (aiosqlite) fallback
- **Real-time**: HTTP polling (tasks: 5s, voice events: 3s, wallet: 10s)
- **Voice**: VOICEVOX integration for audio announcements

### 3.2 nginx Reverse Proxy
Frontend nginx routes API calls to services:

| Path | Upstream |
|------|----------|
| `/` | SPA (index.html) |
| `/api/wallet/` | wallet:8000 |
| `/api/voice/` | voice-service:8000 |
| `/api/` | backend:8000 |
| `/audio/` | voice-service:8000 |

### 3.3 Design System
Material Design 3 Light Theme with 50+ CSS variables, Inter / JetBrains Mono fonts.

## 4. Data Models

### 4.1 Task Model (Dashboard Backend, 19 columns)
Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer (PK, auto) | Task ID |
| `title` | String | Task title |
| `description` | Text | Detailed description |
| `bounty_gold` | Integer (default 10) | Credit reward |
| `bounty_xp` | Integer (default 50) | System XP reward |
| `urgency` | Integer (0-4) | 0=low, 4=critical |
| `zone` | String | Zone identifier |
| `task_type` | String | Task category |
| `is_completed` | Boolean | Completion flag |
| `is_queued` | Boolean | Queue status |
| `assigned_to` | Integer | Accepted user ID |
| `accepted_at` | DateTime | Acceptance timestamp |
| `dispatched_at` | DateTime | Dispatch timestamp |
| `announcement_audio_url` | String | Pre-generated voice URL |
| `completion_audio_url` | String | Pre-generated completion voice URL |
| `last_reminded_at` | DateTime | Last reminder timestamp |

### 4.2 Task Duplicate Detection (2-stage)
1. **Stage 1**: Title + location exact match against active tasks
2. **Stage 2**: Zone + task_type overlap detection (handles LLM wording variation)

### 4.3 User Model (Dashboard Backend)
- `id`, `username`, `credits`
- **Note**: `users.py` router is currently a stub with hardcoded mock data. DB integration pending (see TASK_SCHEDULE.md C.1).
- `credits` field is legacy — Wallet Service `balance` is the authoritative source.

### 4.4 Wallet Data Models (Wallet Service, PostgreSQL)
- `Wallet`: user_id, balance
- `LedgerEntry`: transaction_id, wallet_id, amount, entry_type (DEBIT/CREDIT), reference_id
- `Device`: device_id, xp, topic_prefix, is_active
- `RewardRate`: device_type, rate_per_hour
- `SupplyStats`: total_issued, total_burned, circulating (singleton)

## 5. Frontend Components

### 5.1 Core Components
| Component | File | Description |
|-----------|------|-------------|
| `App.tsx` | 340 lines | Main dashboard: 3-column grid, task/voice polling |
| `TaskCard.tsx` | 153 lines | Task card: accept→working→complete state machine, urgency colors |
| `UserSelector.tsx` | 50 lines | User selection dropdown |
| `WalletBadge.tsx` | 39 lines | Credit balance badge (10s polling) |
| `WalletPanel.tsx` | 60 lines | Transaction history slide-in panel |

### 5.2 UI Components
| Component | Description |
|-----------|-------------|
| `Button.tsx` | 4 variants, Framer Motion animations |
| `Card.tsx` | 4 elevation levels |
| `Badge.tsx` | 7 variants (success/warning/error/gold/xp etc.) |

### 5.3 AudioQueue
Priority-based sequential audio playback (`src/audio/AudioQueue.ts`):

| Priority | Level | Use Case |
|----------|-------|----------|
| USER_ACTION | Highest | Accept/complete/ignore responses |
| ANNOUNCEMENT | Medium | New task announcements |
| VOICE_EVENT | Lowest | Ephemeral speak events |

Max queue size: 20. React integration via `useSyncExternalStore` hook.

## 6. Task Lifecycle

```
Brain: create_task(bounty=2000, urgency=3)
  → Backend: POST /tasks/ (Task record + voice generation)
  → Voice: announce_with_completion (dual MP3 generation)
  → Frontend: 5s poll detects new task, plays announcement audio

User: "受ける" (Accept)
  → Backend: PUT /tasks/{id}/accept (assigned_to, accepted_at set)
  → Frontend: synthesize accept voice (/api/voice/synthesize)

User: "完了" (Complete)
  → Backend: PUT /tasks/{id}/complete
    → Wallet: POST /transactions/task-reward (fire-and-forget)
      → System Wallet -bounty → User Wallet +bounty
    → SystemStats: tasks_completed++, total_xp += bounty_xp
  → Frontend: plays pre-generated completion audio

User: "無視" (Ignore)
  → Frontend: GET /api/voice/rejection/random (instant from stock)
  → Task remains available for other users
```

## 7. Known Issues

| ID | Issue | Impact |
|----|-------|--------|
| C-2 | Task model missing `assigned_to`/`accepted_at` columns | Accept endpoint fails with AttributeError |
| H-6 | setState in useEffect (React anti-pattern) | Cascade re-renders on initial load |
| H-7 | useEffect missing `prevTaskIds` dependency | Stale closure may miss new tasks |
| — | `users.py` is a stub | Hardcoded mock data, no DB integration |
| — | No authentication | Anyone can accept/complete tasks as any user |
| — | WalletPanel endpoint mismatch | Frontend expects `/transactions/{userId}` but API provides `/wallets/{userId}/history` |

See `ISSUES.md` for full issue list and `CURRENCY_SYSTEM.md` for detailed wallet documentation.
