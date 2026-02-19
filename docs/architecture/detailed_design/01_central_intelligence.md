# 01. Central Intelligence & LLM Strategy

## 1. Overview
The **Central Intelligence Layer** acts as the "brain" of the Symbiotic Office Management System (SOMS). Unlike traditional rule-based Building Management Systems (BMS), SOMS utilizes a Large Language Model (LLM) to perform context-aware decision-making, natural language processing, and complex task planning.

## 2. Infrastructure & Hardware

### 2.1 Server Specifications
- **GPU**: AMD Radeon RX 9700 (RDNA4, 16GB VRAM)
  - Uses the **ROCm** open-source GPU compute stack.
  - `HSA_OVERRIDE_GFX_VERSION=12.0.1` for RDNA4 compatibility.
  - **Important**: Only the dGPU (`/dev/dri/card1`, `/dev/dri/renderD128`) is passed to Docker. Passing the entire `/dev/dri` causes iGPU reset and GNOME crashes.
- **CPU**: AMD Ryzen (with Raphael iGPU on a separate render node for display).
- **RAM**: 64GB+ system RAM.
- **Storage**: NVMe SSD.

### 2.2 Distributed Topology
The system uses **MQTT** for loose coupling. The "Central Intelligence" is a logical role, not a specific machine.
- **Current**: Single-server deployment running all services via Docker Compose.
- **Future**: Nodes can be physically separated — Brain, Perception, and Dashboard each as independent hosts communicating over MQTT/HTTP.

## 3. Model Architecture

### 3.1 Model Selection: Qwen2.5:14b
We use **Qwen2.5:14b** with Q4_K_M quantization, running on **Ollama** with ROCm support.

- **Instruction Following**: Superior performance in structured output (JSON) and tool-calling schemas.
- **Coding & Logic**: High capabilities in logical reasoning, essential for valid tool calls.
- **Multilingual Support**: Strong Japanese + English performance for bilingual office environment.
- **Context Window**: Large context for sensor logs and conversation history.
- **Efficiency**: 14B with 4-bit quantization fits comfortably in 16GB VRAM.

### 3.2 Inference Engine: Ollama
- **Image**: `ollama/ollama:rocm` Docker image.
- **API**: OpenAI-compatible REST API at port 11434.
- **Model Management**: `ollama pull qwen2.5:14b` downloads and manages model weights.
- **Volume**: `ollama_models:/root/.ollama` for persistent model storage.
- **Host Access**: Services connect via `http://ollama:11434/v1` (Docker internal) or `http://host.docker.internal:11434/v1` (host Ollama).

### 3.3 Mock LLM (Development/Testing)
A keyword-based LLM simulator (`infra/mock_llm/`) provides an OpenAI-compatible API for testing without GPU.
- **Dual-mode**: When `tools` are present in the request → generates tool calls (Brain mode); when absent → generates natural text (Voice text generation mode).
- **Keyword matching**: temperature/CO2/supply keywords trigger corresponding tool calls.

## 4. Cognitive Architecture

### 4.1 ReAct Loop (Think → Act → Observe)
The Brain service (`services/brain/src/main.py`) implements a ReAct cognitive loop:

1. **Event Trigger**: MQTT event (3s batch delay) or 30s polling interval.
2. **Context Assembly**: WorldModel state + active tasks injected into LLM context.
3. **Think**: LLM analyzes the situation.
4. **Act**: LLM generates tool calls using OpenAI function-calling format.
5. **Observe**: Tool execution results are fed back to LLM.
6. **Iterate**: Up to 5 iterations per cycle.

### 4.2 Constitutional AI & System Prompt
The system prompt (`src/system_prompt.py`) defines behavioral constraints:

1. **Safety First**: Never execute actions that could harm humans or equipment.
2. **Cost Awareness**: Budget consciousness for credit spending.
3. **Duplicate Prevention**: Check active tasks before creating new ones.
4. **Graduated Response**: Escalate interventions gradually.
5. **Privacy**: Do not describe individuals' personal activities.
6. **Normal State Silence**: Do not use `speak` tool when all readings are normal.

### 4.3 Tool Definitions (OpenAI Function-Calling)
5 tools are defined in `src/tool_registry.py` using OpenAI function-calling schema:

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `create_task` | Create human task with bounty | title, description, bounty (500-5000), urgency (0-4), zone |
| `send_device_command` | Control edge device via MCP | agent_id, tool_name, arguments (JSON) |
| `get_zone_status` | Query WorldModel for zone state | zone_id |
| `speak` | Ephemeral voice announcement | message (70 chars max), zone, tone |
| `get_active_tasks` | List active tasks (duplicate prevention) | — |

### 4.4 Input Validation (Sanitizer)
`src/sanitizer.py` intercepts every tool call before execution:
- **Range Checks**: Temperature 18-28°C, pump max 60s.
- **Rate Limiting**: Max 10 task creations per hour.
- **Parameter Validation**: Bounty range, urgency range, string length limits.
- **Known issue** (H-5): Rate limit timestamps are recorded before validation success, wasting valid creation slots.

## 5. Supporting Modules

### 5.1 WorldModel (`src/world_model/`)
- `world_model.py`: Unified zone state from MQTT telemetry. Parses topic structure (`office/{zone}/{device_type}/{device_id}/{channel}`), detects 8 event types (CO2 threshold, temperature spike, prolonged sitting, door open/close, etc.).
- `data_classes.py`: Pydantic models — EnvironmentData, OccupancyData, DeviceState, Event, ZoneState.
- `sensor_fusion.py`: Exponential decay weighted fusion (temperature half-life 2min, CO2 1min, occupancy 30s).
- **Known issue** (H-1): Perception publishes `"count"` but WorldModel expects `"person_count"`.
- **Known issue** (H-2): Perception uses 3-part MQTT topics but WorldModel parser expects 5-part.

### 5.2 Task Scheduling (`src/task_scheduling/`)
- `queue_manager.py`: Min-heap task queue, 24h forced dispatch.
- `decision.py`: Dispatch decisions based on urgency, zone activity, occupancy, time of day, focus level.
- `priority.py`: Priority scoring — urgency×1000 + wait time + deadline bonus.

### 5.3 Dashboard Client (`src/dashboard_client.py`)
REST client for the Dashboard Backend API. Handles task CRUD and triggers dual voice generation (announcement + completion) via Voice Service.
- **Known issue** (H-3): No null check on voice generation failure — audio URLs can be None if Voice Service is down.

### 5.4 Task Reminder (`src/task_reminder.py`)
Re-announces pending tasks after 1 hour of inactivity. 30-minute cooldown between reminders. 5-minute check interval. Generates fresh announcement voice (not a shortened "reminder" message).

### 5.5 MCP Bridge (`src/mcp_bridge.py`)
MQTT ↔ JSON-RPC 2.0 translation. Uses `asyncio.Future` for request-response correlation with 10s timeout.
- **Known issue** (H-4): `request_id` matching logic overwrites topic-extracted ID with payload ID — potential mismatch risk.

### 5.6 LLM Client (`src/llm_client.py`)
Async OpenAI-compatible API wrapper using aiohttp. 120s timeout for LLM inference calls.

## 6. Service Dependencies

```
Brain
  ├── → MQTT Broker (paho-mqtt, subscribe: office/#, hydro/#, aqua/#, mcp/+/response/#)
  ├── → Dashboard Backend (REST: POST/GET/PUT /tasks)
  ├── → Voice Service (REST: POST /api/voice/announce_with_completion, /synthesize)
  └── → LLM (Ollama or mock-llm, OpenAI-compatible API)
```
