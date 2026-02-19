"""
Maps Home Assistant entity_id to HEMS zone/domain structure.
"""
import json
from loguru import logger


class EntityMapper:
    """Maps HA entity_id (e.g. light.living_room) to HEMS zone + domain."""

    def __init__(self, entity_map_json: str = "{}"):
        self._custom_map: dict[str, dict] = {}
        try:
            raw = json.loads(entity_map_json)
            if isinstance(raw, dict):
                self._custom_map = raw
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse HEMS_HA_ENTITY_MAP, using defaults")

    def map(self, entity_id: str) -> tuple[str, str]:
        """Return (zone, domain) for a given HA entity_id.

        Custom map example: {"light.bedroom": {"zone": "bedroom", "domain": "light"}}
        Default: domain from entity_id prefix, zone from entity_id suffix.
        """
        if entity_id in self._custom_map:
            entry = self._custom_map[entity_id]
            return entry.get("zone", "home"), entry.get("domain", "unknown")

        # Default: entity_id format is "domain.name_suffix"
        parts = entity_id.split(".", 1)
        if len(parts) == 2:
            domain = parts[0]
            # Use the name part as zone (e.g. "living_room" from "light.living_room")
            zone = parts[1]
            return zone, domain

        return "home", "unknown"

    def get_mqtt_topic(self, entity_id: str) -> str:
        """Build MQTT topic for a given entity_id."""
        zone, domain = self.map(entity_id)
        return f"hems/home/{zone}/{domain}/{entity_id}/state"
