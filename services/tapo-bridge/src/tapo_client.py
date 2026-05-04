"""python-kasa wrapper for Tapo P-series plugs.

python-kasa supports both Kasa and Tapo devices via the same API. For Tapo,
credentials (cloud account username/password) must be provided at discover time
even for local LAN control.
"""

from __future__ import annotations

from typing import Any

from kasa import Credentials, Device, Discover
from loguru import logger


class TapoClient:
    """Thin wrapper to connect to and control Tapo devices by IP."""

    def __init__(self, username: str, password: str):
        self._creds = Credentials(username=username, password=password)
        self._cache: dict[str, Device] = {}

    async def _connect(self, ip: str) -> Device | None:
        if ip in self._cache:
            return self._cache[ip]
        try:
            device = await Discover.discover_single(ip, credentials=self._creds)
            await device.update()
            self._cache[ip] = device
            return device
        except Exception as e:
            logger.error(f"Tapo connect failed {ip}: {e}")
            return None

    async def get_status(self, ip: str) -> dict[str, Any] | None:
        device = await self._connect(ip)
        if device is None:
            return None
        try:
            await device.update()
        except Exception as e:
            logger.warning(f"Tapo update failed {ip}: {e}")
            self._cache.pop(ip, None)
            return None

        payload: dict[str, Any] = {
            "state": "on" if device.is_on else "off",
            "on": device.is_on,
            "model": device.model,
            "alias": device.alias,
            "rssi": device.rssi,
        }

        # Emeter-capable plugs (P110, P115, etc.) expose energy module
        try:
            energy = device.modules.get("Energy") if hasattr(device, "modules") else None
            if energy is not None:
                payload["power_watts"] = float(getattr(energy, "current_consumption", 0.0) or 0.0)
                total = getattr(energy, "consumption_total", None)
                if total is not None:
                    payload["energy_kwh"] = float(total)
                voltage = getattr(energy, "voltage", None)
                if voltage is not None:
                    payload["voltage"] = float(voltage)
                current = getattr(energy, "current", None)
                if current is not None:
                    payload["current"] = float(current)
        except Exception as e:
            logger.debug(f"Tapo energy read skipped {ip}: {e}")

        return payload

    async def turn_on(self, ip: str) -> bool:
        device = await self._connect(ip)
        if device is None:
            return False
        try:
            await device.turn_on()
            return True
        except Exception as e:
            logger.error(f"Tapo turn_on failed {ip}: {e}")
            return False

    async def turn_off(self, ip: str) -> bool:
        device = await self._connect(ip)
        if device is None:
            return False
        try:
            await device.turn_off()
            return True
        except Exception as e:
            logger.error(f"Tapo turn_off failed {ip}: {e}")
            return False

    async def toggle(self, ip: str) -> bool:
        device = await self._connect(ip)
        if device is None:
            return False
        try:
            if device.is_on:
                await device.turn_off()
            else:
                await device.turn_on()
            return True
        except Exception as e:
            logger.error(f"Tapo toggle failed {ip}: {e}")
            return False
