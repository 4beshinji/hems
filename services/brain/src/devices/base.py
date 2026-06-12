"""VendorParser ABC + DispatchContext.

Two responsibilities per vendor are expressed through one ABC:

* **parse** (pure): MQTT topic parts + payload -> DeviceObservation
* **dispatch** (side-effects): action -> bridge HTTP / MQTT publish

``DispatchContext`` carries the shared collaborators (aiohttp session, paho
mqtt client) plus the bridge URLs and ``asyncio`` module. Crucially, the bridge
URLs and ``asyncio`` are read **live from the ``device_dispatcher`` facade
module** at dispatch time. The characterization tests (and production hot-reload
of env-derived globals) set e.g. ``device_dispatcher.HA_BRIDGE_URL = ...`` and
``patch("device_dispatcher.asyncio.sleep")`` — sourcing through the facade keeps
those patch points authoritative after the split (behaviour-identical).

``resolve_ref`` centralises the vendor_ref resolution + W1.2 validation that was
previously duplicated across the four ``_dispatch_*`` methods. The validation
must run **before any I/O** and its error string is byte-stable.
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Any

from device_id_validator import is_valid_device_ref


class DispatchContext:
    """Shared collaborators + helpers for vendor dispatch.

    Bridge URLs / asyncio are proxied from the ``device_dispatcher`` facade so
    that test patches and runtime reassignment remain authoritative.
    """

    def __init__(self, session, mqtt_client):
        self.session = session
        self.mqtt_client = mqtt_client

    @property
    def _facade(self):
        # Late import; the facade imports this module, so resolve lazily.
        return importlib.import_module("device_dispatcher")

    @property
    def asyncio(self):
        return self._facade.asyncio

    @property
    def ha_url(self) -> str:
        return self._facade.HA_BRIDGE_URL

    @property
    def switchbot_url(self) -> str:
        return self._facade.SWITCHBOT_BRIDGE_URL

    @property
    def tapo_url(self) -> str:
        return self._facade.TAPO_BRIDGE_URL

    @staticmethod
    def resolve_ref(device: dict, vendor: str) -> tuple[str | None, dict | None]:
        """Resolve + validate the vendor_ref for *device*.

        Returns ``(device_ref, None)`` on success or ``(None, error_dict)`` if
        the ref fails W1.2 validation. Mirrors the historical per-vendor logic:
        ``vendor_ref`` or ``device_id`` with the ``{vendor}.`` prefix stripped.
        The validation runs before any caller I/O; the error string is the
        byte-stable ``Invalid vendor_ref {ref!r}: must match ^[\\w.\\-]+$``.
        """
        device_ref = device.get("vendor_ref") or device.get("device_id", "").replace(f"{vendor}.", "")
        if not is_valid_device_ref(device_ref):
            from loguru import logger

            logger.warning("%s dispatch rejected: invalid device_ref %r", vendor, device_ref)
            return None, {
                "success": False,
                "error": f"Invalid vendor_ref {device_ref!r}: must match ^[\\w.\\-]+$",
            }
        return device_ref, None


class VendorParser(ABC):
    """Base class for a vendor's parse + dispatch behaviour."""

    vendor: str = ""

    # ── parse (pure) ───────────────────────────────────────────────
    @abstractmethod
    def matches(self, parts: list[str]) -> bool:
        """Return True if this parser handles the given topic parts."""

    @abstractmethod
    def parse(self, parts: list[str], payload: dict):
        """Return a DeviceObservation (or None) for the topic parts/payload."""

    # ── dispatch (side-effects) ────────────────────────────────────
    @abstractmethod
    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        """Execute *action* on *device*. Returns {"success": bool, ...}."""
