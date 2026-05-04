"""
SwitchBot API v1.1 client with HMAC-SHA256 authentication.
"""

import base64
import hashlib
import hmac
import time
import uuid
from typing import Any

import aiohttp
from loguru import logger

import config

# SwitchBot device type → HEMS domain mapping
DEVICE_TYPE_DOMAIN: dict[str, str] = {
    # Lights
    "Color Bulb": "light",
    "Strip Light": "light",
    "Ceiling Light": "light",
    "Ceiling Light Pro": "light",
    # Covers
    "Curtain": "cover",
    "Curtain3": "cover",
    "Blind Tilt": "cover",
    "Roller Shade": "cover",
    # Switches / Plugs
    "Bot": "switch",
    "Plug Mini (US)": "switch",
    "Plug Mini (JP)": "switch",
    "Plug": "switch",
    # Climate
    "Air Conditioner": "climate",
    # Sensors
    "Meter": "sensor",
    "Meter Plus": "sensor",
    "MeterPlus": "sensor",
    "MeterPro": "sensor",
    "MeterPro(CO2)": "sensor",
    "Outdoor Meter": "sensor",
    "Hub 2": "sensor",
    # Binary sensors
    "Motion Sensor": "binary_sensor",
    "Contact Sensor": "binary_sensor",
    "Water Detector": "binary_sensor",
    # Hub (IR remote capable)
    "Hub Mini": "hub",
    "Hub 3": "hub",
    # Other
    "Lock": "lock",
    "Lock Pro": "lock",
    "Keypad": "lock",
    "Robot Vacuum Cleaner S1": "vacuum",
    "Robot Vacuum Cleaner S1 Plus": "vacuum",
    "Air Purifier VOC": "switch",
    "Air Purifier Table": "switch",
    "Humidifier": "switch",
    "Humidifier2": "switch",
    "Evaporative Humidifier": "switch",
    "Evaporative Humidifier (Auto-refill)": "switch",
    "Fan": "switch",
    "Battery Circulator Fan": "switch",
}


