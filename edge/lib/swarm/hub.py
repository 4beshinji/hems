"""
SwarmHub — MicroPython hub that aggregates Leaf devices and bridges to MQTT.

Uses composition with MCPDevice (not inheritance) so existing soms_mcp.py
remains unchanged. Manages multiple transports and a Leaf registry.

Usage on ESP32:
    from soms_mcp import MCPDevice
    from swarm.hub import SwarmHub
    from swarm.transport_espnow import ESPNowTransport

    device = MCPDevice()
    hub = SwarmHub(device)
    hub.add_transport(ESPNowTransport())
    device.connect()

    while True:
        device.loop()
        hub.poll()
        time.sleep(0.1)
"""

import time
import json
import struct

try:
    from swarm.message import (
        decode, decode_sensor_report, decode_heartbeat, decode_register,
        decode_wake_notify, encode, encode_command,
        MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_WAKE_NOTIFY,
        MSG_COMMAND, MSG_ACK,
        CHANNEL_NAMES,
    )
except ImportError:
    import sys
    sys.path.insert(0, "/lib")
    from swarm.message import (
        decode, decode_sensor_report, decode_heartbeat, decode_register,
        decode_wake_notify, encode, encode_command,
        MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_WAKE_NOTIFY,
        MSG_COMMAND, MSG_ACK,
        CHANNEL_NAMES,
    )


