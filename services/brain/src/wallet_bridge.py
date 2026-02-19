"""WalletBridge: MQTT heartbeat → Wallet REST API relay.

Forwards device heartbeats to the Wallet service so that mesh leaf devices
(which cannot make REST calls directly) still receive infrastructure rewards.
Includes device metrics and utility_score from the DeviceRegistry.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)


class WalletBridge:
    def __init__(self, session, device_registry):
        self.session = session
        self.device_registry = device_registry
        self.wallet_url = os.getenv("WALLET_SERVICE_URL", "http://wallet:8000")
        self._last_forwarded: dict[str, float] = {}
        self.forward_interval = 300  # 5 min throttle

    async def forward_heartbeat(self, device_id: str, payload: dict):
        """Forward a heartbeat to Wallet service with DeviceRegistry metrics.

        Throttled to at most once per forward_interval per device.
        """
        now = time.time()
        last = self._last_forwarded.get(device_id, 0)
        if now - last < self.forward_interval:
            return

        device_info = self.device_registry.get_device(device_id)
        body = {}
        if device_info:
            body["power_mode"] = device_info.power_mode
            body["battery_pct"] = device_info.battery_pct
            body["hops_to_mqtt"] = device_info.hops_to_mqtt
            body["utility_score"] = device_info.utility_score

        url = f"{self.wallet_url}/devices/{device_id}/heartbeat"
        try:
            async with self.session.post(url, json=body, timeout=10) as resp:
                if resp.status == 200:
                    self._last_forwarded[device_id] = now
                    logger.debug("Heartbeat forwarded: %s → Wallet", device_id)
                elif resp.status == 404:
                    # Device not registered in Wallet — skip silently
                    self._last_forwarded[device_id] = now
                else:
                    text = await resp.text()
                    logger.warning(
                        "Heartbeat forward failed: %s → %d %s",
                        device_id, resp.status, text[:200],
                    )
        except Exception as e:
            logger.warning("Heartbeat forward error: %s → %s", device_id, e)

    async def forward_children(self, parent_id: str, payload: dict):
        """Forward heartbeats for child devices listed in the payload."""
        children = payload.get("children", [])
        for child_data in children:
            child_id = child_data.get("device_id")
            if not child_id:
                continue
            # Use dot notation for child IDs
            if "." not in child_id and "." not in parent_id:
                full_child_id = f"{parent_id}.{child_id}"
            else:
                full_child_id = child_id
            await self.forward_heartbeat(full_child_id, child_data)
