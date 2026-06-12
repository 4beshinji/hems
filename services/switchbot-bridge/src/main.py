"""
HEMS SwitchBot Bridge — connects SwitchBot Cloud API v1.1 to HEMS via MQTT.

Polling: Periodically fetches device status → MQTT publish
Webhook: Receives SwitchBot push events → MQTT publish
REST API: Brain tool calls → SwitchBot API commands
"""

import asyncio
from contextlib import asynccontextmanager

import aiohttp
from device_mapper import DeviceMapper
from fastapi import FastAPI, HTTPException, Request
from hems_common import MqttPublisher, bridge_lifespan, publish_bridge_status
from loguru import logger
from pydantic import BaseModel
from switchbot_client import SwitchBotClient

import config

# Module-level shared state
sb_client: SwitchBotClient | None = None
mqtt_pub: MqttPublisher | None = None
device_mapper: DeviceMapper | None = None

# Domains that publish sensor sub-entities (temperature, humidity from Meter/Hub)
_SENSOR_DOMAINS = {"sensor"}


def _publish_device_state(device_id: str, parsed: dict):
    """Publish parsed device state to MQTT."""
    domain = parsed.get("domain", "switch")
    topic = device_mapper.get_mqtt_topic(device_id, domain)

    # Override friendly_name with custom name if configured
    custom_name = device_mapper.get_name(device_id)
    if custom_name:
        parsed["friendly_name"] = custom_name

    mqtt_pub.publish(topic, parsed)

    # Sensor devices: also publish sub-entities for temp/humidity/co2
    if domain == "sensor":
        zone = device_mapper.get_zone(device_id)
        entity_base = f"switchbot.{device_id}"
        if "temperature" in parsed:
            mqtt_pub.publish(
                f"hems/home/{zone}/sensor/{entity_base}_temperature/state",
                {
                    "entity_id": f"{entity_base}_temperature",
                    "state": str(parsed["temperature"]),
                    "value": parsed["temperature"],
                    "unit": "°C",
                    "device_class": "temperature",
                    "friendly_name": f"{parsed.get('friendly_name', device_id)} 温度",
                    "domain": "sensor",
                },
            )
        if "humidity" in parsed:
            mqtt_pub.publish(
                f"hems/home/{zone}/sensor/{entity_base}_humidity/state",
                {
                    "entity_id": f"{entity_base}_humidity",
                    "state": str(parsed["humidity"]),
                    "value": parsed["humidity"],
                    "unit": "%",
                    "device_class": "humidity",
                    "friendly_name": f"{parsed.get('friendly_name', device_id)} 湿度",
                    "domain": "sensor",
                },
            )
        if "co2" in parsed:
            mqtt_pub.publish(
                f"hems/home/{zone}/sensor/{entity_base}_co2/state",
                {
                    "entity_id": f"{entity_base}_co2",
                    "state": str(parsed["co2"]),
                    "value": parsed["co2"],
                    "unit": "ppm",
                    "device_class": "carbon_dioxide",
                    "friendly_name": f"{parsed.get('friendly_name', device_id)} CO2",
                    "domain": "sensor",
                },
            )

    # Plug Mini: publish power as separate sensor entity
    if "power_watts" in parsed:
        zone = device_mapper.get_zone(device_id)
        entity_base = f"switchbot.{device_id}"
        mqtt_pub.publish(
            f"hems/home/{zone}/sensor/{entity_base}_power/state",
            {
                "entity_id": f"{entity_base}_power",
                "state": str(parsed["power_watts"]),
                "value": parsed["power_watts"],
                "unit": "W",
                "device_class": "power",
                "friendly_name": f"{parsed.get('friendly_name', device_id)} 電力",
                "domain": "sensor",
            },
        )


