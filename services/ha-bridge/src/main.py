"""
HEMS Home Assistant Bridge — connects HA to HEMS via MQTT.

WebSocket: HA state_changed events -> MQTT publish
REST API: Brain tool calls -> HA service calls
Polling fallback: when WebSocket disconnects
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiohttp
from loguru import logger

import config
from ha_client import HAClient
from mqtt_publisher import MQTTPublisher
from entity_mapper import EntityMapper

# Module-level shared state
ha_client: HAClient | None = None
mqtt_pub: MQTTPublisher | None = None
entity_mapper: EntityMapper | None = None
_tasks: list[asyncio.Task] = []

# Relevant HA domains for HEMS
_TRACKED_DOMAINS = {"light", "climate", "cover", "switch", "sensor", "binary_sensor"}


def _parse_ha_state(entity_id: str, state: dict) -> dict:
    """Extract relevant fields from HA state object."""
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    attrs = state.get("attributes", {})
    result = {
        "entity_id": entity_id,
        "state": state.get("state", "unknown"),
        "last_changed": state.get("last_changed", ""),
        "domain": domain,
    }

    if domain == "light":
        result["brightness"] = attrs.get("brightness", 0)
        result["color_temp"] = attrs.get("color_temp", 0)
        result["on"] = state.get("state") == "on"
    elif domain == "climate":
        result["temperature"] = attrs.get("temperature")
        result["current_temperature"] = attrs.get("current_temperature")
        result["hvac_mode"] = state.get("state", "off")
        result["fan_mode"] = attrs.get("fan_mode", "auto")
    elif domain == "cover":
        result["current_position"] = attrs.get("current_position", 0)
        result["is_open"] = state.get("state") == "open"
    elif domain == "switch":
        result["on"] = state.get("state") == "on"
    elif domain in ("sensor", "binary_sensor"):
        result["unit"] = attrs.get("unit_of_measurement", "")
        result["device_class"] = attrs.get("device_class", "")

    result["friendly_name"] = attrs.get("friendly_name", entity_id)
    return result


async def _on_state_changed(entity_id: str, new_state: dict):
    """Handle a state_changed event from HA WebSocket."""
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    if domain not in _TRACKED_DOMAINS:
        return

    parsed = _parse_ha_state(entity_id, new_state)
    topic = entity_mapper.get_mqtt_topic(entity_id)
    mqtt_pub.publish(topic, parsed)
    logger.debug(f"State changed: {entity_id} -> {parsed.get('state')}")


async def _poll_states():
    """Poll all HA states and publish to MQTT (fallback mode)."""
    while True:
        states = await ha_client.get_states()
        for s in states:
            entity_id = s.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            if domain in _TRACKED_DOMAINS:
                parsed = _parse_ha_state(entity_id, s)
                topic = entity_mapper.get_mqtt_topic(entity_id)
                mqtt_pub.publish(topic, parsed)

        # Publish bridge status
        mqtt_pub.publish("hems/home/bridge/status", {
            "connected": ha_client.connected,
            "mode": "polling",
        })
        await asyncio.sleep(config.STATE_POLL_INTERVAL)


async def _bridge_status_loop():
    """Periodically publish bridge connection status."""
    while True:
        mqtt_pub.publish("hems/home/bridge/status", {
            "connected": ha_client.connected,
            "mode": "websocket" if ha_client.connected else "disconnected",
        })
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ha_client, mqtt_pub, entity_mapper

    entity_mapper = EntityMapper(config.HEMS_HA_ENTITY_MAP)
    mqtt_pub = MQTTPublisher(config.MQTT_BROKER, config.MQTT_PORT,
                             config.MQTT_USER, config.MQTT_PASS)
    mqtt_pub.connect()

    ha_client = HAClient(config.HA_URL, config.HA_TOKEN)

    async with aiohttp.ClientSession() as session:
        await ha_client.start(session)

        # Start WebSocket event loop with polling fallback
        _tasks.append(asyncio.create_task(
            ha_client.reconnect_loop(_on_state_changed, _poll_states)
        ))
        _tasks.append(asyncio.create_task(_bridge_status_loop()))

        logger.info(f"HA Bridge started (HA={config.HA_URL})")
        yield

        for t in _tasks:
            t.cancel()
        await ha_client.stop()
        mqtt_pub.disconnect()
        logger.info("HA Bridge stopped")


app = FastAPI(title="HEMS HA Bridge", lifespan=lifespan)


# --- REST API ---

class DeviceControlRequest(BaseModel):
    entity_id: str
    service: str
    data: dict = {}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/device/control")
async def device_control(req: DeviceControlRequest):
    if not ha_client:
        raise HTTPException(503, "HA client not initialized")

    # Parse domain and service from the service string (e.g. "light/turn_on")
    # or use entity_id domain
    if "/" in req.service:
        domain, service = req.service.split("/", 1)
    else:
        domain = req.entity_id.split(".")[0] if "." in req.entity_id else ""
        service = req.service

    success = await ha_client.call_service(domain, service, req.entity_id, req.data)
    if success:
        return {"success": True, "result": f"Service {domain}/{service} called for {req.entity_id}"}
    raise HTTPException(502, f"HA service call failed: {domain}/{service}")


@app.get("/api/devices")
async def get_devices():
    if not ha_client:
        raise HTTPException(503, "HA client not initialized")

    states = await ha_client.get_states()
    devices = []
    for s in states:
        entity_id = s.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if domain in _TRACKED_DOMAINS:
            devices.append(_parse_ha_state(entity_id, s))
    return {"devices": devices}


@app.get("/api/device/{entity_id}")
async def get_device(entity_id: str):
    if not ha_client:
        raise HTTPException(503, "HA client not initialized")

    state = await ha_client.get_state(entity_id)
    if state is None:
        raise HTTPException(404, f"Entity {entity_id} not found")
    return _parse_ha_state(entity_id, state)
