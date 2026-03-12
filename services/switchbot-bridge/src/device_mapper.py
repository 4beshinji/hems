"""
Maps SwitchBot device IDs to HEMS zone/domain structure.
"""
import json
from loguru import logger


class DeviceMapper:
    """Maps SwitchBot deviceId to HEMS zone + friendly name."""

    def __init__(self, device_map_json: str = "{}"):
        self._custom_map: dict[str, dict] = {}
        try:
            raw = json.loads(device_map_json)
            if isinstance(raw, dict):
                self._custom_map = raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse SWITCHBOT_DEVICE_MAP, using defaults")

    def get_zone(self, device_id: str) -> str:
        """Return zone for a given SwitchBot device ID."""
        if device_id in self._custom_map:
            return self._custom_map[device_id].get("zone", "home")
        return "home"

    def get_name(self, device_id: str) -> str | None:
        """Return custom name override if configured."""
        if device_id in self._custom_map:
            return self._custom_map[device_id].get("name")
        return None

    def get_mqtt_topic(self, device_id: str, domain: str) -> str:
        """Build MQTT topic for a SwitchBot device.

        Uses the same hems/home/{zone}/{domain}/{entity_id}/state structure
        as the HA bridge, so WorldModel handles it transparently.
        """
        zone = self.get_zone(device_id)
        entity_id = f"switchbot.{device_id}"
        return f"hems/home/{zone}/{domain}/{entity_id}/state"
