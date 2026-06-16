"""
HEMS Weather Bridge — FastAPI service that polls weather APIs and publishes to MQTT.
Supports JMA (気象庁, free) and OpenWeatherMap providers.
"""

from contextlib import asynccontextmanager

from data_poller import DataPoller
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from hems_common import MqttPublisher, bridge_lifespan, verify_internal_token
from loguru import logger
from weather_client import JMAClient, OWMClient

import config

# Module-level state
weather_client: JMAClient | OWMClient | None = None
mqtt_pub: MqttPublisher | None = None
poller: DataPoller | None = None

# Routers: /health stays public for Docker healthchecks; all other REST routes
# require the internal bearer token when HEMS_INTERNAL_TOKEN is configured.
public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(verify_internal_token)])


@asynccontextmanager
async def lifespan(app: FastAPI):
    global weather_client, mqtt_pub, poller

    # MQTT — weather: no retain, debug errors, raise on connect failure, no connection tracking
    mqtt_pub = MqttPublisher(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_USER,
        config.MQTT_PASS,
        default_retain=False,
        default_qos=0,
        ensure_ascii=False,
        error_level="debug",
        raise_on_connect_error=True,
        track_connection=False,
        auto_reconnect=False,
    )

    # Weather client + poller are set up before task_factories are called
    async def _startup():
        global weather_client, poller
        if config.WEATHER_PROVIDER == "openweathermap":
            if not config.OWM_API_KEY:
                logger.error("OWM_API_KEY not configured — bridge will not poll")
            weather_client = OWMClient(
                config.OWM_API_KEY,
                config.OWM_LAT,
                config.OWM_LON,
                config.OWM_UNITS,
                config.OWM_LANG,
            )
        else:
            logger.info(f"Using JMA provider: area={config.JMA_AREA_CODE}, detail={config.JMA_DETAIL_CODE}")
            weather_client = JMAClient(config.JMA_AREA_CODE, config.JMA_DETAIL_CODE)

        await weather_client.start()
        poller = DataPoller(weather_client, mqtt_pub)

    async def _shutdown():
        if weather_client is not None:
            await weather_client.stop()

    # Build task factories conditionally (skip polling if OWM key absent)
    can_poll = not (config.WEATHER_PROVIDER == "openweathermap" and not config.OWM_API_KEY)

    def _poll_current():
        return poller.poll_current()

    def _poll_forecast():
        return poller.poll_forecast()

    task_factories = [_poll_current, _poll_forecast] if can_poll else []
    if can_poll:
        logger.info(f"Polling started: current={config.CURRENT_INTERVAL}s, forecast={config.FORECAST_INTERVAL}s")

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=task_factories,
        on_shutdown=_shutdown,
    ):
        logger.info("Weather Bridge started")
        yield
    logger.info("Weather Bridge stopped")


app = FastAPI(title="HEMS Weather Bridge", lifespan=lifespan)


@public_router.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": config.WEATHER_PROVIDER,
        "configured": True,
    }


@private_router.get("/api/weather/current")
async def get_current():
    if not poller:
        raise HTTPException(503, "Service not ready")
    if not poller.current_data:
        raise HTTPException(404, "No weather data yet")
    return poller.current_data


@private_router.get("/api/weather/forecast")
async def get_forecast():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "entries": poller.forecast_data or [],
    }


@private_router.get("/api/weather/alerts")
async def get_alerts():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "alerts": poller.alerts_data or [],
    }


@private_router.get("/api/weather/status")
async def get_status():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return poller.get_status()


app.include_router(public_router)
app.include_router(private_router)
