# services/backend/

Backend REST API (FastAPI + SQLAlchemy async) — task/voice/stats persistence plus three cross-cutting subsystems that span brain + frontend: the unified Device Registry, the Shopping List, and the Chat REST router.

Extends the parent `hems/CLAUDE.md` (entry, build/run, MQTT topics, ports). Read that first if you haven't. Brain-side device tools and the brain chat server are documented in `services/brain/CLAUDE.md` — this file is the backend (persistence + HTTP) side.

## Device Registry (Unified sensor + actuator 管理)

すべてのセンサー/アクチュエータを `Device` テーブル1本で管理。ベンダー(zigbee/switchbot/tapo/ha/mcp)は属性。

- **自動登録**: Brain が MQTT (office/sensor, hems/home, hems/switchbot, hems/tapo, zigbee2mqtt) を監視、
  未知の device_id を検出したら backend `/devices/heartbeat` で自動作成。
- **メタデータ編集**: `/devices` ページで `display_name / zone / location / purpose / description` を編集
- **用途(purpose)**: LLM が用途理解でツール選択に使う重要フィールド (例: "水やりポンプ", "起床補助ライト")
- **Backend `/devices/`**: CRUD + heartbeat + `{id}/control` プロキシ
- **Safety**: action allowlist (sanitizer), pulse duration_s ≤ 600s, brightness 0-255, color_temp 153-500
- **LLM ツール** (ベンダー非依存, brain 側): `control_actuator` / `list_devices` / `describe_device` — 定義は `services/brain/CLAUDE.md`
- **dispatcher**: `brain/src/device_dispatcher.py` — `vendor` でハブ別ディスパッチ (ha-bridge / switchbot-bridge / tapo-bridge / zigbee2mqtt MQTT)

## Shopping List

Built-in shopping list with brain integration.

- **Backend**: CRUD API for shopping items with purchase history
- **Database**: `ShoppingItem`, `PurchaseHistory` models
- **MQTT**: `hems/shopping/{added,updated,purchased,deleted}` (per-event) + `hems/shopping/list` (full pending snapshot, published on every mutation)
- **World model**: `ShoppingState` is rebuilt from the `hems/shopping/list` snapshot by `digital_updates._update_shopping_state`, so the recurring-due / departure reminder rules read live data. Per-event topics still feed brain_mqtt → ShoppingClassifier + event_store; backend DB remains the source of truth (see IMPLEMENTATION_MAP §5)
- **Brain tools/rules**: `add_shopping_item`, `get_shopping_list` (always-on) + recurring-due / departure reminders — see `services/brain/CLAUDE.md`

## Chat (backend side)

Interactive chat with the AI character via the dashboard. The backend persists and proxies; the brain runs the actual chat ReAct loop.

- **Backend chat router**: `/chat/` REST API — message persistence (Conversation/Message tables), Brain proxy, optional TTS
  - Sliding window: last 20 messages sent to Brain as conversation context
  - Auto-TTS: responses under 100 chars are synthesized via voice-service
- **Brain chat server** (`services/brain/CLAUDE.md`): internal aiohttp server, separate read-only ReAct loop (max 3 iterations)
- **Frontend ChatPanel**: unified timeline (chat + voice events), text input + STT, optimistic UI, AudioQueue playback
