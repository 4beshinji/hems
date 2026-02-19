"""
SOMS MCP Device — shared MicroPython library for ESP32 edge devices.

Handles WiFi, MQTT, MCP tool calls (JSON-RPC 2.0), per-channel telemetry,
reconnection, and periodic heartbeat.

Usage:
    from soms_mcp import MCPDevice
    device = MCPDevice()            # reads config.json
    device.register_tool("get_status", get_sensor_data)
    device.connect()
    while True:
        device.loop()
        device.publish_sensor_data({"temperature": 21.5, "humidity": 45.2})
        time.sleep(30)
"""

import network
import time
import json
import machine
from umqtt.simple import MQTTClient


class MCPDevice:
    def __init__(self, config_path="config.json", **overrides):
        """
        Initialise from config.json, with optional keyword overrides.

        Expected config.json keys:
            device_id, zone, wifi_ssid, wifi_password,
            mqtt_broker, mqtt_port (default 1883),
            report_interval (default 30)
        """
        cfg = self._load_config(config_path)
        cfg.update(overrides)
        self.config = cfg

        self.device_id = cfg["device_id"]
        self.zone = cfg.get("zone", "default")
        self.ssid = cfg["wifi_ssid"]
        self.password = cfg["wifi_password"]
        self.broker = cfg["mqtt_broker"]
        self.port = cfg.get("mqtt_port", 1883)
        self.mqtt_user = cfg.get("mqtt_user", None)
        self.mqtt_pass = cfg.get("mqtt_pass", None)
        self.report_interval = cfg.get("report_interval", 30)

        # Derive MQTT topic prefix: office/{zone}/sensor/{device_id}
        self.topic_prefix = cfg.get(
            "topic_prefix",
            f"office/{self.zone}/sensor/{self.device_id}",
        )

        self.client = None
        self.tools = {}
        self._wlan = None
        self._boot_ticks = time.ticks_ms()
        self._last_heartbeat = 0

    # ---- Config ----

    @staticmethod
    def _load_config(path):
        try:
            with open(path) as f:
                return json.load(f)
        except OSError:
            return {}

    # ---- WiFi ----

    def connect_wifi(self):
        self._wlan = network.WLAN(network.STA_IF)
        self._wlan.active(True)
        if self._wlan.isconnected():
            print("WiFi already connected:", self._wlan.ifconfig())
            return
        print(f"Connecting to WiFi {self.ssid}...")
        self._wlan.connect(self.ssid, self.password)
        for _ in range(30):
            if self._wlan.isconnected():
                break
            time.sleep(1)
        if self._wlan.isconnected():
            print("WiFi connected:", self._wlan.ifconfig())
        else:
            raise OSError("WiFi connection failed")

    # ---- MQTT ----

    def _connect_mqtt(self):
        self.client = MQTTClient(
            self.device_id, self.broker, port=self.port,
            user=self.mqtt_user, password=self.mqtt_pass,
        )
        self.client.set_callback(self._mqtt_callback)
        self.client.connect()
        self.client.subscribe(f"mcp/{self.device_id}/request/call_tool")
        print(f"MQTT connected to {self.broker}:{self.port}")

    def connect(self):
        """Full connection sequence: WiFi then MQTT."""
        self.connect_wifi()
        self._connect_mqtt()

    def reconnect(self):
        """Attempt WiFi/MQTT reconnection without machine.reset()."""
        print("Reconnecting...")
        try:
            if self._wlan and not self._wlan.isconnected():
                self.connect_wifi()
            self._connect_mqtt()
            print("Reconnected successfully")
        except Exception as e:
            print(f"Reconnect failed: {e}")
            raise

    # ---- Tool registration ----

    def register_tool(self, name, callback):
        self.tools[name] = callback

    # ---- MQTT callback / MCP handler ----

    def _mqtt_callback(self, topic, msg):
        topic_str = topic.decode()
        try:
            payload = json.loads(msg.decode())
        except Exception as e:
            print(f"JSON parse error: {e}")
            return
        if topic_str == f"mcp/{self.device_id}/request/call_tool":
            self._handle_tool_call(payload)

    def _handle_tool_call(self, payload):
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if method == "call_tool" and tool_name in self.tools:
            print(f"Executing tool: {tool_name}")
            try:
                result = self.tools[tool_name](**args)
                response = {"jsonrpc": "2.0", "result": result, "id": req_id}
            except Exception as e:
                print(f"Tool error: {e}")
                response = {"jsonrpc": "2.0", "error": str(e), "id": req_id}
            self.client.publish(
                f"mcp/{self.device_id}/response/{req_id}",
                json.dumps(response),
            )

    # ---- Main loop helper ----

    def loop(self):
        """Call in the main while-loop to process MQTT messages and heartbeat."""
        self.client.check_msg()
        self._maybe_heartbeat()

    # ---- Telemetry ----

    def publish_telemetry(self, subtopic, data):
        """Publish raw data to {topic_prefix}/{subtopic}."""
        topic = f"{self.topic_prefix}/{subtopic}"
        self.client.publish(topic, json.dumps(data))

    def publish_sensor_data(self, data):
        """
        Publish per-channel telemetry for WorldModel compatibility.

        data: dict like {"temperature": 21.5, "humidity": 45.2, "co2": 420}
        Publishes each key as a separate MQTT topic with {"value": <val>}.
        """
        for channel, value in data.items():
            topic = f"{self.topic_prefix}/{channel}"
            self.client.publish(topic, json.dumps({"value": value}))

    # ---- Heartbeat ----

    def _maybe_heartbeat(self):
        now = time.time()
        if now - self._last_heartbeat >= 60:
            uptime_ms = time.ticks_diff(time.ticks_ms(), self._boot_ticks)
            payload = {
                "status": "online",
                "uptime_sec": uptime_ms // 1000,
                "device_id": self.device_id,
            }
            self.client.publish(
                f"{self.topic_prefix}/heartbeat",
                json.dumps(payload),
            )
            self._last_heartbeat = now