class SwarmHub:
    """
    Aggregates Leaf sensor data from multiple transports and publishes
    per-channel MQTT through the parent MCPDevice.
    """

    def __init__(self, mcp_device, wake_chains=None):
        """
        mcp_device: MCPDevice instance (already configured with WiFi/MQTT)
        wake_chains: dict like {"leaf_pir_01": {"wakes": "leaf_cam_01", "gpio": 5}}
        """
        self.device = mcp_device
        self.transports = []
        self.wake_chains = wake_chains or {}

        # Leaf registry: leaf_id(int) -> {name, hw_type, caps, last_seen, battery_mv, transport_idx}
        self._leafs = {}

        # Register MCP tools on the parent device
        self.device.register_tool("leaf_command", self.leaf_command)
        self.device.register_tool("get_swarm_status", self.get_swarm_status)

    def add_transport(self, transport):
        """Add a transport (ESPNowTransport, UARTTransport, etc.)."""
        idx = len(self.transports)
        self.transports.append(transport)
        return idx

    # ── Main poll ────────────────────────────────────────────

    def poll(self):
        """
        Poll all transports for incoming Leaf messages, decode them,
        and publish to MQTT. Call this in the main loop.
        """
        for idx, transport in enumerate(self.transports):
            while True:
                result = transport.receive()
                if result is None:
                    break
                addr, raw = result
                self._process_message(addr, raw, idx)

    # ── Message processing ───────────────────────────────────

    def _process_message(self, addr, raw, transport_idx):
        try:
            msg_type, leaf_id, payload = decode(raw)
        except ValueError as e:
            print(f"[SwarmHub] Bad frame from {addr}: {e}")
            return

        if msg_type == MSG_REGISTER:
            self._handle_register(leaf_id, payload, transport_idx, addr)
        elif msg_type == MSG_SENSOR_REPORT:
            self._handle_sensor_report(leaf_id, payload)
        elif msg_type == MSG_HEARTBEAT:
            self._handle_heartbeat(leaf_id, payload)
        elif msg_type == MSG_WAKE_NOTIFY:
            self._handle_wake_notify(leaf_id, payload)
        elif msg_type == MSG_ACK:
            pass

    def _leaf_name(self, leaf_id):
        entry = self._leafs.get(leaf_id)
        if entry:
            return entry.get("name", "leaf_%d" % leaf_id)
        return "leaf_%d" % leaf_id

    def _handle_register(self, leaf_id, payload, transport_idx, addr):
        info = decode_register(payload)
        name = "leaf_%d" % leaf_id
        self._leafs[leaf_id] = {
            "name": name,
            "hw_type": info["hw_type"],
            "capabilities": info["capabilities"],
            "last_seen": time.time(),
            "battery_mv": 0,
            "transport_idx": transport_idx,
            "addr": addr,
        }
        print("[SwarmHub] Registered leaf %d (%s) hw=%s caps=%s" % (
            leaf_id, name, info["hw_type"], info["capabilities"]))

    def _handle_sensor_report(self, leaf_id, payload):
        channels = decode_sensor_report(payload)
        leaf_name = self._leaf_name(leaf_id)
        device_id = "%s.%s" % (self.device.device_id, leaf_name)

        # Publish each channel as per-channel MQTT
        for channel, value in channels.items():
            topic = "office/%s/sensor/%s/%s" % (self.device.zone, device_id, channel)
            self.device.client.publish(topic, json.dumps({"value": value}))

        if leaf_id in self._leafs:
            self._leafs[leaf_id]["last_seen"] = time.time()
            self._leafs[leaf_id]["last_data"] = channels

    def _handle_heartbeat(self, leaf_id, payload):
        hb = decode_heartbeat(payload)
        if leaf_id in self._leafs:
            self._leafs[leaf_id]["battery_mv"] = hb["battery_mv"]
            self._leafs[leaf_id]["last_seen"] = time.time()

    def _handle_wake_notify(self, leaf_id, payload):
        woken_id = decode_wake_notify(payload)
        print("[SwarmHub] Leaf %d woke leaf %d" % (leaf_id, woken_id))

    # ── MCP Tools ────────────────────────────────────────────

    def leaf_command(self, leaf_id, command, args=None):
        """Send command to a Leaf. Called via MCP from Brain."""
        # Find leaf by name or int ID
        target_id = None
        for lid, info in self._leafs.items():
            if info.get("name") == leaf_id or str(lid) == str(leaf_id):
                target_id = lid
                break
        if target_id is None:
            return {"error": "unknown leaf: %s" % leaf_id}

        cmd_map = {
            "set_state": 0x01, "set_pwm": 0x02, "read_now": 0x03,
            "set_interval": 0x04, "deep_sleep": 0x05, "reset": 0x06,
        }
        cmd_id = cmd_map.get(command)
        if cmd_id is None:
            return {"error": "unknown command: %s" % command}

        arg_bytes = b""
        if args:
            if command == "set_state":
                val = 1 if args.get("state") in ("on", True, 1) else 0
                arg_bytes = struct.pack("B", val)
            elif command == "set_pwm":
                arg_bytes = struct.pack("<H", int(args.get("duty", 0)))
            elif command == "set_interval":
                arg_bytes = struct.pack("<H", int(args.get("seconds", 30)))
            elif command == "deep_sleep":
                arg_bytes = struct.pack("<I", int(args.get("wake_after_ms", 60000)))

        cmd_payload = encode_command(cmd_id, arg_bytes)
        frame = encode(MSG_COMMAND, target_id, cmd_payload)

        # Send via the transport the leaf registered on
        leaf_info = self._leafs[target_id]
        tidx = leaf_info.get("transport_idx", 0)
        addr = leaf_info.get("addr")
        if tidx < len(self.transports):
            self.transports[tidx].send(addr, frame)

        return {"status": "sent", "leaf_id": leaf_id, "command": command}

    def get_swarm_status(self):
        """Return status of all registered Leaves."""
        now = time.time()
        leaves = []
        for lid, info in self._leafs.items():
            age = now - info.get("last_seen", 0)
            entry = {
                "leaf_id": lid,
                "name": info.get("name", "leaf_%d" % lid),
                "hw_type": info["hw_type"],
                "capabilities": info["capabilities"],
                "battery_mv": info.get("battery_mv", 0),
                "last_seen_sec_ago": int(age),
                "online": age < 120,
            }
            batt = info.get("battery_mv", 0)
            if 0 < batt < 2400:
                entry["warning"] = "low_battery"
            leaves.append(entry)
        return {
            "hub_id": self.device.device_id,
            "leaf_count": len(leaves),
            "leaves": leaves,
        }
