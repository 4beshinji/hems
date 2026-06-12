"""Zigbee (zigbee2mqtt) vendor parser + dispatch + Z2M bridge metadata parser."""

from __future__ import annotations

import json
import re
from typing import Any

from brain_utils import parse_iso_ts as _parse_iso_ts
from devices.actions import _zigbee_payload_for
from devices.base import DispatchContext, VendorParser
from devices.observation import _SENSOR_CHANNEL_UNITS, DeviceObservation


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


class ZigbeeParser(VendorParser):
    vendor = "zigbee"

    def matches(self, parts: list[str]) -> bool:
        # zigbee2mqtt/{device} (excluding bridge/*)
        return len(parts) >= 2 and parts[0] == "zigbee2mqtt" and not parts[1].startswith("bridge")

    def parse(self, parts: list[str], payload: dict) -> DeviceObservation | None:
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

    async def dispatch(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        # Zigbee dispatch is synchronous (MQTT publish + loop.call_later); the
        # async signature here just satisfies the ABC. Core routes through the
        # sync method to preserve the historical no-await call contract.
        return self.dispatch_sync(ctx, device, action, params)

    def dispatch_sync(self, ctx: DispatchContext, device: dict, action: str, params: dict) -> dict[str, Any]:
        if ctx.mqtt_client is None:
            return {"success": False, "error": "MQTT client not available for Zigbee dispatch"}
        # W1.2: guard before injecting device_ref into MQTT topic
        device_ref, err = DispatchContext.resolve_ref(device, "zigbee")
        if err is not None:
            return err
        payload = _zigbee_payload_for(action, params)
        if payload is None and action not in ("pulse", "rainbow"):
            return {"success": False, "error": f"action '{action}' not mapped for Zigbee"}

        # pulse: on → schedule off (non-blocking via asyncio)
        if action == "pulse":
            duration = int(params.get("duration_s", 10))
            if duration > 600:
                return {"success": False, "error": "pulse duration_s > 600 rejected"}
            ctx.mqtt_client.publish(
                f"zigbee2mqtt/{device_ref}/set",
                json.dumps({"state": "ON"}),
            )
            loop = ctx.asyncio.get_running_loop()
            loop.call_later(
                duration,
                lambda: ctx.mqtt_client.publish(
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
            ctx.mqtt_client.publish(topic, json.dumps({"state": "ON", "brightness": 254}))
            loop = ctx.asyncio.get_running_loop()
            for i in range(steps):
                hue = 360.0 * i / steps
                delay = interval * (i + 1)
                loop.call_later(
                    delay,
                    lambda h=hue: ctx.mqtt_client.publish(
                        topic,
                        json.dumps({"color": {"hue": h, "saturation": 100}}),
                    ),
                )
            # Restore warm white after rainbow
            loop.call_later(
                duration + 0.5,
                lambda: ctx.mqtt_client.publish(
                    topic,
                    json.dumps({"color_temp": 350}),
                ),
            )
            return {"success": True, "result": f"zigbee rainbow {duration}s ({steps} steps) -> {device_ref}"}

        ctx.mqtt_client.publish(f"zigbee2mqtt/{device_ref}/set", json.dumps(payload))
        return {"success": True, "result": f"zigbee {action} -> {device_ref}"}

    def permit_join(self, ctx: DispatchContext, enable: bool, duration_s: int = 0) -> dict[str, Any]:
        """Request Z2M coordinator to allow/deny new device joins.

        duration_s=0 + enable=True means "open until manually closed".
        Z2M auto-closes after its configured permit_join_timeout otherwise.
        """
        if ctx.mqtt_client is None:
            return {"success": False, "error": "MQTT client not available"}
        if duration_s < 0 or duration_s > 3600:
            return {"success": False, "error": "duration_s must be 0..3600"}
        payload: dict = {"value": bool(enable)}
        if enable and duration_s > 0:
            payload["time"] = duration_s
        ctx.mqtt_client.publish(
            "zigbee2mqtt/bridge/request/permit_join",
            json.dumps(payload),
        )
        action = f"open{f' ({duration_s}s)' if duration_s else ''}" if enable else "close"
        return {"success": True, "result": f"zigbee permit_join {action}"}
