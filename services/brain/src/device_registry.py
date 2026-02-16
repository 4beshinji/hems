"""
DeviceRegistry: Unified device metadata, state, and network topology manager.

Tracks all devices (Namaeda/Kareda/Ha/Remote) and provides:
- Adaptive timeout calculation based on device state
- LLM-friendly status summaries and tree views
- Automatic state transitions (online → stale → offline)
"""

import time
import logging

logger = logging.getLogger(__name__)

# State thresholds (seconds since last_seen)
ONLINE_THRESHOLD = 120       # 2 minutes
STALE_THRESHOLD = 900        # 15 minutes

# Adaptive timeouts by device state
TIMEOUT_BY_STATE = {
    "online": 10.0,
    "sleeping": 30.0,   # queued, wait for wake
    "stale": 20.0,
    "offline": 5.0,     # fast-fail
}


class DeviceInfo:
    """Single device metadata."""

    __slots__ = (
        "device_id", "device_type", "power_mode", "state",
        "parent_id", "children", "hops_to_mqtt", "battery_pct",
        "last_seen", "next_wake_epoch", "capabilities", "queue_status",
    )

    def __init__(self, device_id: str, device_type: str = "unknown"):
        self.device_id: str = device_id
        self.device_type: str = device_type          # namaeda|kareda|ha|remote
        self.power_mode: str = "ALWAYS_ON"
        self.state: str = "online"
        self.parent_id: str | None = None
        self.children: dict[str, "DeviceInfo"] = {}
        self.hops_to_mqtt: int = 0
        self.battery_pct: int | None = None
        self.last_seen: float = time.time()
        self.next_wake_epoch: float | None = None
        self.capabilities: list[str] = []
        self.queue_status: dict | None = None        # {"queued_count": N, "targets": [...]}

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "power_mode": self.power_mode,
            "state": self.state,
            "parent_id": self.parent_id,
            "hops_to_mqtt": self.hops_to_mqtt,
            "battery_pct": self.battery_pct,
            "children": list(self.children.keys()),
        }


