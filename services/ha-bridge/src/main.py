"""
HEMS Home Assistant Bridge — connects HA to HEMS via MQTT.

WebSocket: HA state_changed events -> MQTT publish
REST API: Brain tool calls -> HA service calls
Polling fallback: when WebSocket disconnects
"""

import asyncio
from contextlib import asynccontextmanager

import aiohttp
from entity_mapper import EntityMapper
from fastapi import FastAPI, HTTPException
from ha_client import HAClient
from hems_common import MqttPublisher, bridge_lifespan, publish_bridge_status
from loguru import logger
from pydantic import BaseModel

import config

# Module-level shared state
ha_client: HAClient | None = None
mqtt_pub: MqttPublisher | None = None
entity_mapper: EntityMapper | None = None

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

        # Publish bridge status (canonical: hems/ha/bridge/status)
        publish_bridge_status(mqtt_pub, "ha", connected=ha_client.connected, mode="polling")
        await asyncio.sleep(config.STATE_POLL_INTERVAL)


async def _bridge_status_loop():
    """Periodically publish bridge connection status (canonical: hems/ha/bridge/status)."""
    while True:
        publish_bridge_status(
            mqtt_pub,
            "ha",
            connected=ha_client.connected,
            mode="websocket" if ha_client.connected else "disconnected",
        )
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ha_client, mqtt_pub, entity_mapper

    entity_mapper = EntityMapper(config.HEMS_HA_ENTITY_MAP)
    # ha: retain=True, no connection tracking (unconditional publish),
    # raise_on_connect_error=False (log and continue on MQTT failure).
    mqtt_pub = MqttPublisher(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_USER,
        config.MQTT_PASS,
        default_retain=True,
        track_connection=False,
        auto_reconnect=False,
        raise_on_connect_error=False,
    )

    ha_client = HAClient(config.HA_URL, config.HA_TOKEN)
    _session: aiohttp.ClientSession | None = None

    async def _startup():
        nonlocal _session
        _session = aiohttp.ClientSession()
        await ha_client.start(_session)
        logger.info(f"HA Bridge started (HA={config.HA_URL})")

    async def _shutdown():
        await ha_client.stop()
        if _session:
            await _session.close()
        logger.info("HA Bridge stopped")

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        # WebSocket reconnect_loop and status loop — ha_client is set before
        # task factories run (bridge_lifespan calls on_startup first).
        task_factories=(
            lambda: ha_client.reconnect_loop(_on_state_changed, _poll_states),
            _bridge_status_loop,
        ),
        on_shutdown=_shutdown,
    ):
        yield


app = FastAPI(title="HEMS HA Bridge", lifespan=lifespan)


# --- REST API ---

# Domains that could be used for command injection or dangerous operations
_BLOCKED_DOMAINS = {
    "shell_command",
    "command_line",
    "python_script",
    "script",
    "automation",
    "event",
    "persistent_notification",
}

# Per-domain parameter validation rules
_DOMAIN_VALIDATORS: dict[str, dict] = {
    "light": {
        "brightness": {"type": (int, float), "min": 0, "max": 255},
        "color_temp": {"type": (int, float), "min": 153, "max": 500},
        "transition": {"type": (int, float), "min": 0, "max": 300},
        "color_name": {"type": str, "max_len": 50},
        "rgb_color": {"type": list},
    },
    "climate": {
        "temperature": {"type": (int, float), "min": 16, "max": 30},
        "target_temp_high": {"type": (int, float), "min": 16, "max": 30},
        "target_temp_low": {"type": (int, float), "min": 16, "max": 30},
        "fan_mode": {"type": str, "max_len": 30},
        "hvac_mode": {"type": str, "max_len": 20},
    },
    "cover": {
        "position": {"type": (int, float), "min": 0, "max": 100},
        "tilt_position": {"type": (int, float), "min": 0, "max": 100},
    },
    "switch": {},
    "light.turn_on": {},
    "light.turn_off": {},
}


def _validate_ha_params(domain: str, service: str, data: dict) -> str | None:
    """Validate HA service call parameters. Returns error message or None."""
    # Block dangerous domains
    if domain in _BLOCKED_DOMAINS:
        return f"Domain '{domain}' is blocked for safety reasons"

    # Validate known parameters
    rules = _DOMAIN_VALIDATORS.get(domain, {})
    for param, value in data.items():
        if param not in rules:
            continue  # Unknown params pass through (HA will reject invalid ones)
        rule = rules[param]
        if "type" in rule and not isinstance(value, rule["type"]):
            return f"Parameter '{param}' has invalid type"
        if isinstance(value, (int, float)):
            if "min" in rule and value < rule["min"]:
                return f"Parameter '{param}' = {value} is below minimum {rule['min']}"
            if "max" in rule and value > rule["max"]:
                return f"Parameter '{param}' = {value} exceeds maximum {rule['max']}"
        if isinstance(value, str) and "max_len" in rule and len(value) > rule["max_len"]:
            return f"Parameter '{param}' string too long"

    return None


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

    # Validate parameters before forwarding to HA
    err = _validate_ha_params(domain, service, req.data)
    if err:
        raise HTTPException(400, f"Invalid parameters: {err}")

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
