"""
Brain control — power mode + batch jobs + Ollama model list.
"""

import json
import os

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/brain", tags=["brain"])

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# In-memory store: brain pushes snapshots every cognitive cycle (~30s)
_power_mode_store: dict = {
    "mode": "normal",
    "reason": "",
    "entered_at": 0.0,
    "cycle_interval_sec": 30,
    "llm_cooldown_remaining_sec": 0,
    "manual_override_remaining_sec": 0,
}


def _mqtt_publish(topic: str, payload: dict) -> None:
    import paho.mqtt.publish as mqtt_pub

    auth = {"username": MQTT_USER, "password": MQTT_PASS} if MQTT_USER else None
    mqtt_pub.single(
        topic,
        json.dumps(payload, ensure_ascii=False),
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        auth=auth,
    )


# ── Power mode ────────────────────────────────────────────────────────────────


@router.get("/power-mode")
async def get_power_mode():
    """Get current brain power mode status."""
    return _power_mode_store


class PowerModeRequest(BaseModel):
    mode: str  # "normal" | "sleep" | "away"


@router.post("/power-mode")
async def set_power_mode(req: PowerModeRequest):
    """Set brain power mode (publishes MQTT command to brain)."""
    if req.mode not in ("normal", "sleep", "away"):
        raise HTTPException(status_code=400, detail="mode must be normal | sleep | away")
    _mqtt_publish("hems/brain/set-power-mode", {"mode": req.mode})
    # Optimistic update — brain will confirm via /snapshot on next cycle
    _power_mode_store["mode"] = req.mode
    return {"ok": True, "mode": req.mode}


@router.post("/snapshot")
async def receive_brain_snapshot(data: dict):
    """Receive power mode status snapshot from brain (called every cognitive cycle)."""
    _power_mode_store.clear()
    _power_mode_store.update(data)
    return {"updated": True}


# ── Ollama models ─────────────────────────────────────────────────────────────


@router.get("/ollama/models")
async def list_ollama_models():
    """List available Ollama models. Returns empty list when Ollama is unreachable."""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{OLLAMA_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 200:
                return {"models": []}
            data = await resp.json()
            models = [
                {
                    "name": m.get("name", ""),
                    "size_gb": round(m.get("size", 0) / 1_073_741_824, 1),
                    "family": m.get("details", {}).get("family", ""),
                }
                for m in data.get("models", [])
                if m.get("name")
            ]
            return {"models": models}
    except Exception:
        return {"models": []}


# ── Batch run ─────────────────────────────────────────────────────────────────

_VALID_BATCH_TASKS = {"news_briefing", "morning_greeting", "weather_report", "task_planning"}

BATCH_TASK_LABELS = {
    "news_briefing": "ニュース要約",
    "morning_greeting": "朝のあいさつ",
    "weather_report": "天気レポート",
    "task_planning": "タスク詳細設計",
}


class BatchRequest(BaseModel):
    tasks: list[str]
    model: str | None = None


@router.post("/batch")
async def run_batch(req: BatchRequest):
    """Trigger batch task execution on the brain with an optional model override."""
    tasks = [t for t in req.tasks if t in _VALID_BATCH_TASKS]
    if not tasks:
        raise HTTPException(status_code=400, detail="No valid tasks specified")
    _mqtt_publish("hems/brain/batch-run", {"tasks": tasks, "model": req.model})
    labels = [BATCH_TASK_LABELS.get(t, t) for t in tasks]
    return {"ok": True, "tasks": tasks, "labels": labels, "model": req.model}
