# 05. Edge Engineering (ESP32 & SensorSwarm)

## 1. Overview
The Edge Layer consists of distributed microcontrollers that act as the "hands and eyes" of the system, bridging digital commands from the LLM to the physical world. The primary architecture is the **SensorSwarm** 2-tier Hub-Leaf network, complemented by standalone legacy devices.

## 2. SensorSwarm Architecture (`edge/swarm/`, `edge/lib/swarm/`)

### 2.1 Hub-Leaf 2-Tier Design
```
                    ┌────────────────────────┐
                    │   MQTT Broker          │
                    │   (Mosquitto)          │
                    └──────────┬─────────────┘
                               │ WiFi + MQTT
                    ┌──────────┴─────────────┐
                    │   SwarmHub             │
                    │   (ESP32 w/ WiFi)      │
                    │   hub.py               │
                    └──┬─────┬─────┬─────────┘
                       │     │     │
              ESP-NOW  │ UART│  I2C│
                       │     │     │
                    ┌──┘  ┌──┘  ┌──┘
                    ▼     ▼     ▼
                  Leaf  Leaf  Leaf
                  (C6)  (Pico) (ATtiny)
```

- **Hub**: ESP32 with WiFi + MQTT connectivity. Aggregates Leaf data and forwards to MQTT broker.
- **Leaf**: Low-power sensor nodes that communicate with Hub via one of 4 transport layers.
- **Device ID**: Dot notation — `swarm_hub_01.leaf_env_01` — allows WorldModel to parse without modification.

### 2.2 Binary Protocol
Hub-Leaf communication uses a compact binary protocol (5-245 bytes):

```
| MAGIC (0x53) | VERSION | MSG_TYPE | LEAF_ID | PAYLOAD_LEN | PAYLOAD... | XOR_CHECKSUM |
|   1 byte     | 1 byte  |  1 byte  | 1 byte  |   1 byte    |  0-240B    |    1 byte    |
```

Message types: SENSOR_REPORT, HEARTBEAT, REGISTER, COMMAND, ACK, WAKE, WAKE_NOTIFY, CONFIG, TIME_SYNC.

### 2.3 Transport Layers

| Transport | Hardware | Range | Power | Status | Directory |
|-----------|----------|-------|-------|--------|-----------|
| ESP-NOW | ESP32-C6 (Wi-Fi radio) | ~200m outdoor | Medium | Implemented | `edge/swarm/leaf-espnow/` |
| UART | Raspberry Pi Pico (wired) | Cable length | Low | Implemented | `edge/swarm/leaf-uart/` |
| I2C | ATtiny85/84 (<2KB RAM) | ~1m | Very Low | Implemented | `edge/swarm/leaf-arduino/` |
| BLE | ESP32 (BLE radio) | ~50m | Low | Stub only | `edge/lib/swarm/transport_ble.py` |

### 2.4 Hub Firmware (`edge/swarm/hub-node/`)
- MicroPython on ESP32 with WiFi
- Connects to MQTT broker on boot
- Listens on configured transports for Leaf messages
- Translates binary sensor reports → MQTT telemetry (`{"value": X}`)
- Handles Leaf registration, heartbeat tracking, and command forwarding

### 2.5 Shared Library (`edge/lib/swarm/`)
- `message.py`: Binary protocol encoder/decoder
- `hub.py`: Hub base class with transport management
- `leaf.py`: Leaf base class with sensor reporting
- `transport_espnow.py`, `transport_uart.py`, `transport_i2c.py`, `transport_ble.py`: Transport implementations

### 2.6 MCP Tools for SensorSwarm
Brain can interact with SensorSwarm via `send_device_command`:
- `leaf_command`: Send command to a specific Leaf via Hub
- `get_swarm_status`: Query Hub for connected Leaf status, battery levels

### 2.7 Virtual Emulator
`infra/virtual_edge/` provides a SwarmHub + 3 Leaf virtual emulator for testing without hardware:
- Generates realistic sensor telemetry (temperature, humidity, CO2, motion, door events)
- Docker: `edge/lib` mounted to `/edge_lib` volume (`docker-compose.edge-mock.yml`)

## 3. Legacy Standalone Devices

### 3.1 MicroPython Firmware (`edge/office/`)
Production firmware for standalone ESP32 devices:

| Directory | Hardware | Sensors |
|-----------|----------|---------|
| `edge/office/sensor-01/` | ESP32 | BME680 (temp/hum/gas), MH-Z19C (CO2) |
| `edge/office/sensor-02/` | ESP32 | BME680, MH-Z19C drivers |

Architecture:
1. Boot → WiFi connect → MQTT connect → Subscribe `mcp/{my_id}/request/#`
2. Main loop: Read sensors → Publish telemetry → Handle MCP commands
3. Shared MCP library: `edge/lib/soms_mcp.py`

### 3.2 PlatformIO C++ Firmware (`edge/test-edge/`)

| Directory | Hardware | Purpose |
|-----------|----------|---------|
| `edge/test-edge/camera-node/` | ESP32-CAM | Camera capture + RTSP streaming |
| `edge/test-edge/sensor-node/` | ESP32 | Sensor reading + MCP |

### 3.3 Sensor Catalog (Implemented)
- **Environmental**: BME680 (temp/hum/gas/pressure), MH-Z19C (CO2), DHT22 (temp/hum)
- **Occupancy**: PIR motion sensors → `pir_detected` + `occupancy` channels
- **Door**: Magnetic reed switches → event generation
- **Visual**: OV2640 (ESP32-CAM)

## 4. Diagnostic Tools (`edge/tools/`)
13 diagnostic scripts including:
- `blink_identify.py`: LED identification for physical device location
- `diag_i2c.py`: I2C bus scanner
- `test_uart.py`: UART communication tester
- `clean_scan.py`: Network scan utility

## 5. MQTT Telemetry Format
All edge devices publish per-channel telemetry:
```
Topic:   office/{zone}/sensor/{device_id}/{channel}
Payload: {"value": X}
```

Channels include: `temperature`, `humidity`, `co2`, `pressure`, `gas_resistance`, `pir_detected`, `occupancy`, `door`.

Heartbeat: `{topic_prefix}/heartbeat` every 60 seconds.

## 6. Deployment Notes

### Power & Connectivity
- **Hub nodes**: USB power + WiFi
- **Leaf nodes**: Battery or USB, communicate via transport to nearest Hub
- **Standalone**: USB adapters, direct WiFi to MQTT broker

### Docker Integration
- `docker-compose.edge-mock.yml`: Virtual edge emulator (3 services)
- `edge/lib` is tracked in git (`.gitignore` has `!edge/lib/`)
- Bind-mounted as `/edge_lib` in Docker for virtual edge access

## 7. Future Work
- **BLE Transport**: Complete implementation for nRF54L15 targets (D.2)
- **OTA Updates**: Firmware over-the-air update mechanism (D.4)
- **Sub-GHz (LoRa)**: Long-range transport for outdoor/building-scale (D.5)
- **Node Mass Production**: Config-based device provisioning (D.6)
- **Hub-to-Hub**: Inter-hub communication protocol for multi-zone (G.3)

See `edge/swarm/README.md` for SensorSwarm-specific documentation.
