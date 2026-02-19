"""
Virtual SwarmHub — aggregates VirtualSwarmLeaf data and bridges to MQTT.

Extends VirtualDevice to fit into the existing virtual_edge framework.
Decodes binary Leaf messages and publishes per-channel MQTT telemetry
using the device_id format: {hub_id}.{leaf_name}
"""

import json
import logging
import time
import sys
import os

for _p in ["/edge_lib", os.path.join(os.path.dirname(__file__), "..", "..", "..", "edge", "lib")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
from swarm.message import (
    decode, decode_sensor_report, decode_heartbeat, decode_register,
    decode_wake_notify, encode, encode_command,
    MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_WAKE_NOTIFY,
    MSG_COMMAND, MSG_ACK,
    CHANNEL_NAMES, CAPABILITY_NAMES,
)
from device import VirtualDevice

logger = logging.getLogger(__name__)


class VirtualSwarmHub(VirtualDevice):
    """
    SwarmHub that lives inside the virtual_edge process.

    - Receives binary frames from VirtualSwarmLeaf via VirtualTransport.
    - Decodes them and publishes per-channel MQTT.
    - Exposes MCP tools: leaf_command, get_swarm_status.
    """

    def __init__(self, hub_id, zone, mqtt_client, transport, leaves=None):
        topic_prefix = f"office/{zone}/sensor/{hub_id}"
        super().__init__(hub_id, topic_prefix, mqtt_client)
        self.zone = zone
        self.transport = transport
        self.leaves = leaves or []

        # Leaf registry: leaf_id (int) -> metadata dict
        self._leaf_registry = {}

        # Register MCP tools
        self.register_tool("leaf_command", self._tool_leaf_command)
        self.register_tool("get_swarm_status", self._tool_get_swarm_status)

    # ── Leaf name mapping ────────────────────────────────────

    def _leaf_name(self, leaf_id):
        """Get registered leaf name, or generate one from ID."""
        entry = self._leaf_registry.get(leaf_id)
        if entry:
            return entry.get("name", f"leaf_{leaf_id}")
        return f"leaf_{leaf_id}"

    def _find_leaf_id(self, name):
        """Find leaf_id by name string."""
        for lid, info in self._leaf_registry.items():
            if info.get("name") == name:
                return lid
        # Try parsing as int
        try:
            return int(name)
        except (ValueError, TypeError):
            return None

    # ── Main update loop ─────────────────────────────────────

    def update(self):
        """Called every simulation tick. Process Leaf messages + update leaves."""
        now = time.time()

        # Update all attached virtual leaves
        for leaf in self.leaves:
            leaf.update(now)

        # Drain transport: Leaf -> Hub messages
        for leaf_id, raw in self.transport.receive_from_leaves():
            self._process_leaf_message(leaf_id, raw)

        # Publish Hub heartbeat
        if not hasattr(self, "_last_hb") or now - self._last_hb >= 60:
            self.publish_telemetry("heartbeat", {
                "status": "online",
                "uptime_sec": int(now - getattr(self, "_start_time", now)),
                "device_id": self.device_id,
                "leaf_count": len(self._leaf_registry),
            })
            self._last_hb = now
            if not hasattr(self, "_start_time"):
                self._start_time = now

    # ── Binary message processing ────────────────────────────

    def _process_leaf_message(self, leaf_id, raw):
        try:
            msg_type, _lid, payload = decode(raw)
        except ValueError as e:
            logger.warning(f"[{self.device_id}] Bad frame from leaf {leaf_id}: {e}")
            return

        if msg_type == MSG_SENSOR_REPORT:
            self._handle_sensor_report(leaf_id, payload)
        elif msg_type == MSG_HEARTBEAT:
            self._handle_heartbeat(leaf_id, payload)
        elif msg_type == MSG_REGISTER:
            self._handle_register(leaf_id, payload)
        elif msg_type == MSG_WAKE_NOTIFY:
            self._handle_wake_notify(leaf_id, payload)
        elif msg_type == MSG_ACK:
            logger.debug(f"[{self.device_id}] ACK from leaf {leaf_id}")
        else:
            logger.debug(f"[{self.device_id}] Unknown msg 0x{msg_type:02x} from leaf {leaf_id}")

    def _handle_sensor_report(self, leaf_id, payload):
        """Decode sensor data and publish per-channel MQTT."""
        channels = decode_sensor_report(payload)
        leaf_name = self._leaf_name(leaf_id)
        device_id = f"{self.device_id}.{leaf_name}"

        for channel, value in channels.items():
            topic = f"office/{self.zone}/sensor/{device_id}/{channel}"
            self.client.publish(topic, json.dumps({"value": value}))

        # Update last_seen
        if leaf_id in self._leaf_registry:
            self._leaf_registry[leaf_id]["last_seen"] = time.time()
            self._leaf_registry[leaf_id]["last_data"] = channels

    def _handle_heartbeat(self, leaf_id, payload):
        hb = decode_heartbeat(payload)
        if leaf_id in self._leaf_registry:
            self._leaf_registry[leaf_id]["battery_mv"] = hb["battery_mv"]
            self._leaf_registry[leaf_id]["uptime_sec"] = hb["uptime_sec"]
            self._leaf_registry[leaf_id]["last_seen"] = time.time()
        logger.debug(
            f"[{self.device_id}] Heartbeat leaf {leaf_id}: "
            f"batt={hb['battery_mv']}mV uptime={hb['uptime_sec']}s"
        )

    def _handle_register(self, leaf_id, payload):
        info = decode_register(payload)
        # Find the leaf object to get its name for the registry
        leaf_name = f"leaf_{leaf_id}"
        for leaf in self.leaves:
            if leaf.leaf_id == leaf_id:
                # Use a descriptive name based on capabilities
                leaf_name = getattr(leaf, "name", None) or f"leaf_{leaf_id}"
                break

        self._leaf_registry[leaf_id] = {
            "name": leaf_name,
            "hw_type": info["hw_type"],
            "capabilities": info["capabilities"],
            "last_seen": time.time(),
            "battery_mv": 0,
            "uptime_sec": 0,
            "last_data": {},
        }
        logger.info(
            f"[{self.device_id}] Registered leaf {leaf_id} ({leaf_name}): "
            f"hw={info['hw_type']} caps={info['capabilities']}"
        )

    def _handle_wake_notify(self, leaf_id, payload):
        woken_id = decode_wake_notify(payload)
        logger.info(
            f"[{self.device_id}] Leaf {leaf_id} woke leaf {woken_id}"
        )

    # ── MCP Tools ────────────────────────────────────────────

    def _tool_leaf_command(self, leaf_id, command, args=None):
        """
        Send a command to a specific Leaf via the transport.
        Called by Brain through MCP.
        """
        # Resolve leaf name to int ID
        target_id = self._find_leaf_id(leaf_id)
        if target_id is None:
            return {"error": f"Unknown leaf: {leaf_id}"}

        if target_id not in self._leaf_registry:
            return {"error": f"Leaf {leaf_id} not registered"}

        # Map command name to command ID
        cmd_map = {
            "set_state": 0x01,
            "set_pwm": 0x02,
            "read_now": 0x03,
            "set_interval": 0x04,
            "deep_sleep": 0x05,
            "reset": 0x06,
        }
        cmd_id = cmd_map.get(command)
        if cmd_id is None:
            return {"error": f"Unknown command: {command}"}

        # Encode args
        import struct
        arg_bytes = b""
        if args:
            if command == "set_state":
                state_val = 1 if args.get("state") in ("on", True, 1) else 0
                arg_bytes = struct.pack("B", state_val)
            elif command == "set_pwm":
                arg_bytes = struct.pack("<H", int(args.get("duty", 0)))
            elif command == "set_interval":
                arg_bytes = struct.pack("<H", int(args.get("seconds", 30)))
            elif command == "deep_sleep":
                arg_bytes = struct.pack("<I", int(args.get("wake_after_ms", 60000)))

        payload = encode_command(cmd_id, arg_bytes)
        frame = encode(MSG_COMMAND, target_id, payload)
        self.transport.send_to_leaf(target_id, frame)

        return {
            "status": "sent",
            "leaf_id": leaf_id,
            "command": command,
        }

    def _tool_get_swarm_status(self):
        """Return status of all registered Leaves."""
        now = time.time()
        leaves = []
        for lid, info in self._leaf_registry.items():
            age = now - info.get("last_seen", 0)
            entry = {
                "leaf_id": lid,
                "name": info.get("name", f"leaf_{lid}"),
                "hw_type": info["hw_type"],
                "capabilities": info["capabilities"],
                "battery_mv": info.get("battery_mv", 0),
                "last_seen_sec_ago": round(age, 1),
                "online": age < 120,
                "last_data": info.get("last_data", {}),
            }
            # Low battery warning
            batt = info.get("battery_mv", 0)
            if 0 < batt < 2400:
                entry["warning"] = "low_battery"
            leaves.append(entry)

        return {
            "hub_id": self.device_id,
            "leaf_count": len(leaves),
            "leaves": leaves,
        }
