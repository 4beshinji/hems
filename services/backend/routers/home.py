"""
Home Assistant control proxy router.
Frontend → Backend → ha-bridge for smart home device control.
"""
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/home", tags=["home"])

HA_BRIDGE_URL = os.getenv("HA_BRIDGE_URL", "")

_home_store: dict = {}


# --- Pydantic models ---

class LightControl(BaseModel):
    entity_id: str
    on: bool
    brightness: int | None = None
    color_temp: int | None = None


class ClimateControl(BaseModel):
    entity_id: str
    mode: str | None = None
    temperature: float | None = None
    fan_mode: str | None = None


class CoverControl(BaseModel):
    entity_id: str
    action: str | None = None
    position: int | None = None


# --- Endpoints ---

@router.get("/")
async def get_home():
    """Return latest smart home device states."""
    return _home_store if _home_store else {"status": "no_data"}


@router.post("/snapshot")
async def update_home(data: dict):
    """Receive home device snapshot from Brain."""
    _home_store.clear()
    _home_store.update(data)
    return {"updated": True}


@router.post("/light/control")
async def control_light(cmd: LightControl):
    """Control a light via ha-bridge proxy."""
    if not HA_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="HA bridge not configured")

    service = "light/turn_on" if cmd.on else "light/turn_off"
    data = {}
    if cmd.on and cmd.brightness is not None:
        data["brightness"] = cmd.brightness
    if cmd.on and cmd.color_temp is not None:
        data["color_temp"] = cmd.color_temp

    return await _ha_proxy_call(cmd.entity_id, service, data)


@router.post("/climate/control")
async def control_climate(cmd: ClimateControl):
    """Control a climate device via ha-bridge proxy."""
    if not HA_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="HA bridge not configured")

    if cmd.mode == "off":
        return await _ha_proxy_call(cmd.entity_id, "climate/turn_off")

    data = {}
    if cmd.mode:
        data["hvac_mode"] = cmd.mode
    if cmd.temperature is not None:
        data["temperature"] = cmd.temperature
    if cmd.fan_mode:
        data["fan_mode"] = cmd.fan_mode

    if cmd.mode and cmd.temperature is not None:
        await _ha_proxy_call(cmd.entity_id, "climate/set_hvac_mode", {"hvac_mode": cmd.mode})
        return await _ha_proxy_call(cmd.entity_id, "climate/set_temperature", {
            "temperature": cmd.temperature,
            **({"fan_mode": cmd.fan_mode} if cmd.fan_mode else {}),
        })

    service = "climate/set_hvac_mode" if cmd.mode else "climate/set_temperature"
    return await _ha_proxy_call(cmd.entity_id, service, data)


@router.post("/cover/control")
async def control_cover(cmd: CoverControl):
    """Control a cover via ha-bridge proxy."""
    if not HA_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="HA bridge not configured")

    if cmd.position is not None:
        return await _ha_proxy_call(cmd.entity_id, "cover/set_cover_position",
                                    {"position": cmd.position})
    if cmd.action == "open":
        return await _ha_proxy_call(cmd.entity_id, "cover/open_cover")
    elif cmd.action == "close":
        return await _ha_proxy_call(cmd.entity_id, "cover/close_cover")
    elif cmd.action == "stop":
        return await _ha_proxy_call(cmd.entity_id, "cover/stop_cover")

    raise HTTPException(status_code=400, detail="No action or position specified")


@router.get("/devices")
async def get_home_devices():
    """Proxy device list from ha-bridge."""
    if not HA_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="HA bridge not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{HA_BRIDGE_URL}/api/devices")
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))


async def _ha_proxy_call(entity_id: str, service: str, data: dict | None = None) -> dict:
    """Forward a service call to ha-bridge."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{HA_BRIDGE_URL}/api/device/control",
                json={"entity_id": entity_id, "service": service, "data": data or {}},
            )
            if resp.status_code == 200:
                return {"success": True, "result": f"{service} -> {entity_id}"}
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))
