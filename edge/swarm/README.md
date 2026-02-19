# SensorSwarm

2-tier sensor network for SOMS: low-cost battery-powered **Leaf** devices communicate with a WiFi+MQTT **Hub** that bridges data to the Brain.

## Architecture

```
Brain (LLM) ← MQTT → Hub (ESP32) ← ESP-NOW/UART/I2C/BLE → Leaf devices
```

- **Hub**: WiFi+MQTT connected ESP32, aggregates Leaf data, publishes per-channel MQTT
- **Leaf**: No WiFi needed. Battery-powered sensors/actuators (ESP32-C3, ATtiny, Pi Pico, nRF54)
- **Zero Brain changes**: device_id = `hub_01.leaf_env_01` passes through WorldModel as-is

## Binary Protocol

Lightweight binary frames (5–245 bytes) fit ESP-NOW's 250B limit and run on ATtiny (2KB RAM).

```
[Magic 0x53][Version][MsgType][LeafID][Payload...][XOR Checksum]
```

Message types: SENSOR_REPORT, HEARTBEAT, REGISTER, COMMAND, ACK, WAKE, CONFIG, TIME_SYNC

Codec: `edge/lib/swarm/message.py` (pure Python, MicroPython compatible)

## MQTT Topics

Hub publishes Leaf data in existing per-channel format:
```
office/{zone}/sensor/{hub_id}.{leaf_name}/{channel} → {"value": X}
```

MCP commands to Hub control Leaves:
```json
{"method": "call_tool", "params": {"name": "leaf_command", "arguments": {"leaf_id": "leaf_relay_01", "command": "set_state", "args": {"state": "on"}}}}
```

## Directory Structure

```
edge/lib/swarm/          # Shared MicroPython library
  message.py             # Binary codec (all platforms)
  hub.py                 # SwarmHub class (composition with MCPDevice)
  leaf.py                # SwarmLeaf base class
  transport_espnow.py    # ESP-NOW transport
  transport_uart.py      # UART transport (frame sync)
  transport_i2c.py       # I2C master transport
  transport_ble.py       # BLE transport (stub)

edge/swarm/              # Device firmware
  hub-node/              # Hub: ESP32-S3/C6 (MicroPython)
  leaf-espnow/           # Leaf: ESP32-C3/C6 via ESP-NOW
  leaf-uart/             # Leaf: Pi Pico via UART
  leaf-arduino/          # Leaf: ATtiny (I2C, C++), nRF54 (BLE, stub)

infra/virtual_edge/src/  # Virtual emulator
  swarm_transport.py     # In-memory transport
  swarm_leaf.py          # Virtual leaves (TempHumidity, PIR, Door, Relay)
  swarm_hub.py           # Virtual hub (extends VirtualDevice)
```

## Virtual Emulator

Runs with `docker compose -f infra/docker-compose.edge-mock.yml up`. The virtual edge
automatically starts a SwarmHub with 3 leaves (env, PIR, door sensor).

Verify:
```bash
mosquitto_sub -t "office/main/sensor/swarm_hub_01.#" -v
```

## Transports

| Transport | Leaf Platform | Range | Power | Status |
|-----------|--------------|-------|-------|--------|
| ESP-NOW   | ESP32-C3/C6  | ~200m | Low   | Implemented |
| UART      | Pi Pico      | Wired | N/A   | Implemented |
| I2C       | ATtiny       | Wired | Minimal | Implemented |
| BLE       | nRF54L15     | ~100m | Very low | Stub |

## MCP Tools

Hub exposes two tools to Brain via MCP:

- `leaf_command(leaf_id, command, args)` — Send command to a Leaf (set_state, read_now, set_interval, etc.)
- `get_swarm_status()` — Get all Leaf status (battery, last_seen, capabilities)
