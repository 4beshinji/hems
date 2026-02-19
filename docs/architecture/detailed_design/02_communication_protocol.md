# 02. Communication Protocol (MCP over MQTT)

## 1. Protocol Rationale
The core of SOMS is the **Model Context Protocol (MCP)**, adapted to run over **MQTT** for the following reasons:
- **Asynchronicity**: Decouples the slow cognitive processes of the LLM (seconds) from the fast physical world (milliseconds).
- **Resilience**: MQTT's QoS and LWT (Last Will and Testament) ensure reliable delivery on unstable Wi-Fi.
- **Lightweight**: Low overhead suitable for ESP32 microcontrollers.
- **Topology**: Hub-and-Spoke model aligns with Central Intelligence → Multiple Edge Agents architecture.

## 2. Topic Taxonomy

### 2.1 Sensor Telemetry
Per-channel publishing with `{"value": X}` JSON payload:

```
office/{zone}/sensor/{device_id}/{channel}
  e.g. office/main/sensor/env_01/temperature
  Payload: {"value": 24.5}
```

### 2.2 SensorSwarm (Hub-forwarded)
Hub devices forward Leaf sensor data using dot-separated device IDs:

```
office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}
  e.g. office/main/sensor/swarm_hub_01.leaf_env_01/temperature
  Payload: {"value": 24.5}
```

### 2.3 Camera & Activity
```
office/{zone}/camera/{camera_id}/status
office/{zone}/activity/{monitor_id}
```

**Known issue** (H-2): Perception monitors publish to 3-part topics (e.g. `office/{zone}/activity`) but WorldModel expects 5-part topics (`office/{zone}/{type}/{id}/{channel}`).

### 2.4 MCP Control (JSON-RPC 2.0)
```
mcp/{agent_id}/request/{method}     # LLM → Edge
mcp/{agent_id}/response/{request_id} # Edge → LLM
```

### 2.5 Heartbeat
```
{topic_prefix}/heartbeat    # 60-second interval
```

### 2.6 Brain Subscriptions
Brain subscribes to: `office/#`, `hydro/#`, `aqua/#`, and `mcp/+/response/#`.

## 3. MCP Payload Structure (JSON-RPC 2.0)

### Tool Execution Request
**Topic**: `mcp/esp32_01/request/call_tool`
```json
{
  "jsonrpc": "2.0",
  "method": "call_tool",
  "params": {
    "name": "set_led_color",
    "arguments": {"r": 255, "g": 0, "b": 0}
  },
  "id": "req-uuid-456"
}
```

### Tool Execution Response
**Topic**: `mcp/esp32_01/response/req-uuid-456`
```json
{
  "jsonrpc": "2.0",
  "result": {"status": "ok", "message": "LED color set to Red"},
  "id": "req-uuid-456"
}
```

## 4. SensorSwarm Binary Protocol

Hub-Leaf communication uses a compact binary protocol (not MQTT) for low-power, low-latency mesh networking.

### Frame Format (5-245 bytes)
```
| MAGIC (0x53) | VERSION | MSG_TYPE | LEAF_ID | PAYLOAD_LEN | PAYLOAD... | XOR_CHECKSUM |
|   1 byte     | 1 byte  |  1 byte  | 1 byte  |   1 byte    |  0-240B    |    1 byte    |
```

### Message Types
| Type | Value | Direction | Description |
|------|-------|-----------|-------------|
| SENSOR_REPORT | 0x01 | Leaf → Hub | Sensor telemetry data |
| HEARTBEAT | 0x02 | Leaf → Hub | Periodic liveness signal |
| REGISTER | 0x04 | Leaf → Hub | Initial registration |
| COMMAND | 0x05 | Hub → Leaf | Control command |
| ACK | 0x06 | Both | Acknowledgement |
| WAKE / WAKE_NOTIFY | 0x07 / 0x03 | Hub ↔ Leaf | Wake-up signals |
| CONFIG | 0x08 | Hub → Leaf | Configuration update |
| TIME_SYNC | 0x09 | Hub → Leaf | Time synchronization |

