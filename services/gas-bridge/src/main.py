"""
HEMS GAS Bridge — FastAPI service that polls GAS Web App and publishes to MQTT.
"""

from contextlib import asynccontextmanager

from data_poller import DataPoller
from fastapi import FastAPI, HTTPException
from gas_client import GASClient
from hems_common import MqttPublisher, bridge_lifespan
from loguru import logger

import config

# Module-level state
gas_client: GASClient | None = None
mqtt_pub: MqttPublisher | None = None
poller: DataPoller | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gas_client, mqtt_pub, poller

    if not config.GAS_WEBAPP_URL:
        logger.error("GAS_WEBAPP_URL not configured — bridge will not poll")
    else:
        logger.info(f"GAS Web App URL: {config.GAS_WEBAPP_URL[:60]}...")

    # MQTT — gas: no retain, debug errors, raise on connect failure, no connection tracking
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

    async def _startup():
        global gas_client, poller
        gas_client = GASClient(config.GAS_WEBAPP_URL, config.GAS_API_KEY)
        await gas_client.start()
        poller = DataPoller(gas_client, mqtt_pub)

    async def _shutdown():
        if gas_client is not None:
            await gas_client.stop()

    task_factories = []
    if config.GAS_WEBAPP_URL:
        task_factories = [
            lambda: poller.poll_calendar(),
            lambda: poller.poll_tasks(),
            lambda: poller.poll_gmail(),
            lambda: poller.poll_sheets(),
            lambda: poller.poll_drive(),
        ]
        logger.info(
            f"Polling started: calendar={config.CALENDAR_INTERVAL}s, "
            f"tasks={config.TASKS_INTERVAL}s, gmail={config.GMAIL_INTERVAL}s, "
            f"sheets={config.SHEETS_INTERVAL}s, drive={config.DRIVE_INTERVAL}s"
        )

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=task_factories,
        on_shutdown=_shutdown,
    ):
        logger.info("GAS Bridge started")
        yield
    logger.info("GAS Bridge stopped")


app = FastAPI(title="HEMS GAS Bridge", lifespan=lifespan)


@app.get("/health")
async def health():
    if gas_client:
        health_data = await gas_client.fetch("health")
        return {
            "status": "ok" if health_data else "gas_unreachable",
            "gas_webapp_configured": bool(config.GAS_WEBAPP_URL),
            "gas_health": health_data,
        }
    return {"status": "starting", "gas_webapp_configured": bool(config.GAS_WEBAPP_URL)}


@app.get("/api/gas/calendar")
async def get_calendar():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "upcoming": poller.calendar_data,
        "free_slots": poller.free_slots_data,
    }


@app.get("/api/gas/tasks")
async def get_tasks():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "all": poller.tasks_data,
        "due_today": poller.tasks_due_data,
    }


@app.get("/api/gas/gmail")
async def get_gmail():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return {
        "summary": poller.gmail_data,
        "recent": poller.gmail_recent_data,
    }


@app.get("/api/gas/sheets/{name}")
async def get_sheet(name: str):
    if not poller:
        raise HTTPException(503, "Service not ready")
    data = poller.sheets_data.get(name)
    if data is None:
        raise HTTPException(404, f"Sheet '{name}' not found")
    return data


@app.get("/api/gas/drive")
async def get_drive():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return poller.drive_data or {}


@app.get("/api/gas/status")
async def get_status():
    if not poller:
        raise HTTPException(503, "Service not ready")
    return poller.get_status()
