"""
Device dispatcher — vendor-agnostic actuator control and topic parsing.

Phase 1 supports: ha, switchbot, mcp.
Phase 2 adds: tapo.
Phase 3 adds: zigbee (zigbee2mqtt).

Two responsibilities:
1. Parse incoming MQTT topic/payload → DeviceObservation for auto-registration
2. Execute action on a Device (DB row) → dispatch to the right bridge/MQTT publisher
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

from brain_utils import parse_iso_ts as _parse_iso_ts

HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")
SWITCHBOT_BRIDGE_URL = os.getenv("SWITCHBOT_BRIDGE_URL", "")
TAPO_BRIDGE_URL = os.getenv("TAPO_BRIDGE_URL", "")
DASHBOARD_API_URL = os.getenv("DASHBOARD_API_URL", os.getenv("BACKEND_URL", "http://backend:8000"))



@dataclass
class DeviceObservation:
    """Parsed from MQTT topic/payload, used for auto-registration heartbeat."""

    device_id: str
    vendor: str
    vendor_ref: str | None = None
    kind: str = "actuator"
    device_class: str | None = None
    capabilities: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    zone: str | None = None
    display_name: str | None = None
    description: str | None = None
    model_id: str | None = None
    manufacturer: str | None = None
    last_state: dict[str, Any] = field(default_factory=dict)
    last_value: dict[str, Any] = field(default_factory=dict)
    battery_pct: int | None = None
    link_quality: int | None = None
    last_seen_ts: float | None = None


# ── MQTT topic → DeviceObservation ─────────────────────────────────

_SENSOR_CHANNEL_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "co2": "ppm",
    "pressure": "hPa",
    "light": "lx",
    "illuminance": "lx",
    "voc": "",
    "soil_moisture": "%",
    "pm25": "µg/m³",
}


def parse_mqtt(topic: str, payload: dict) -> DeviceObservation | None:
    """Return a DeviceObservation if topic matches a known device pattern."""
    parts = topic.split("/")

    # office/{zone}/sensor/{device_id}/{channel}
    if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
        zone_id, device_name, channel = parts[1], parts[3], parts[4]
        device_id = f"mcp.{device_name}"
        value = payload.get(channel) or payload.get("value")
        last_value = {}
        if value is not None:
            try:
                last_value[channel] = float(value)
            except (TypeError, ValueError):
                pass
        unit = _SENSOR_CHANNEL_UNITS.get(channel, "")
        return DeviceObservation(
            device_id=device_id,
            vendor="mcp",
            vendor_ref=device_name,
            kind="sensor",
            device_class=_infer_sensor_class(channel),
            channels=[channel],
            units={channel: unit} if unit else {},
            zone=zone_id,
            last_value=last_value,
        )

    # hems/switchbot/{device_id}/state
    if len(parts) >= 3 and parts[0] == "hems" and parts[1] == "switchbot" and len(parts) >= 4 and parts[3] == "state":
        vendor_ref = parts[2]
        device_id = f"switchbot.{vendor_ref}"
        return DeviceObservation(
            device_id=device_id,
            vendor="switchbot",
            vendor_ref=vendor_ref,
            kind="both",
            device_class=_infer_switchbot_class(payload),
            capabilities=_infer_switchbot_caps(payload),
            zone=payload.get("zone"),
            last_state=_extract_state(payload),
            last_value=_extract_sensor_values(payload),
            battery_pct=payload.get("battery"),
            link_quality=payload.get("rssi") if isinstance(payload.get("rssi"), (int, float)) else None,
        )

    # hems/tapo/{device_id}/state
    if len(parts) >= 4 and parts[0] == "hems" and parts[1] == "tapo" and parts[3] == "state":
        vendor_ref = parts[2]
        device_id = f"tapo.{vendor_ref}"
        return DeviceObservation(
            device_id=device_id,
            vendor="tapo",
            vendor_ref=vendor_ref,
            kind="both",
            device_class="plug",
            capabilities=["on_off", "pulse"],
            zone=payload.get("zone"),
            last_state={"on": payload.get("state") == "on" or bool(payload.get("on"))},
            last_value={k: payload[k] for k in ("power_watts", "voltage", "current", "energy_kwh") if k in payload},
        )

    # zigbee2mqtt/{device}
    if len(parts) >= 2 and parts[0] == "zigbee2mqtt" and not parts[1].startswith("bridge"):
        vendor_ref = parts[1]
        device_id = f"zigbee.{vendor_ref}"
        caps = []
        last_state = {}
        if "state" in payload:
            caps.append("on_off")
            last_state["on"] = str(payload["state"]).upper() == "ON"
        if "brightness" in payload:
            caps.append("brightness")
            last_state["brightness"] = payload["brightness"]
        if "color_temp" in payload:
            caps.append("color_temp")
            last_state["color_temp"] = payload["color_temp"]
        if "color" in payload and isinstance(payload["color"], dict):
            color = payload["color"]
            if "x" in color and "y" in color:
                caps.append("color_xy")
                last_state["color_xy"] = {"x": color["x"], "y": color["y"]}
            if "hue" in color and "saturation" in color:
                caps.append("color_hs")
                last_state["color_hs"] = {"hue": color["hue"], "saturation": color["saturation"]}
        channels = []
        units = {}
        last_value = {}
        for ch in ("temperature", "humidity", "pressure", "illuminance", "co2", "soil_moisture"):
            if ch in payload:
                channels.append(ch)
                last_value[ch] = payload[ch]
                if ch in _SENSOR_CHANNEL_UNITS:
                    units[ch] = _SENSOR_CHANNEL_UNITS[ch]
        device_class = _infer_zigbee_class(caps, channels)
        kind = "both" if caps and channels else ("actuator" if caps else "sensor")
        return DeviceObservation(
            device_id=device_id,
            vendor="zigbee",
            vendor_ref=vendor_ref,
            kind=kind,
            device_class=device_class,
            capabilities=caps,
            channels=channels,
            units=units,
            last_state=last_state,
            last_value=last_value,
            battery_pct=payload.get("battery"),
            link_quality=payload.get("linkquality"),
            last_seen_ts=_parse_iso_ts(payload.get("last_seen")),
        )

    # hems/home/{zone}/{domain}/{entity_id}/state (HA bridge)
    if len(parts) >= 6 and parts[0] == "hems" and parts[1] == "home" and parts[5] == "state":
        zone_id, domain, entity_id = parts[2], parts[3], parts[4]
        # entity_id sometimes contains dots already; the ha-bridge flattens them
        ha_entity = payload.get("entity_id", f"{domain}.{entity_id}")
        device_id = f"ha.{ha_entity}"
        return DeviceObservation(
            device_id=device_id,
            vendor="ha",
            vendor_ref=ha_entity,
            kind=_infer_ha_kind(domain),
            device_class=_infer_ha_class(domain, payload),
            capabilities=_infer_ha_caps(domain, payload),
            zone=zone_id,
            last_state=_extract_ha_state(domain, payload),
            last_value=_extract_sensor_values(payload),
        )

    return None


def _infer_sensor_class(channel: str) -> str:
    if channel in ("temperature", "humidity"):
        return "temp_humidity"
    if channel == "co2":
        return "co2"
    if channel == "soil_moisture":
        return "soil"
    if channel in ("light", "illuminance"):
        return "light_sensor"
    return "sensor"


def _infer_switchbot_class(payload: dict) -> str:
    t = (payload.get("device_type") or payload.get("domain") or "").lower()
    if "plug" in t:
        return "plug"
    if "light" in t or "bulb" in t:
        return "light"
    if "hub" in t:
        return "hub_ir"
    if "curtain" in t or "blind" in t:
        return "curtain"
    if "meter" in t or "sensor" in t:
        return "temp_humidity"
    return t or "switchbot"


def _infer_switchbot_caps(payload: dict) -> list[str]:
    caps: list[str] = []
    dtype = (payload.get("device_type") or payload.get("domain") or "").lower()
    if "plug" in dtype or "switch" in dtype or "bulb" in dtype or "light" in dtype:
        caps.append("on_off")
    if "bulb" in dtype or "strip" in dtype:
        caps.extend(["brightness", "color_temp"])
    if "curtain" in dtype or "blind" in dtype:
        caps.append("set_position")
    if "hub" in dtype:
        caps.append("ir_send")
    if "plug" in dtype:
        caps.append("pulse")
    return caps


def _infer_zigbee_class(caps: list[str], channels: list[str]) -> str:
    if "brightness" in caps or "color_temp" in caps:
        return "light"
    if "on_off" in caps and not channels:
        return "plug"
    if "soil_moisture" in channels:
        return "soil"
    if "co2" in channels:
        return "co2"
    if "temperature" in channels and "humidity" in channels:
        return "temp_humidity"
    return "zigbee"


def _infer_ha_kind(domain: str) -> str:
    if domain in ("sensor", "binary_sensor"):
        return "sensor"
    if domain in ("light", "switch", "climate", "cover", "scene"):
        return "actuator"
    return "both"


def _infer_ha_class(domain: str, payload: dict) -> str:
    if domain == "light":
        return "light"
    if domain == "switch":
        return "plug"
    if domain == "climate":
        return "climate"
    if domain == "cover":
        return "curtain"
    device_class = payload.get("device_class")
    if device_class:
        return str(device_class)
    return domain


def _infer_ha_caps(domain: str, payload: dict) -> list[str]:
    caps: list[str] = []
    if domain == "light":
        caps.append("on_off")
        if "brightness" in payload:
            caps.append("brightness")
        if "color_temp" in payload:
            caps.append("color_temp")
    elif domain == "switch":
        caps.extend(["on_off", "pulse"])
    elif domain == "cover":
        caps.append("set_position")
    elif domain == "climate":
        caps.append("set_temperature")
    return caps


def _extract_state(payload: dict) -> dict[str, Any]:
    state = {}
    if "state" in payload:
        raw = payload["state"]
        if isinstance(raw, str):
            state["on"] = raw.lower() in ("on", "open", "true", "1")
        else:
            state["on"] = bool(raw)
    for k in ("brightness", "color_temp", "position", "power_state"):
        if k in payload:
            state[k] = payload[k]
    return state


def _extract_ha_state(domain: str, payload: dict) -> dict[str, Any]:
    state = {}
    raw = payload.get("state")
    if raw is not None:
        if domain == "cover":
            state["position"] = payload.get("current_position", 100 if raw == "open" else 0)
        else:
            state["on"] = str(raw).lower() in ("on", "open", "true", "1", "home")
    for k in ("brightness", "color_temp", "current_position", "current_temperature", "hvac_mode"):
        if k in payload:
            state[k] = payload[k]
    return state


def _extract_sensor_values(payload: dict) -> dict[str, Any]:
    values = {}
    for k in (
        "temperature",
        "humidity",
        "co2",
        "pressure",
        "light",
        "illuminance",
        "voc",
        "soil_moisture",
        "pm25",
        "power_watts",
        "voltage",
        "current",
        "energy_kwh",
        "power",
    ):
        if k in payload:
            values[k] = payload[k]
    return values


# ── Z2M bridge/devices metadata parser ────────────────────────────

_EXPOSE_TYPE_MAP = {
    "light": ("actuator", "light"),
    "switch": ("actuator", "switch"),
    "cover": ("actuator", "cover"),
    "climate": ("actuator", "climate"),
    "lock": ("actuator", "lock"),
    "fan": ("actuator", "fan"),
}

_EXPOSE_FEATURE_MAP = {
    "occupancy": ("sensor", "motion"),
    "contact": ("sensor", "door"),
    "temperature": ("sensor", "climate"),
    "humidity": ("sensor", "climate"),
    "illuminance": ("sensor", "illuminance"),
    "soil_moisture": ("sensor", "soil"),
    "water_leak": ("sensor", "leak"),
    "vibration": ("sensor", "vibration"),
    "power": ("sensor", "power"),
}

_FEATURE_TO_CAPABILITY = {
    "state": "on_off",
    "brightness": "brightness",
    "color_temp": "color_temp",
    "color_xy": "color_xy",
    "color_hs": "color_hs",
    "position": "set_position",
    "tilt": "set_tilt",
}


_IEEE_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{16}$")


def is_raw_ieee_addr(name: str | None) -> bool:
    """True if `name` looks like an unfriendly Zigbee IEEE address (e.g. 0xa4c138...)."""
    return bool(name and _IEEE_ADDR_RE.match(name))


def _clean_label(s: str | None) -> str:
    """Strip NUL bytes and control chars Z2M sometimes leaves in vendor strings."""
    if not s:
        return ""
    return "".join(c for c in s if c.isprintable() and c != "\x00").strip()


def _short_desc(desc: str, max_len: int = 50) -> str:
    """Trim long descriptions at the first comma (Z2M descriptions are spec-style:
    'TRADFRI bulb E26/E27, color/white spectrum, globe, opal, 800/806/810 lm')."""
    if not desc:
        return ""
    head = desc.split(",", 1)[0].strip()
    if len(head) <= max_len:
        return head
    return head[: max_len - 1].rstrip() + "…"


def _z2m_friendly_display(
    friendly: str,
    vendor: str | None,
    model: str | None,
    desc: str | None,
) -> str:
    """Build a human-readable display name from Z2M definition fields.

    If the Zigbee `friendly_name` was renamed by the user, keep it.
    Otherwise prefer the human-readable description ("HOBEIAN Vibration sensor")
    over the model code ("ZG-102ZM"), and append the IEEE short-id so that
    multiple identical sensors stay distinguishable.
    """
    if friendly and not is_raw_ieee_addr(friendly):
        return friendly
    vendor = _clean_label(vendor)
    desc = _short_desc(_clean_label(desc))
    model = _clean_label(model)
    # Z2M occasionally returns a placeholder description for unknown devices —
    # fall through to model_id in that case.
    if desc and "automatically generated" in desc.lower():
        desc = ""
    if desc:
        label = f"{vendor} {desc}".strip() if vendor and not desc.lower().startswith(vendor.lower()) else desc
    elif model:
        label = f"{vendor} {model}".strip() if vendor else model
    elif vendor:
        label = vendor
    else:
        label = "Zigbee device"
    if is_raw_ieee_addr(friendly):
        return f"{label} ({friendly[-6:]})"
    return label


def parse_z2m_bridge_devices(payload: list[dict]) -> list[DeviceObservation]:
    """Parse zigbee2mqtt/bridge/devices retained message into DeviceObservations."""
    observations: list[DeviceObservation] = []
    for dev in payload:
        friendly = dev.get("friendly_name")
        if not friendly or friendly == "Coordinator":
            continue
        definition = dev.get("definition") or {}
        if not definition:
            continue

        device_id = f"zigbee.{friendly}"
        model = definition.get("model")
        vendor = definition.get("vendor")
        desc = definition.get("description")
        exposes = definition.get("exposes") or []

        kind = "sensor"
        device_class = None
        capabilities: list[str] = []
        channels: list[str] = []

        for expose in exposes:
            etype = expose.get("type", "")

            if etype in _EXPOSE_TYPE_MAP:
                kind = _EXPOSE_TYPE_MAP[etype][0]
                device_class = _EXPOSE_TYPE_MAP[etype][1]
                for feat in expose.get("features") or []:
                    fname = feat.get("name", "")
                    cap = _FEATURE_TO_CAPABILITY.get(fname)
                    if cap and cap not in capabilities:
                        capabilities.append(cap)

            if etype == "enum" or etype == "binary" or etype == "numeric":
                fname = expose.get("name", "")
                if fname in _EXPOSE_FEATURE_MAP:
                    fkind, fclass = _EXPOSE_FEATURE_MAP[fname]
                    if kind == "sensor" and fkind == "sensor":
                        device_class = fclass
                    elif fkind == "sensor" and kind == "actuator":
                        kind = "both"
                    if fname not in channels:
                        channels.append(fname)

        if not device_class:
            continue

        is_battery = dev.get("power_source") == "Battery"
        description_text = f"{vendor} {desc}" if vendor and desc else (desc or model or "")
        display_name = _z2m_friendly_display(friendly, vendor, model, desc)

        obs = DeviceObservation(
            device_id=device_id,
            vendor="zigbee",
            vendor_ref=friendly,
            kind=kind,
            device_class=device_class,
            capabilities=capabilities,
            channels=channels,
            display_name=display_name,
            description=description_text,
            model_id=model,
            manufacturer=vendor,
            battery_pct=dev.get("battery"),
        )
        observations.append(obs)

    return observations


# ── Action → vendor bridge dispatch ────────────────────────────────


class DeviceDispatcher:
    """Central router for actuator commands across bridges.

    Looks up the device (by device_id) via backend, then dispatches based on vendor.
    Brain's ToolExecutor calls dispatch() for `control_actuator`.
    """

    def __init__(self, session: aiohttp.ClientSession, mqtt_client=None):
        self.session = session
        self.mqtt_client = mqtt_client  # paho client for zigbee2mqtt publish
        self.backend_url = DASHBOARD_API_URL

    async def lookup(self, device_id: str) -> dict | None:
        """Fetch device record from backend."""
        try:
            async with self.session.get(
                f"{self.backend_url}/devices/{device_id}",
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
        params = params or {}
        device = await self.lookup(device_id)
        if not device:
            return {"success": False, "error": f"Device '{device_id}' not registered"}

        vendor = device.get("vendor", "")
        caps = device.get("capabilities", []) or []

        # Per-action capability guardrail
        if action not in _ALLOWED_ACTIONS:
            return {"success": False, "error": f"Unknown action '{action}'"}
        required_cap = _ACTION_CAPABILITY.get(action)
        if required_cap and required_cap not in caps:
            return {"success": False, "error": f"Device does not advertise capability '{required_cap}' (has: {caps})"}

        if vendor == "ha":
            return await self._dispatch_ha(device, action, params)
        if vendor == "switchbot":
            return await self._dispatch_switchbot(device, action, params)
        if vendor == "tapo":
            return await self._dispatch_tapo(device, action, params)
        if vendor == "zigbee":
            return self._dispatch_zigbee(device, action, params)
        if vendor == "mcp":
            return {"success": False, "error": "MCP actuator control uses send_device_command tool"}

        return {"success": False, "error": f"Unsupported vendor '{vendor}'"}

    async def _dispatch_ha(self, device: dict, action: str, params: dict) -> dict:
        if not HA_BRIDGE_URL:
            return {"success": False, "error": "HA bridge not configured"}
        entity_id = device.get("vendor_ref") or device.get("device_id", "").replace("ha.", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""

        # rainbow: async hue cycling via repeated HA calls
        if action == "rainbow":
            duration = int(params.get("duration_s", 10))
            if duration > 60:
                return {"success": False, "error": "rainbow duration_s > 60 rejected"}
            asyncio.ensure_future(self._ha_rainbow(entity_id, duration))
            return {"success": True, "result": f"ha rainbow {duration}s -> {entity_id}"}

        service, data = _ha_service_for(action, params, domain)
        if service is None:
            return {"success": False, "error": f"action '{action}' not mapped for HA domain '{domain}'"}

        async with self.session.post(
            f"{HA_BRIDGE_URL}/api/device/control",
            json={"entity_id": entity_id, "service": service, "data": data or {}},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            result = await resp.json()
            if resp.status == 200:
                return {"success": True, "result": f"ha {action} -> {entity_id}"}
            return {"success": False, "error": result.get("detail", f"HTTP {resp.status}")}

    async def _ha_rainbow(self, entity_id: str, duration: int):
        """Cycle through rainbow hues via HA light/turn_on calls."""
        steps = min(duration * 2, 20)
        interval = duration / steps
        for i in range(steps):
            hue = 360.0 * i / steps
            try:
                async with self.session.post(
                    f"{HA_BRIDGE_URL}/api/device/control",
                    json={"entity_id": entity_id, "service": "light/turn_on",
                           "data": {"hs_color": [hue, 100], "brightness": 254}},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    await resp.read()
            except Exception:
                pass
            await asyncio.sleep(interval)
        # Restore warm white
        try:
            async with self.session.post(
                f"{HA_BRIDGE_URL}/api/device/control",
                json={"entity_id": entity_id, "service": "light/turn_on",
                       "data": {"color_temp": 350}},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                await resp.read()
        except Exception:
            pass

    async def _dispatch_switchbot(self, device: dict, action: str, params: dict) -> dict:
        if not SWITCHBOT_BRIDGE_URL:
            return {"success": False, "error": "SwitchBot bridge not configured"}
        device_ref = device.get("vendor_ref") or device.get("device_id", "").replace("switchbot.", "")

        cmd, parameter, cmd_type = _switchbot_cmd_for(action, params)
        if cmd is None:
            return {"success": False, "error": f"action '{action}' not mapped for SwitchBot"}

        async with self.session.post(
            f"{SWITCHBOT_BRIDGE_URL}/api/devices/{device_ref}/command",
            json={"command": cmd, "parameter": parameter, "command_type": cmd_type},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if resp.status == 200:
                return {"success": True, "result": f"switchbot {cmd} -> {device_ref}"}
            return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}

    async def _dispatch_tapo(self, device: dict, action: str, params: dict) -> dict:
        if not TAPO_BRIDGE_URL:
            return {"success": False, "error": "Tapo bridge not configured"}
        device_ref = device.get("vendor_ref") or device.get("device_id", "").replace("tapo.", "")

        # pulse is handled here: on → sleep → off
        if action == "pulse":
            duration = int(params.get("duration_s", 10))
            if duration > 600:
                return {"success": False, "error": "pulse duration_s > 600 rejected"}
            r1 = await self._tapo_raw(device_ref, "turnOn")
            if not r1.get("success"):
                return r1
            await asyncio.sleep(duration)
            r2 = await self._tapo_raw(device_ref, "turnOff")
            if not r2.get("success"):
                return {"success": False, "error": f"pulse on ok but off failed: {r2.get('error')}"}
            return {"success": True, "result": f"tapo pulse {duration}s -> {device_ref}"}

        cmd = {"on": "turnOn", "off": "turnOff", "toggle": "toggle"}.get(action)
        if not cmd:
            return {"success": False, "error": f"action '{action}' not supported by Tapo"}
        return await self._tapo_raw(device_ref, cmd)

    async def _tapo_raw(self, device_ref: str, command: str) -> dict:
        try:
            async with self.session.post(
                f"{TAPO_BRIDGE_URL}/api/devices/{device_ref}/command",
                json={"command": command},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": f"tapo {command} -> {device_ref}"}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _dispatch_zigbee(self, device: dict, action: str, params: dict) -> dict:
        if self.mqtt_client is None:
            return {"success": False, "error": "MQTT client not available for Zigbee dispatch"}
        device_ref = device.get("vendor_ref") or device.get("device_id", "").replace("zigbee.", "")
        payload = _zigbee_payload_for(action, params)
        if payload is None and action not in ("pulse", "rainbow"):
            return {"success": False, "error": f"action '{action}' not mapped for Zigbee"}

        # pulse: on → schedule off (non-blocking via asyncio)
        if action == "pulse":
            duration = int(params.get("duration_s", 10))
            if duration > 600:
                return {"success": False, "error": "pulse duration_s > 600 rejected"}
            self.mqtt_client.publish(
                f"zigbee2mqtt/{device_ref}/set",
                json.dumps({"state": "ON"}),
            )
            loop = asyncio.get_running_loop()
            loop.call_later(
                duration,
                lambda: self.mqtt_client.publish(
                    f"zigbee2mqtt/{device_ref}/set",
                    json.dumps({"state": "OFF"}),
                ),
            )
            return {"success": True, "result": f"zigbee pulse {duration}s -> {device_ref}"}

        # rainbow: cycle through hues over duration_s, then restore warm white
        if action == "rainbow":
            duration = int(params.get("duration_s", 10))
            if duration > 60:
                return {"success": False, "error": "rainbow duration_s > 60 rejected"}
            steps = min(duration * 2, 20)
            interval = duration / steps
            topic = f"zigbee2mqtt/{device_ref}/set"
            # Ensure light is on + full brightness
            self.mqtt_client.publish(topic, json.dumps({"state": "ON", "brightness": 254}))
            loop = asyncio.get_running_loop()
            for i in range(steps):
                hue = 360.0 * i / steps
                delay = interval * (i + 1)
                loop.call_later(
                    delay,
                    lambda h=hue: self.mqtt_client.publish(
                        topic,
                        json.dumps({"color": {"hue": h, "saturation": 100}}),
                    ),
                )
            # Restore warm white after rainbow
            loop.call_later(
                duration + 0.5,
                lambda: self.mqtt_client.publish(
                    topic,
                    json.dumps({"color_temp": 350}),
                ),
            )
            return {"success": True, "result": f"zigbee rainbow {duration}s ({steps} steps) -> {device_ref}"}

        self.mqtt_client.publish(f"zigbee2mqtt/{device_ref}/set", json.dumps(payload))
        return {"success": True, "result": f"zigbee {action} -> {device_ref}"}

    def zigbee_permit_join(self, enable: bool, duration_s: int = 0) -> dict:
        """Request Z2M coordinator to allow/deny new device joins.

        duration_s=0 + enable=True means "open until manually closed".
        Z2M auto-closes after its configured permit_join_timeout otherwise.
        """
        if self.mqtt_client is None:
            return {"success": False, "error": "MQTT client not available"}
        if duration_s < 0 or duration_s > 3600:
            return {"success": False, "error": "duration_s must be 0..3600"}
        payload: dict = {"value": bool(enable)}
        if enable and duration_s > 0:
            payload["time"] = duration_s
        self.mqtt_client.publish(
            "zigbee2mqtt/bridge/request/permit_join",
            json.dumps(payload),
        )
        action = f"open{f' ({duration_s}s)' if duration_s else ''}" if enable else "close"
        return {"success": True, "result": f"zigbee permit_join {action}"}


# ── Action capability allowlist ───────────────────────────────────

_ALLOWED_ACTIONS = {
    "on",
    "off",
    "toggle",
    "set_brightness",
    "set_color_temp",
    "set_color_xy",
    "set_color_hs",
    "set_position",
    "set_temperature",
    "pulse",
    "rainbow",
    "ir_send",
}

_ACTION_CAPABILITY = {
    "on": "on_off",
    "off": "on_off",
    "toggle": "on_off",
    "set_brightness": "brightness",
    "set_color_temp": "color_temp",
    "set_color_xy": "color_xy",
    "set_color_hs": "color_hs",
    "set_position": "set_position",
    "set_temperature": "set_temperature",
    "pulse": "pulse",
    "rainbow": "color_hs",
    "ir_send": "ir_send",
}


def _ha_service_for(action: str, params: dict, domain: str) -> tuple[str | None, dict]:
    if action == "on":
        return f"{domain}/turn_on", {}
    if action == "off":
        return f"{domain}/turn_off", {}
    if action == "toggle":
        return f"{domain}/toggle", {}
    if action == "set_brightness":
        return "light/turn_on", {"brightness": int(params.get("value", 128))}
    if action == "set_color_temp":
        return "light/turn_on", {"color_temp": int(params.get("value", 300))}
    if action == "set_color_xy":
        return "light/turn_on", {"xy_color": [float(params.get("x", 0.3)), float(params.get("y", 0.3))]}
    if action == "set_color_hs":
        return "light/turn_on", {"hs_color": [float(params.get("hue", 0)), float(params.get("saturation", 100))]}
    if action == "set_position":
        return "cover/set_cover_position", {"position": int(params.get("value", 100))}
    if action == "set_temperature":
        return "climate/set_temperature", {"temperature": float(params.get("value", 24))}
    return None, {}


def _switchbot_cmd_for(action: str, params: dict) -> tuple[str | None, str, str]:
    if action == "on":
        return "turnOn", "default", "command"
    if action == "off":
        return "turnOff", "default", "command"
    if action == "toggle":
        return "toggle", "default", "command"
    if action == "set_brightness":
        return "setBrightness", str(params.get("value", 50)), "command"
    if action == "set_color_temp":
        return "setColorTemperature", str(params.get("value", 3000)), "command"
    if action == "set_position":
        return "setPosition", f"0,ff,{params.get('value', 50)}", "command"
    if action == "ir_send":
        return params.get("command", "turnOn"), params.get("parameter", "default"), "customize"
    return None, "", ""


def _zigbee_payload_for(action: str, params: dict) -> dict | None:
    if action == "on":
        return {"state": "ON"}
    if action == "off":
        return {"state": "OFF"}
    if action == "toggle":
        return {"state": "TOGGLE"}
    if action == "set_brightness":
        return {"state": "ON", "brightness": int(params.get("value", 128))}
    if action == "set_color_temp":
        return {"color_temp": int(params.get("value", 300))}
    if action == "set_color_xy":
        return {"color": {"x": float(params.get("x", 0.3)), "y": float(params.get("y", 0.3))}}
    if action == "set_color_hs":
        return {"color": {"hue": float(params.get("hue", 0)), "saturation": float(params.get("saturation", 100))}}
    if action == "pulse":
        return {"state": "ON"}  # pulse itself is handled separately
    return None
