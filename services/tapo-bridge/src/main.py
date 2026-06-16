"""
HEMS tapo-bridge — connects Tapo P-series plugs to HEMS via MQTT + REST.

Polling: periodically reads device status → MQTT publish (hems/tapo/{ref}/state)
REST: accepts control commands from Brain → python-kasa → device
"""

from contextlib import asynccontextmanager

from device_mapper import DeviceMapper
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel
from tapo_client import TapoClient

import config
from hems_common import MqttPublisher, bridge_lifespan, publish_bridge_status, verify_internal_token

cfg: config.Config | None = None
device_mapper: DeviceMapper | None = None
mqtt_pub: MqttPublisher | None = None
tapo: TapoClient | None = None

# Routers: /health stays public for Docker healthchecks; all other REST routes
# require the internal bearer token when HEMS_INTERNAL_TOKEN is configured.
public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(verify_internal_token)])


async def _poll_loop():
    import asyncio

    assert cfg and device_mapper and mqtt_pub and tapo
    while True:
        try:
            for vendor_ref in device_mapper.all_refs():
                ip = device_mapper.get_ip(vendor_ref)
                if not ip:
                    continue
                status = await tapo.get_status(ip)
                if status is None:
                    continue
                zone = device_mapper.get_zone(vendor_ref)
                name = device_mapper.get_name(vendor_ref)
                payload = {
                    "entity_id": f"tapo.{vendor_ref}",
                    "vendor_ref": vendor_ref,
                    "zone": zone,
                    "friendly_name": name,
                    "domain": "switch",
                    **status,
                }
                mqtt_pub.publish(device_mapper.mqtt_topic(vendor_ref), payload)
        except Exception as e:
            logger.warning(f"Tapo poll loop error: {e}")
        await asyncio.sleep(cfg.poll_interval_sec)


async def _status_loop():
    import asyncio

    assert cfg and mqtt_pub and device_mapper
    while True:
        try:
            publish_bridge_status(
                mqtt_pub,
                "tapo",
                device_count=len(device_mapper.all_refs()),
            )
        except Exception as e:
            logger.debug(f"Status loop error: {e}")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cfg, device_mapper, mqtt_pub, tapo
    cfg = config.load_config()
    device_mapper = DeviceMapper(cfg)

    # MQTT — tapo: retain=True, error-level error, no connection tracking (unconditional publish)
    mqtt_pub = MqttPublisher(
        cfg.mqtt_broker,
        cfg.mqtt_port,
        cfg.mqtt_user,
        cfg.mqtt_pass,
        default_retain=True,
        default_qos=0,
        ensure_ascii=False,
        error_level="error",
        raise_on_connect_error=False,
        track_connection=False,
        auto_reconnect=True,
    )

    async def _startup():
        global tapo
        if not cfg.tapo_username or not cfg.tapo_password:
            logger.warning("TAPO_USERNAME / TAPO_PASSWORD not set — Tapo devices will fail")
        tapo = TapoClient(cfg.tapo_username, cfg.tapo_password)
        if not cfg.devices:
            logger.warning("TAPO_DEVICES empty — no devices will be polled")

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=[_poll_loop, _status_loop],
    ):
        logger.info(f"tapo-bridge started with {len(cfg.devices)} devices")
        yield


app = FastAPI(title="HEMS Tapo Bridge", lifespan=lifespan)


@public_router.get("/health")
async def health():
    return {
        "status": "ok",
        "device_count": len(device_mapper.all_refs()) if device_mapper else 0,
    }


@private_router.get("/api/devices")
async def list_devices():
    if not device_mapper:
        return {"devices": []}
    items = []
    for ref in device_mapper.all_refs():
        items.append(
            {
                "vendor_ref": ref,
                "device_id": f"tapo.{ref}",
                "ip": device_mapper.get_ip(ref),
                "zone": device_mapper.get_zone(ref),
                "name": device_mapper.get_name(ref),
            }
        )
    return {"devices": items}


@private_router.get("/api/devices/{vendor_ref}/status")
async def device_status(vendor_ref: str):
    if not device_mapper or not tapo:
        raise HTTPException(status_code=503, detail="bridge not initialized")
    ip = device_mapper.get_ip(vendor_ref)
    if not ip:
        raise HTTPException(status_code=404, detail=f"Unknown device '{vendor_ref}'")
    status = await tapo.get_status(ip)
    if status is None:
        raise HTTPException(status_code=502, detail=f"Failed to read Tapo {ip}")
    return {"vendor_ref": vendor_ref, "ip": ip, **status}


class CommandRequest(BaseModel):
    command: str  # turnOn | turnOff | toggle
    parameter: str | None = None


_ALLOWED_COMMANDS = {"turnOn", "turnOff", "toggle"}


@private_router.post("/api/devices/{vendor_ref}/command")
async def device_command(vendor_ref: str, body: CommandRequest):
    if not device_mapper or not tapo:
        raise HTTPException(status_code=503, detail="bridge not initialized")
    if body.command not in _ALLOWED_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Command '{body.command}' not in {sorted(_ALLOWED_COMMANDS)}",
        )

    ip = device_mapper.get_ip(vendor_ref)
    if not ip:
        raise HTTPException(status_code=404, detail=f"Unknown device '{vendor_ref}'")

    if body.command == "turnOn":
        ok = await tapo.turn_on(ip)
    elif body.command == "turnOff":
        ok = await tapo.turn_off(ip)
    else:
        ok = await tapo.toggle(ip)

    if not ok:
        raise HTTPException(status_code=502, detail=f"Tapo {body.command} failed")

    # Refresh state and publish immediately
    status = await tapo.get_status(ip)
    if status is not None and mqtt_pub is not None:
        zone = device_mapper.get_zone(vendor_ref)
        name = device_mapper.get_name(vendor_ref)
        mqtt_pub.publish(
            device_mapper.mqtt_topic(vendor_ref),
            {
                "entity_id": f"tapo.{vendor_ref}",
                "vendor_ref": vendor_ref,
                "zone": zone,
                "friendly_name": name,
                "domain": "switch",
                **status,
            },
        )

    return {"success": True, "command": body.command, "vendor_ref": vendor_ref}


app.include_router(public_router)
app.include_router(private_router)