async def _poll_all_devices():
    """Poll all SwitchBot devices and publish status to MQTT."""
    while True:
        try:
            physical, infrared = await sb_client.get_devices()
            for device in physical:
                device_id = device["deviceId"]
                device_type = device.get("deviceType", "")
                domain = sb_client.get_domain(device_type)

                # Skip hubs (no useful status endpoint), vacuums, locks
                if domain in ("hub", "vacuum", "lock"):
                    # Hub 2 has sensor domain, so only skip pure hubs
                    if domain != "sensor":
                        continue

                status = await sb_client.get_device_status(device_id)
                if status:
                    parsed = sb_client.parse_status(device_id, status)
                    _publish_device_state(device_id, parsed)

            # Publish bridge status
            publish_bridge_status(
                mqtt_pub,
                "switchbot",
                device_count=len(physical),
                ir_device_count=len(infrared),
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Poll error: {e}")
            publish_bridge_status(mqtt_pub, "switchbot", connected=False)

        await asyncio.sleep(config.POLL_INTERVAL)


async def _bridge_status_loop():
    """Periodically publish bridge connection status."""
    while True:
        publish_bridge_status(mqtt_pub, "switchbot")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sb_client, mqtt_pub, device_mapper

    device_mapper = DeviceMapper(config.SWITCHBOT_DEVICE_MAP)

    # MQTT — switchbot profile: retain=True, error level=error, no connection tracking,
    # unconditional publish (track_connection=False), ensure_ascii=False
    mqtt_pub = MqttPublisher(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_USER,
        config.MQTT_PASS,
        default_retain=True,
        default_qos=0,
        ensure_ascii=False,
        error_level="error",
        raise_on_connect_error=False,
        track_connection=False,
        auto_reconnect=True,
    )

    sb_client = SwitchBotClient(config.SWITCHBOT_TOKEN, config.SWITCHBOT_SECRET)
    _session: aiohttp.ClientSession | None = None

    async def _startup():
        nonlocal _session
        _session = aiohttp.ClientSession()
        await sb_client.start(_session)

        physical, infrared = await sb_client.get_devices()
        logger.info(f"SwitchBot devices: {len(physical)} physical, {len(infrared)} IR")

        if config.WEBHOOK_URL:
            result = await sb_client._api_post(
                "/webhook/setupWebhook",
                {
                    "action": "setupWebhook",
                    "url": config.WEBHOOK_URL,
                    "deviceList": "ALL",
                },
            )
            if result:
                logger.info(f"SwitchBot webhook registered: {config.WEBHOOK_URL}")

    async def _shutdown():
        await sb_client.stop()
        if _session is not None:
            await _session.close()

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=[_poll_all_devices, _bridge_status_loop],
        on_shutdown=_shutdown,
    ):
        logger.info("SwitchBot Bridge started")
        yield
    logger.info("SwitchBot Bridge stopped")


app = FastAPI(title="HEMS SwitchBot Bridge", lifespan=lifespan)


# --- Command validation ---

# Allowed commands per domain (whitelist approach)
_ALLOWED_COMMANDS: dict[str, set[str]] = {
    "light": {"turnOn", "turnOff", "toggle", "setBrightness", "setColor", "setColorTemperature"},
    "cover": {"turnOn", "turnOff", "setPosition", "open", "close", "pause"},
    "switch": {"turnOn", "turnOff", "toggle", "press"},
    "climate": {"turnOn", "turnOff", "setAll"},
    "sensor": set(),  # sensors don't accept commands
    "binary_sensor": set(),
    "lock": {"lock", "unlock"},
    "hub": set(),
    "vacuum": {"start", "stop", "dock", "PowLevel"},
}