class DeviceRegistry:
    """Central registry for all device metadata and network topology."""

    def __init__(self):
        self.devices: dict[str, DeviceInfo] = {}

    def update_from_heartbeat(self, device_id: str, payload: dict):
        """
        Update device tree from a heartbeat message.

        Expected payload keys (all optional):
        - device_type: str
        - power_mode: str
        - battery_pct: int | None
        - hops_to_mqtt: int
        - capabilities: list[str]
        - next_wake_sec: int (seconds until next wake)
        - queue_status: dict
        - children: list[dict] (same shape, recursive)
        """
        device = self._ensure_device(device_id)
        self._apply_payload(device, payload)
        device.last_seen = time.time()

        # Recurse into children
        for child_data in payload.get("children", []):
            child_id = child_data.get("device_id")
            if not child_id:
                continue
            # Use dot notation for child IDs if not already qualified
            if "." not in child_id and "." not in device_id:
                full_child_id = f"{device_id}.{child_id}"
            else:
                full_child_id = child_id

            child = self._ensure_device(full_child_id)
            self._apply_payload(child, child_data)
            child.parent_id = device_id
            child.last_seen = time.time()
            device.children[full_child_id] = child

        self._update_device_states()
        logger.debug(f"Registry updated from heartbeat: {device_id} ({len(self.devices)} devices total)")

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Look up a device by ID (supports dot-separated IDs)."""
        return self.devices.get(device_id)

    def get_timeout_for_device(self, agent_id: str) -> float:
        """Calculate adaptive timeout based on device state."""
        device = self.devices.get(agent_id)
        if device is None:
            return 10.0  # default
        self._update_single_state(device)
        return TIMEOUT_BY_STATE.get(device.state, 10.0)

    def get_status_summary(self, zone_id: str | None = None) -> str:
        """Generate LLM-friendly device status summary."""
        if not self.devices:
            return ""

        self._update_device_states()

        # Filter by zone if specified (zone is the first part of device_id path)
        devices = list(self.devices.values())
        if zone_id:
            devices = [d for d in devices if d.device_id.startswith(zone_id)]

        if not devices:
            return ""

        # Count by state
        counts = {"online": 0, "sleeping": 0, "stale": 0, "offline": 0}
        low_battery = []
        for d in devices:
            counts[d.state] = counts.get(d.state, 0) + 1
            if d.battery_pct is not None and d.battery_pct < 20:
                low_battery.append(d)

        lines = []
        total = len(devices)
        parts = []
        if counts["online"]:
            parts.append(f"online:{counts['online']}")
        if counts["sleeping"]:
            parts.append(f"sleeping:{counts['sleeping']}")
        if counts["stale"]:
            parts.append(f"stale:{counts['stale']}")
        if counts["offline"]:
            parts.append(f"offline:{counts['offline']}")
        lines.append(f"デバイス合計: {total}台 ({', '.join(parts)})")

        if low_battery:
            for d in low_battery:
                lines.append(f"⚠ 低バッテリー: {d.device_id} ({d.battery_pct}%)")

        if counts["offline"]:
            offline_devs = [d for d in devices if d.state == "offline"]
            for d in offline_devs[:5]:
                mins_ago = int((time.time() - d.last_seen) / 60)
                lines.append(f"✗ オフライン: {d.device_id} ({mins_ago}分前)")

        return "\n".join(lines)

    def get_device_tree(self, zone_id: str | None = None) -> str:
        """Generate tree-format device network display for LLM."""
        if not self.devices:
            return "デバイスネットワーク: デバイス未登録"

        self._update_device_states()

        # Find root devices (no parent)
        roots = [d for d in self.devices.values() if d.parent_id is None]
        if zone_id:
            roots = [d for d in roots if d.device_id.startswith(zone_id)]

        if not roots:
            return "デバイスネットワーク: 該当デバイスなし"

        lines = ["デバイスネットワーク:"]
        for root in sorted(roots, key=lambda d: d.device_id):
            self._render_tree_node(root, lines, indent=0)

        return "\n".join(lines)

    def _render_tree_node(self, device: DeviceInfo, lines: list, indent: int):
        """Recursively render a device tree node."""
        prefix = "  " * indent + ("├─ " if indent > 0 else "")
        state_icon = {"online": "●", "sleeping": "◐", "stale": "◌", "offline": "✗"}.get(device.state, "?")

        info_parts = [f"{state_icon} {device.device_id} [{device.device_type}]"]
        info_parts.append(device.state)
        if device.battery_pct is not None:
            info_parts.append(f"bat:{device.battery_pct}%")
        if device.power_mode != "ALWAYS_ON":
            info_parts.append(device.power_mode)
        if device.queue_status and device.queue_status.get("queued_count", 0) > 0:
            info_parts.append(f"queue:{device.queue_status['queued_count']}")

        lines.append(f"{prefix}{' | '.join(info_parts)}")

        for child in sorted(device.children.values(), key=lambda d: d.device_id):
            self._render_tree_node(child, lines, indent + 1)

    def _ensure_device(self, device_id: str) -> DeviceInfo:
        """Get or create a DeviceInfo entry."""
        if device_id not in self.devices:
            self.devices[device_id] = DeviceInfo(device_id)
        return self.devices[device_id]

    def _apply_payload(self, device: DeviceInfo, payload: dict):
        """Apply heartbeat payload fields to a DeviceInfo."""
        if "device_type" in payload:
            device.device_type = payload["device_type"]
        if "power_mode" in payload:
            device.power_mode = payload["power_mode"]
        if "battery_pct" in payload:
            device.battery_pct = payload["battery_pct"]
        if "hops_to_mqtt" in payload:
            device.hops_to_mqtt = payload["hops_to_mqtt"]
        if "capabilities" in payload:
            device.capabilities = payload["capabilities"]
        if "queue_status" in payload:
            device.queue_status = payload["queue_status"]
        if "next_wake_sec" in payload:
            wake_sec = payload["next_wake_sec"]
            if wake_sec and wake_sec > 0:
                device.next_wake_epoch = time.time() + wake_sec
            else:
                device.next_wake_epoch = None

    def _update_device_states(self):
        """Update all device states based on last_seen."""
        for device in self.devices.values():
            self._update_single_state(device)

    def _update_single_state(self, device: DeviceInfo):
        """Update a single device's state based on last_seen and power_mode."""
        elapsed = time.time() - device.last_seen

        # Sleeping devices stay sleeping if they have a scheduled wake
        if device.power_mode in ("DEEP_SLEEP", "ULTRA_LOW") and device.next_wake_epoch is not None:
            if elapsed < STALE_THRESHOLD:
                device.state = "sleeping"
                return

        if elapsed < ONLINE_THRESHOLD:
            device.state = "online"
        elif elapsed < STALE_THRESHOLD:
            device.state = "stale"
        else:
            device.state = "offline"
