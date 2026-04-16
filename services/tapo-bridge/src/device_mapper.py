"""Map vendor_ref (e.g. 'plug_desklight') ↔ IP/zone/name."""
from config import Config


class DeviceMapper:
    """Resolves device metadata from config env vars."""

    def __init__(self, cfg: Config):
        self.devices = cfg.devices  # {vendor_ref: ip}
        self.zones = cfg.zones
        self.names = cfg.names

    def all_refs(self) -> list[str]:
        return list(self.devices.keys())

    def get_ip(self, vendor_ref: str) -> str | None:
        return self.devices.get(vendor_ref)

    def get_zone(self, vendor_ref: str) -> str:
        return self.zones.get(vendor_ref, "home")

    def get_name(self, vendor_ref: str) -> str:
        return self.names.get(vendor_ref, vendor_ref)

    def mqtt_topic(self, vendor_ref: str) -> str:
        return f"hems/tapo/{vendor_ref}/state"
