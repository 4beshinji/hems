"""
SwarmLeaf — MicroPython base class for battery-powered leaf sensor nodes.

No WiFi or MQTT needed. Communicates with Hub via a transport (ESP-NOW,
UART, I2C). Supports deep sleep with timer or external interrupt wake.

Usage on ESP32-C3:
    from swarm.leaf import SwarmLeaf
    from swarm.transport_espnow import ESPNowTransport

    transport = ESPNowTransport(hub_mac=b'\\xaa\\xbb\\xcc\\xdd\\xee\\xff')
    leaf = SwarmLeaf(leaf_id=1, hw_type=0x01, transport=transport)
    leaf.add_capability(0x01)  # temperature
    leaf.add_capability(0x02)  # humidity

    def read():
        return {0x01: 22.5, 0x02: 55.0}

    leaf.run(read_fn=read, interval_sec=30, deep_sleep=True)
"""

import time
import struct

try:
    import machine
except ImportError:
    machine = None

try:
    from swarm.message import (
        encode, decode, encode_sensor_report, encode_heartbeat,
        encode_register, decode_command,
        MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_ACK,
        MSG_COMMAND, MSG_CONFIG,
    )
except ImportError:
    import sys
    sys.path.insert(0, "/lib")
    from swarm.message import (
        encode, decode, encode_sensor_report, encode_heartbeat,
        encode_register, decode_command,
        MSG_SENSOR_REPORT, MSG_HEARTBEAT, MSG_REGISTER, MSG_ACK,
        MSG_COMMAND, MSG_CONFIG,
    )


class SwarmLeaf:
    """Base class for battery-powered leaf devices."""

    def __init__(self, leaf_id, hw_type, transport):
        self.leaf_id = leaf_id
        self.hw_type = hw_type
        self.transport = transport
        self.capabilities = []
        self.report_interval = 30
        self._boot_ticks = time.ticks_ms() if hasattr(time, "ticks_ms") else 0
        self._relay_state = False

    def add_capability(self, cap_type):
        """Register a sensor/actuator capability."""
        self.capabilities.append(cap_type)

    # ── Communication ────────────────────────────────────────

    def _send(self, msg_type, payload=b""):
        frame = encode(msg_type, self.leaf_id, payload)
        self.transport.send(frame)

    def _receive(self):
        """Check for incoming messages from Hub. Returns (msg_type, payload) or None."""
        result = self.transport.receive()
        if result is None:
            return None
        try:
            msg_type, _lid, payload = decode(result)
            return msg_type, payload
        except ValueError:
            return None

    # ── Registration ─────────────────────────────────────────

    def register(self):
        """Send REGISTER message to Hub."""
        payload = encode_register(self.hw_type, self.capabilities)
        self._send(MSG_REGISTER, payload)

    # ── Sensor reporting ─────────────────────────────────────

    def report(self, channels):
        """Send a sensor report. channels: {channel_type: value}."""
        payload = encode_sensor_report(channels)
        self._send(MSG_SENSOR_REPORT, payload)

    def heartbeat(self, battery_mv=0):
        """Send heartbeat with battery level."""
        uptime = time.ticks_diff(time.ticks_ms(), self._boot_ticks) // 1000 \
            if hasattr(time, "ticks_ms") else 0
        payload = encode_heartbeat(battery_mv, uptime)
        self._send(MSG_HEARTBEAT, payload)

    # ── Command handling ─────────────────────────────────────

    def process_commands(self):
        """Check and handle any commands from Hub."""
        while True:
            msg = self._receive()
            if msg is None:
                break
            msg_type, payload = msg
            if msg_type == MSG_COMMAND:
                cmd = decode_command(payload)
                self._handle_command(cmd)
                self._send(MSG_ACK)
            elif msg_type == MSG_CONFIG:
                self._send(MSG_ACK)

    def _handle_command(self, cmd):
        """Process a command. Override for custom behavior."""
        cmd_id = cmd["cmd_id"]
        args = cmd["args"]
        if cmd_id == 0x01:  # set_state
            self._relay_state = bool(args[0]) if args else False
            self.on_set_state(self._relay_state)
        elif cmd_id == 0x03:  # read_now — handled by run loop
            pass
        elif cmd_id == 0x04:  # set_interval
            if len(args) >= 2:
                self.report_interval = struct.unpack("<H", args[:2])[0]
        elif cmd_id == 0x06:  # reset
            if machine:
                machine.reset()

    def on_set_state(self, state):
        """Override in subclass to control relay/LED."""
        pass

    # ── Deep sleep ───────────────────────────────────────────

    def deep_sleep(self, ms):
        """Enter deep sleep. Device restarts on wake."""
        if machine and hasattr(machine, "deepsleep"):
            machine.deepsleep(ms)
        else:
            time.sleep(ms / 1000)

    # ── Main loop ────────────────────────────────────────────

    def run(self, read_fn, interval_sec=30, deep_sleep_enabled=False,
            battery_fn=None):
        """
        Main loop for leaf operation.

        read_fn: callable returning {channel_type: value}
        battery_fn: callable returning battery_mv (optional)
        """
        self.report_interval = interval_sec
        self.register()

        hb_counter = 0
        while True:
            # Read sensors and report
            channels = read_fn()
            if channels:
                self.report(channels)

            # Heartbeat every 6 cycles
            hb_counter += 1
            if hb_counter >= 6:
                batt = battery_fn() if battery_fn else 0
                self.heartbeat(batt)
                hb_counter = 0

            # Process any pending commands
            self.process_commands()

            if deep_sleep_enabled:
                self.deep_sleep(self.report_interval * 1000)
            else:
                time.sleep(self.report_interval)