### Transport Layers
| Transport | Hardware | Range | Power | Status |
|-----------|----------|-------|-------|--------|
| ESP-NOW | ESP32 (Wi-Fi radio) | ~200m outdoor | Medium | Implemented |
| UART | Any (wired) | Cable length | Low | Implemented |
| I2C | ATtiny85/84 (<2KB RAM) | ~1m | Very Low | Implemented |
| BLE | ESP32 (BLE radio) | ~50m | Low | Stub only |

The Hub translates binary Leaf messages into standard MQTT telemetry (`{"value": X}`) for WorldModel consumption. Device IDs use dot notation: `swarm_hub_01.leaf_env_01`.

## 5. Python MCP Bridge Architecture

The **MCP Bridge** (`services/brain/src/mcp_bridge.py`) manages translation between the LLM's async function calls and the MQTT bus.

### Core Components
1. **MQTT Client** (`paho-mqtt >=2.0`): Connection to Mosquitto broker.
2. **Pending Request Map**: Dictionary mapping `request_id` → `asyncio.Future`.
3. **Tool Registry** (`tool_registry.py`): Statically defined 5 tools in OpenAI function-calling schema.

### Request-Response Flow
1. LLM generates a `send_device_command` tool call.
2. Bridge generates unique `request_id`, creates `asyncio.Future`, stores in pending map.
3. Bridge publishes JSON-RPC request to `mcp/{agent_id}/request/call_tool`.
4. `await future` — non-blocking wait with **10-second timeout**.
5. Edge device processes command, publishes result to `mcp/{agent_id}/response/{request_id}`.
6. Bridge receives response on `mcp/+/response/#`, resolves matching Future.

## 6. Inter-Service Communication (REST)

Besides MQTT, services communicate via HTTP REST:

| Route | Direction | Purpose |
|-------|-----------|---------|
| `POST/GET/PUT /tasks` | Brain → Backend | Task CRUD |
| `POST /api/voice/announce_with_completion` | Brain → Voice | Dual voice generation |
| `POST /api/voice/synthesize` | Brain → Voice | Direct text-to-speech |
| `GET /api/voice/rejection/random` | Frontend → Voice | Rejection voice from stock |
| `POST /transactions/task-reward` | Backend → Wallet | Task reward payment (fire-and-forget) |

### nginx Reverse Proxy
The frontend nginx routes API calls to appropriate backends:

| Path | Upstream |
|------|----------|
| `/api/wallet/` | wallet:8000 |
| `/api/voice/` | voice-service:8000 |
| `/api/` | backend:8000 |
| `/audio/` | voice-service:8000 |

### Full Service Dependency Graph
```
Frontend (React 19, nginx)
  ├── → Backend (REST /api/)
  ├── → Voice Service (REST /api/voice/, /audio/)
  └── → Wallet Service (REST /api/wallet/)

Brain
  ├── → MQTT Broker (telemetry, MCP)
  ├── → Backend (REST, task CRUD)
  ├── → Voice Service (REST, announce/synthesize)
  └── → LLM (Ollama / mock-llm)

Backend
  ├── → PostgreSQL (asyncpg, tasks/users/voice_events)
  └── → Wallet Service (fire-and-forget task reward on complete)

Wallet
  ├── → PostgreSQL (asyncpg, same DB, wallet schema)
  └── → MQTT Broker (heartbeat/device tracking)

Perception
  ├── → MQTT Broker (publish detections, host network)
  └── → GPU (ROCm, YOLOv11)

Edge Devices
  └── → MQTT Broker (telemetry, MCP responses)
```

## 7. Security Status

**Current state (PoC)**:
- MQTT: `allow_anonymous true` — no authentication.
- Dashboard/API: No authentication layer.
- Network: Single Docker bridge network (`soms-net`), no VLAN isolation.
- PostgreSQL: Port 5432 exposed on all interfaces (should be `127.0.0.1:5432:5432`).

**Planned improvements** (see ISSUES.md M-1, M-2):
- MQTT username/password authentication.
- Dashboard basic auth or OAuth2.
- PostgreSQL port binding restriction.