def _validate_command(device_id: str, command: str, parameter: str = "default") -> str | None:
    """Validate command. Returns error message or None."""
    device_info = sb_client.get_cached_device(device_id)
    if not device_info:
        return None  # Unknown device — let API reject it

    device_type = device_info.get("deviceType", "")
    domain = sb_client.get_domain(device_type)
    allowed = _ALLOWED_COMMANDS.get(domain, set())

    if allowed and command not in allowed:
        return f"Command '{command}' not allowed for {device_type} ({domain})"

    # Validate parameters for specific commands
    if command == "setBrightness":
        try:
            val = int(parameter)
            if not 0 <= val <= 100:
                return f"Brightness must be 0-100, got {val}"
        except (ValueError, TypeError):
            return f"Brightness must be numeric, got '{parameter}'"

    if command == "setPosition":
        try:
            # Format: "index,mode,position" or just position
            if "," in str(parameter):
                parts = str(parameter).split(",")
                pos = int(parts[-1])
            else:
                pos = int(parameter)
            if not 0 <= pos <= 100:
                return f"Position must be 0-100, got {pos}"
        except (ValueError, TypeError):
            return f"Invalid position parameter: '{parameter}'"

    if command == "setColorTemperature":
        try:
            val = int(parameter)
            if not 2700 <= val <= 6500:
                return f"Color temperature must be 2700-6500, got {val}"
        except (ValueError, TypeError):
            return f"Color temperature must be numeric, got '{parameter}'"

    return None


# --- REST API ---


class CommandRequest(BaseModel):
    command: str
    parameter: str = "default"
    command_type: str = "command"


@app.get("/health")
async def health():
    return {"status": "ok", "connected": sb_client.connected if sb_client else False}


@app.get("/api/devices")
async def get_devices():
    """List all SwitchBot devices with current cached info."""
    if not sb_client:
        raise HTTPException(503, "SwitchBot client not initialized")

    physical, infrared = await sb_client.get_devices()
    devices = []
    for d in physical:
        device_id = d["deviceId"]
        device_type = d.get("deviceType", "")
        domain = sb_client.get_domain(device_type)
        zone = device_mapper.get_zone(device_id)
        devices.append(
            {
                "device_id": device_id,
                "device_name": d.get("deviceName", ""),
                "device_type": device_type,
                "domain": domain,
                "zone": zone,
                "hems_entity_id": f"switchbot.{device_id}",
                "hub_device_id": d.get("hubDeviceId", ""),
                "enable_cloud_service": d.get("enableCloudService", False),
            }
        )

    ir_devices = []
    for d in infrared:
        ir_devices.append(
            {
                "device_id": d["deviceId"],
                "device_name": d.get("deviceName", ""),
                "remote_type": d.get("remoteType", ""),
                "hub_device_id": d.get("hubDeviceId", ""),
            }
        )

    return {"devices": devices, "ir_devices": ir_devices}


@app.get("/api/devices/{device_id}/status")
async def get_device_status(device_id: str):
    """Fetch current status of a single device."""
    if not sb_client:
        raise HTTPException(503, "SwitchBot client not initialized")

    status = await sb_client.get_device_status(device_id)
    if status is None:
        raise HTTPException(404, f"Device {device_id} not found or offline")

    parsed = sb_client.parse_status(device_id, status)
    return {"raw": status, "parsed": parsed}


@app.post("/api/devices/{device_id}/command")
async def send_command(device_id: str, req: CommandRequest):
    """Send command to a SwitchBot device."""
    if not sb_client:
        raise HTTPException(503, "SwitchBot client not initialized")

    # Validate command
    err = _validate_command(device_id, req.command, req.parameter)
    if err:
        raise HTTPException(400, f"Invalid command: {err}")

    result = await sb_client.send_command(
        device_id,
        req.command,
        req.parameter,
        req.command_type,
    )
    if result is not None:
        # Refresh status after command
        status = await sb_client.get_device_status(device_id)
        if status:
            parsed = sb_client.parse_status(device_id, status)
            _publish_device_state(device_id, parsed)
        return {"success": True, "result": result}

    raise HTTPException(502, f"SwitchBot command failed: {req.command}")


@app.post("/api/webhook")
async def webhook_receiver(request: Request):
    """Receive SwitchBot webhook push events."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event_type = body.get("eventType", "")
    context = body.get("context", {})

    if event_type == "changeReport":
        device_id = context.get("deviceMac", "") or context.get("deviceId", "")
        device_type = context.get("deviceType", "")

        if device_id:
            # Parse webhook context as status
            parsed = sb_client.parse_status(device_id, context)
            _publish_device_state(device_id, parsed)
            logger.debug(f"Webhook: {device_type} {device_id} → {parsed.get('state')}")

    return {"message": "ok"}
