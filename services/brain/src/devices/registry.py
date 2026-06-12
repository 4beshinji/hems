"""Vendor parser registry + parse_mqtt router + DeviceDispatcher core.

``VENDOR_PARSERS`` is the single registration table. ``parse_mqtt`` walks it in
order (preserving the historical top-to-bottom early-return match order) and the
``DeviceDispatcher.dispatch`` core routes actuator commands to the right parser.
"""

from __future__ import annotations

import aiohttp
from loguru import logger

from brain_constants import backend_auth_headers
from devices.actions import _ACTION_CAPABILITY, DEVICE_ALLOWED_ACTIONS
from devices.base import DispatchContext
from devices.observation import DeviceObservation
from devices.vendors.ha import HAParser
from devices.vendors.mcp import McpParser
from devices.vendors.switchbot import SwitchBotParser
from devices.vendors.tapo import TapoParser
from devices.vendors.zigbee import ZigbeeParser

# Registration table. Order matters: parse_mqtt matches in this order and uses
# the first parser whose .matches() is True (preserving the original if-chain).
VENDOR_PARSERS: dict[str, object] = {
    "mcp": McpParser(),
    "switchbot": SwitchBotParser(),
    "tapo": TapoParser(),
    "zigbee": ZigbeeParser(),
    "ha": HAParser(),
}


def parse_mqtt(topic: str, payload: dict) -> DeviceObservation | None:
    """Return a DeviceObservation if topic matches a known device pattern."""
    parts = topic.split("/")
    for parser in VENDOR_PARSERS.values():
        if parser.matches(parts):
            return parser.parse(parts, payload)
    return None


class DeviceDispatcher:
    """Central router for actuator commands across bridges.

    Looks up the device (by device_id) via backend, then dispatches based on vendor.
    Brain's ToolExecutor calls dispatch() for `control_actuator`.
    """

    def __init__(self, session: aiohttp.ClientSession, mqtt_client=None):
        self.session = session
        self.mqtt_client = mqtt_client  # paho client for zigbee2mqtt publish
        # Imported lazily through the facade so DASHBOARD_API_URL reassignment is honoured.
        import device_dispatcher as _dd

        self.backend_url = _dd.DASHBOARD_API_URL
        self._ctx = DispatchContext(session=session, mqtt_client=mqtt_client)

    @property
    def ctx(self) -> DispatchContext:
        # Keep ctx in sync with attribute reassignment (tests reset mqtt_client).
        self._ctx.session = self.session
        self._ctx.mqtt_client = self.mqtt_client
        return self._ctx

    async def lookup(self, device_id: str) -> dict | None:
        """Fetch device record from backend."""
        try:
            async with self.session.get(
                f"{self.backend_url}/devices/{device_id}",
                headers=backend_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            logger.warning(f"Device lookup failed for {device_id}: {e}")
            return None

    async def list_all(
        self,
        kind: str | None = None,
        zone: str | None = None,
        vendor: str | None = None,
        device_class: str | None = None,
        capability: str | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {}
        if kind:
            params["kind"] = kind
        if zone:
            params["zone"] = zone
        if vendor:
            params["vendor"] = vendor
        if device_class:
            params["device_class"] = device_class
        if capability:
            params["capability"] = capability
        try:
            async with self.session.get(
                f"{self.backend_url}/devices/",
                headers=backend_auth_headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.warning(f"Device list failed: {e}")
        return []

    async def dispatch(self, device_id: str, action: str, params: dict | None = None) -> dict:
        """Execute action on a device. Returns {"success": bool, "result"|"error": str}."""
        from device_id_validator import is_valid_device_ref

        params = params or {}

        # W1.2: reject invalid device_id before any network I/O
        if not is_valid_device_ref(device_id):
            logger.warning("dispatch rejected: invalid device_id %r", device_id)
            return {"success": False, "error": f"Invalid device_id {device_id!r}: must match ^[\\w.\\-]+$"}

        device = await self.lookup(device_id)
        if not device:
            return {"success": False, "error": f"Device '{device_id}' not registered"}

        vendor = device.get("vendor", "")
        caps = device.get("capabilities", []) or []

        # Per-action capability guardrail
        if action not in DEVICE_ALLOWED_ACTIONS:
            return {"success": False, "error": f"Unknown action '{action}'"}
        required_cap = _ACTION_CAPABILITY.get(action)
        if required_cap and required_cap not in caps:
            return {"success": False, "error": f"Device does not advertise capability '{required_cap}' (has: {caps})"}

        parser = VENDOR_PARSERS.get(vendor)
        if parser is None:
            return {"success": False, "error": f"Unsupported vendor '{vendor}'"}

        # Zigbee dispatch is synchronous (no await) — preserve historical contract.
        if vendor == "zigbee":
            return parser.dispatch_sync(self.ctx, device, action, params)
        return await parser.dispatch(self.ctx, device, action, params)

    # ── Backward-compatible private methods (referenced by tests + chat server) ──

    async def _dispatch_ha(self, device: dict, action: str, params: dict) -> dict:
        return await VENDOR_PARSERS["ha"].dispatch(self.ctx, device, action, params)

    async def _ha_rainbow(self, entity_id: str, duration: int):
        return await VENDOR_PARSERS["ha"]._ha_rainbow(self.ctx, entity_id, duration)

    async def _dispatch_switchbot(self, device: dict, action: str, params: dict) -> dict:
        return await VENDOR_PARSERS["switchbot"].dispatch(self.ctx, device, action, params)

    async def _dispatch_tapo(self, device: dict, action: str, params: dict) -> dict:
        return await VENDOR_PARSERS["tapo"].dispatch(self.ctx, device, action, params)

    async def _tapo_raw(self, device_ref: str, command: str) -> dict:
        return await VENDOR_PARSERS["tapo"]._tapo_raw(self.ctx, device_ref, command)

    def _dispatch_zigbee(self, device: dict, action: str, params: dict) -> dict:
        return VENDOR_PARSERS["zigbee"].dispatch_sync(self.ctx, device, action, params)

    def zigbee_permit_join(self, enable: bool, duration_s: int = 0) -> dict:
        return VENDOR_PARSERS["zigbee"].permit_join(self.ctx, enable, duration_s)
