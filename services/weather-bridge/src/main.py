"""
HEMS Weather Bridge — FastAPI service that polls weather APIs and publishes to MQTT.
Supports JMA (気象庁, free) and OpenWeatherMap providers.
"""

import asyncio
from contextlib import asynccontextmanager

from data_poller import DataPoller
from fastapi import FastAPI, HTTPException
from loguru import logger
from mqtt_publisher import MQTTPublisher
from weather_client import JMAClient, OWMClient

import config

# Module-level state
weather_client: JMAClient | OWMClient | None = None
mqtt_pub: MQTTPublisher | None = None
poller: DataPoller | None = None
_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global weather_client, mqtt_pub, poller

    # MQTT
    mqtt_pub = MQTTPublisher(
        config.MQTT_BROKER,
        config.MQTT_PORT,
        config.MQTT_USER,
        config.MQTT_PASS,
    )
    mqtt_pub.connect()

    # Weather client
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

    # Data poller
    poller = DataPoller(weather_client, mqtt_pub)

    # Start polling tasks
    can_poll = True
    if config.WEATHER_PROVIDER == "openweathermap" and not config.OWM_API_KEY:
        can_poll = False

    if can_poll:
        _tasks.append(asyncio.create_task(poller.poll_current()))
        _tasks.append(asyncio.create_task(poller.poll_forecast()))
        logger.info(f"Polling started: current={config.CURRENT_INTERVAL}s, forecast={config.FORECAST_INTERVAL}s")

    logger.info("Weather Bridge started")
    yield

    # Shutdown
    for t in _tasks:
        t.cancel()
    await weather_client.stop()
    mqtt_pub.disconnect()
    logger.info("Weather Bridge stopped")


app = FastAPI(title="HEMS Weather Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": config.WEATHER_PROVIDER,
        "configured": True,
    }


@app.get("/api/weather/current")
async def get_current():
    if not poller:
        raise HTTPException(503, "Service not ready")
    if not poller.current_data:
        raise HTTPException(404, "No weather data yet")
    return poller.current_data


@app.get("/api/weather/forecast")
async def get_forecast():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "entries": poller.forecast_data or [],
    }


@app.get("/api/weather/alerts")
async def get_alerts():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "alerts": poller.alerts_data or [],
    }


@app.get("/api/weather/status")
async def get_status():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return poller.get_status()