class SwitchBotClient:
    """Client for SwitchBot API v1.1."""

    def __init__(self, token: str = "", secret: str = ""):
        self.token = token or config.SWITCHBOT_TOKEN
        self.secret = secret or config.SWITCHBOT_SECRET
        self._session: aiohttp.ClientSession | None = None
        self.connected: bool = False
        self._devices: dict[str, dict] = {}  # deviceId → device info
        self._ir_devices: dict[str, dict] = {}  # deviceId → IR device info

    async def start(self, session: aiohttp.ClientSession):
        self._session = session

    async def stop(self):
        self._session = None
        self.connected = False

    def _make_headers(self) -> dict[str, str]:
        """Generate SwitchBot API v1.1 HMAC-SHA256 authentication headers."""
        t = str(round(time.time() * 1000))
        nonce = str(uuid.uuid4())
        string_to_sign = f"{self.token}{t}{nonce}"
        sign = base64.b64encode(
            hmac.new(
                self.secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "Authorization": self.token,
            "sign": sign,
            "t": t,
            "nonce": nonce,
            "Content-Type": "application/json",
        }

    async def _api_get(self, path: str) -> dict | None:
        """GET request to SwitchBot API."""
        try:
            async with self._session.get(
                f"{config.SWITCHBOT_API_BASE}{path}",
                headers=self._make_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("statusCode") == 100:
                    self.connected = True
                    return data.get("body")
                logger.warning(f"SwitchBot API GET {path} failed: {data.get('message', resp.status)}")
        except Exception as e:
            logger.warning(f"SwitchBot API GET {path} error: {e}")
            self.connected = False
        return None

    async def _api_post(self, path: str, payload: dict) -> dict | None:
        """POST request to SwitchBot API."""
        try:
            async with self._session.post(
                f"{config.SWITCHBOT_API_BASE}{path}",
                headers=self._make_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("statusCode") == 100:
                    return data.get("body")
                logger.warning(f"SwitchBot API POST {path} failed: {data.get('message', resp.status)}")
        except Exception as e:
            logger.error(f"SwitchBot API POST {path} error: {e}")
        return None

    async def get_devices(self) -> tuple[list[dict], list[dict]]:
        """Fetch all devices (physical + IR virtual)."""
        body = await self._api_get("/devices")
        if body is None:
            return [], []
        physical = body.get("deviceList", [])
        infrared = body.get("infraredRemoteList", [])
        # Cache device info
        for d in physical:
            self._devices[d["deviceId"]] = d
        for d in infrared:
            self._ir_devices[d["deviceId"]] = d
        return physical, infrared

    async def get_device_status(self, device_id: str) -> dict | None:
        """Fetch status of a single physical device."""
        return await self._api_get(f"/devices/{device_id}/status")

    async def send_command(
        self, device_id: str, command: str, parameter: str = "default", command_type: str = "command"
    ) -> dict | None:
        """Send command to a device."""
        payload = {
            "command": command,
            "parameter": parameter,
            "commandType": command_type,
        }
        return await self._api_post(f"/devices/{device_id}/commands", payload)

    def get_domain(self, device_type: str) -> str:
        """Map SwitchBot device type to HEMS domain."""
        return DEVICE_TYPE_DOMAIN.get(device_type, "switch")

    def get_cached_device(self, device_id: str) -> dict | None:
        """Get cached device info."""
        return self._devices.get(device_id) or self._ir_devices.get(device_id)

    def parse_status(self, device_id: str, status: dict) -> dict[str, Any]:
        """Parse device status into HEMS-compatible format for MQTT publish."""
        device_info = self._devices.get(device_id, {})
        device_type = device_info.get("deviceType", status.get("deviceType", ""))
        domain = self.get_domain(device_type)
        device_name = device_info.get("deviceName", device_id)

        result = {
            "entity_id": f"switchbot.{device_id}",
            "state": "unknown",
            "domain": domain,
            "device_type": device_type,
            "friendly_name": device_name,
        }

        if domain == "light":
            on = status.get("power", "off") == "on"
            result["state"] = "on" if on else "off"
            result["on"] = on
            result["brightness"] = status.get("brightness", 0)
            result["color_temp"] = status.get("colorTemperature", 0)
            if "color" in status:
                result["color"] = status["color"]

        elif domain == "cover":
            position = status.get("slidePosition", status.get("position", 0))
            moving = status.get("moving", False)
            result["current_position"] = position
            result["is_open"] = position > 0
            result["state"] = "open" if position > 0 else "closed"
            if moving:
                result["state"] = "opening" if status.get("direction", "") == "up" else "closing"

        elif domain == "switch":
            on = status.get("power", "off") == "on"
            result["state"] = "on" if on else "off"
            result["on"] = on
            # Plug Mini provides power data
            if "voltage" in status:
                result["voltage"] = status["voltage"]
            if "weight" in status:  # power in watts
                result["power_watts"] = status["weight"]
            if "electricCurrent" in status:
                result["current_ma"] = status["electricCurrent"]

        elif domain == "climate":
            result["state"] = status.get("mode", "off")
            result["hvac_mode"] = status.get("mode", "off")
            result["temperature"] = status.get("temperature", 0)

        elif domain == "sensor":
            result["state"] = "on"
            if "temperature" in status:
                result["temperature"] = status["temperature"]
            if "humidity" in status:
                result["humidity"] = status["humidity"]
            if "CO2" in status:
                result["co2"] = status["CO2"]
            if "battery" in status:
                result["battery"] = status["battery"]

        elif domain == "binary_sensor":
            device_class = "motion"
            if "Contact" in device_type:
                device_class = "door"
                detected = status.get("openState", "close") != "close"
            elif "Water" in device_type:
                device_class = "moisture"
                detected = status.get("status", 0) == 1
            else:
                # Motion sensor
                detected = status.get("moveDetected", False)
            result["state"] = "on" if detected else "off"
            result["device_class"] = device_class
            if "battery" in status:
                result["battery"] = status["battery"]
            if "brightness" in status:
                result["ambient_brightness"] = status["brightness"]

        elif domain == "lock":
            locked = status.get("lockState", "locked") == "locked"
            result["state"] = "locked" if locked else "unlocked"
            result["on"] = not locked
            if "battery" in status:
                result["battery"] = status["battery"]

        return result
