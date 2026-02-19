"""
Virtual SwarmLeaf devices for emulator testing.
Each leaf generates simulated sensor data, encodes it as binary,
and sends through a VirtualTransport to a SwarmHub.
"""

import logging
import random
import time
import sys
import os

for _p in ["/edge_lib", os.path.join(os.path.dirname(__file__), "..", "..", "..", "edge", "lib")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
from swarm.message import (
    encode, decode,
    encode_sensor_report, encode_heartbeat, encode_register,
    encode_wake_notify, decode_command,
    MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_WAKE_NOTIFY, MSG_ACK,
    MSG_COMMAND, MSG_CONFIG,
    CH_TEMPERATURE, CH_HUMIDITY, CH_PIR_MOTION, CH_DOOR, CH_BATTERY_MV,
    CH_ILLUMINANCE,
    HW_ESP32, HW_ATTINY,
    CAP_RELAY,
)

logger = logging.getLogger(__name__)


class VirtualSwarmLeaf:
    """Base class for virtual leaf devices."""

    def __init__(self, leaf_id, hw_type, capabilities, transport,
                 report_interval=10):
        self.leaf_id = leaf_id
        self.hw_type = hw_type
        self.capabilities = capabilities
        self.transport = transport
        self.report_interval = report_interval

        self.battery_mv = 3300  # 2xAA fresh
        self.uptime = 0
        self._last_report = 0
        self._last_heartbeat = 0
        self._registered = False
        self._relay_state = False

        self.transport.register_leaf(self.leaf_id)

    def _send(self, msg_type, payload=b""):
        frame = encode(msg_type, self.leaf_id, payload)
        self.transport.send_to_hub(self.leaf_id, frame)

    def register(self):
        """Send REGISTER message to Hub."""
        payload = encode_register(self.hw_type, self.capabilities)
        self._send(MSG_REGISTER, payload)
        self._registered = True
        logger.info(f"[Leaf {self.leaf_id}] Sent REGISTER")

    def read_sensors(self):
        """Override in subclass. Returns dict {channel_type: value}."""
        return {}

    def update(self, now=None):
        """Called every simulation tick."""
        if now is None:
            now = time.time()
        self.uptime += 2  # simulation runs every 2s

        # Register on first tick
        if not self._registered:
            self.register()

        # Periodic sensor report
        if now - self._last_report >= self.report_interval:
            data = self.read_sensors()
            if data:
                payload = encode_sensor_report(data)
                self._send(MSG_SENSOR_REPORT, payload)
            self._last_report = now

        # Heartbeat every 60s
        if now - self._last_heartbeat >= 60:
            payload = encode_heartbeat(self.battery_mv, self.uptime)
            self._send(MSG_HEARTBEAT, payload)
            self._last_heartbeat = now

        # Drain battery slowly
        self.battery_mv = max(2000, self.battery_mv - random.uniform(0, 0.05))

        # Process any commands from Hub
        for data in self.transport.receive_from_hub(self.leaf_id):
            self._handle_incoming(data)

    def _handle_incoming(self, raw):
        try:
            msg_type, _leaf_id, payload = decode(raw)
        except ValueError as e:
            logger.warning(f"[Leaf {self.leaf_id}] Bad frame: {e}")
            return

        if msg_type == MSG_COMMAND:
            cmd = decode_command(payload)
            result = self._execute_command(cmd)
            logger.info(f"[Leaf {self.leaf_id}] CMD 0x{cmd['cmd_id']:02x} -> {result}")
            # Send ACK
            self._send(MSG_ACK)
        elif msg_type == MSG_CONFIG:
            logger.info(f"[Leaf {self.leaf_id}] CONFIG received")
            self._send(MSG_ACK)

    def _execute_command(self, cmd):
        cmd_id = cmd["cmd_id"]
        args = cmd["args"]
        if cmd_id == 0x01:  # set_state
            self._relay_state = bool(args[0]) if args else False
            return {"state": self._relay_state}
        if cmd_id == 0x03:  # read_now
            data = self.read_sensors()
            if data:
                payload = encode_sensor_report(data)
                self._send(MSG_SENSOR_REPORT, payload)
            return {"read": True}
        if cmd_id == 0x04:  # set_interval
            import struct
            if len(args) >= 2:
                self.report_interval = struct.unpack("<H", args[:2])[0]
            return {"interval": self.report_interval}
        return {"cmd_id": cmd_id, "status": "ok"}


class TempHumidityLeaf(VirtualSwarmLeaf):
    """Simulates a BME280-style temp/humidity/pressure sensor."""

    def __init__(self, leaf_id, transport, report_interval=10):
        super().__init__(
            leaf_id, HW_ESP32,
            [CH_TEMPERATURE, CH_HUMIDITY],
            transport, report_interval,
        )
        self._temp = 22.0 + random.uniform(-2, 2)
        self._hum = 50.0 + random.uniform(-10, 10)

    def read_sensors(self):
        self._temp += random.uniform(-0.3, 0.3)
        self._hum += random.uniform(-1.0, 1.0)
        self._hum = max(20, min(90, self._hum))
        return {CH_TEMPERATURE: self._temp, CH_HUMIDITY: self._hum}


class PIRLeaf(VirtualSwarmLeaf):
    """Simulates a PIR motion + illuminance sensor with wake chain support."""

    def __init__(self, leaf_id, transport, report_interval=5,
                 wakes_leaf_id=None):
        super().__init__(
            leaf_id, HW_ATTINY,
            [CH_PIR_MOTION, CH_ILLUMINANCE],
            transport, report_interval,
        )
        self._motion = 0
        self._lux = 300.0
        self._wakes_leaf_id = wakes_leaf_id

    def read_sensors(self):
        # 20% chance of motion
        self._motion = 1 if random.random() < 0.2 else 0
        self._lux += random.uniform(-20, 20)
        self._lux = max(0, min(1000, self._lux))

        # Wake chain: if motion detected, send WAKE_NOTIFY
        if self._motion and self._wakes_leaf_id is not None:
            payload = encode_wake_notify(self._wakes_leaf_id)
            self._send(MSG_WAKE_NOTIFY, payload)

        return {CH_PIR_MOTION: self._motion, CH_ILLUMINANCE: self._lux}


class DoorSensorLeaf(VirtualSwarmLeaf):
    """Simulates a door open/close sensor (magnetic reed switch)."""

    def __init__(self, leaf_id, transport, report_interval=15):
        super().__init__(
            leaf_id, HW_ATTINY,
            [CH_DOOR],
            transport, report_interval,
        )
        self._door_open = 0

    def read_sensors(self):
        # 5% chance of state change
        if random.random() < 0.05:
            self._door_open = 1 - self._door_open
        return {CH_DOOR: self._door_open}


class RelayLeaf(VirtualSwarmLeaf):
    """Simulates a relay actuator (controllable via commands)."""

    def __init__(self, leaf_id, transport, report_interval=30):
        super().__init__(
            leaf_id, HW_ESP32,
            [CAP_RELAY],
            transport, report_interval,
        )

    def read_sensors(self):
        # Relay has no sensor data, just reports state
        return {}
