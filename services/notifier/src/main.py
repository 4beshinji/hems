"""
HEMS Lite Notifier — multi-platform notification gateway.
Receives alerts from Sentinel via REST API and dispatches to configured providers.
"""
import os
import sys
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

from providers import (
    Notification,
    LINENotifyProvider,
    DiscordWebhookProvider,
    SlackWebhookProvider,
    NtfyProvider,
)

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(title="HEMS Lite Notifier", version="0.1.0")

# Initialize all providers, filter to configured ones
ALL_PROVIDERS = [
    LINENotifyProvider(),
    DiscordWebhookProvider(),
    SlackWebhookProvider(),
    NtfyProvider(),
]
ACTIVE_PROVIDERS = [p for p in ALL_PROVIDERS if p.is_configured()]


class NotifyRequest(BaseModel):
    level: str        # CRITICAL | HIGH | NORMAL | INFO
    title: str
    body: str
    source: str = ""
    zone: str = ""
    site_id: str = ""
    site_name: str = ""
    timestamp: float = 0.0


@app.on_event("startup")
async def startup():
    if not ACTIVE_PROVIDERS:
        logger.warning("No notification providers configured! Alerts will be logged only.")
    else:
        names = [p.name for p in ACTIVE_PROVIDERS]
        logger.info(f"Active notification providers: {names}")


@app.post("/api/notify")
async def notify(req: NotifyRequest):
    """Receive alert from Sentinel and dispatch to all active providers."""
    notification = Notification(
        level=req.level,
        title=req.title,
        body=req.body,
        source=req.source,
        zone=req.zone,
        site_id=req.site_id,
        site_name=req.site_name,
        timestamp=req.timestamp or time.time(),
    )

    logger.info(f"[{req.level}] {req.title} — dispatching to {len(ACTIVE_PROVIDERS)} providers")

    results = {}
    for provider in ACTIVE_PROVIDERS:
        ok = await provider.send(notification)
        results[provider.name] = "ok" if ok else "failed"
        if not ok:
            logger.error(f"Provider {provider.name} failed for: {req.title}")

    return {"status": "ok", "dispatched": results}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "providers": [p.name for p in ACTIVE_PROVIDERS],
        "all_providers": [p.name for p in ALL_PROVIDERS],
    }
