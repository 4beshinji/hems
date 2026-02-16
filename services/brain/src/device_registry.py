"""
Device registry — tracks connected edge devices.
Simplified from SOMS (removed utility_score/decay).
"""
import time
from loguru import logger


class DeviceInfo:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.last_seen: float = 0
        self.ip: str = ""
        self.firmware: str = ""
        self.zone: str = ""
        self.channels: list[str] = []

    @property
    def is_online(self) -> bool:
        return (time.time() - self.last_seen) < 120  # 2 min timeout


class DeviceRegistry:
    def __init__(self):
        self.devices: dict[str, DeviceInfo] = {}

    def update_from_heartbeat(self, device_id: str, payload: dict):
        if device_id not in self.devices:
            self.devices[device_id] = DeviceInfo(device_id)
            logger.info(f"New device registered: {device_id}")

        dev = self.devices[device_id]
        dev.last_seen = time.time()
        dev.ip = payload.get("ip", dev.ip)
        dev.firmware = payload.get("firmware", dev.firmware)
        dev.zone = payload.get("zone", dev.zone)
        dev.channels = payload.get("channels", dev.channels)

    def get_status_summary(self) -> str:
        if not self.devices:
            return ""
        lines = []
        for dev_id, dev in self.devices.items():
            status = "online" if dev.is_online else "offline"
            lines.append(f"- {dev_id} [{status}] zone={dev.zone} channels={','.join(dev.channels)}")
        return "\n".join(lines)

    def record_zone_action(self, zone: str, action_type: str):
        pass  # Simplified — no utility scoring in HEMS
