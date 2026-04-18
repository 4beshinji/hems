"""
OpenClaw Bridge — connects OpenClaw desktop agent to HEMS via MQTT + REST.
Polls PC metrics, publishes to hems/pc/* topics, exposes REST API for brain tools.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from config import (
    BROWSER_CHECKERS_JSON,
    GITHUB_ENABLED,
    GITHUB_INTERVAL,
    GITHUB_TOKEN,
    GMAIL_APP_PASSWORD,
    GMAIL_EMAIL,
    GMAIL_ENABLED,
    GMAIL_INTERVAL,
    LOG_LEVEL,
    METRICS_INTERVAL,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    OPENCLAW_GATEWAY_TOKEN,
    OPENCLAW_GATEWAY_URL,
    PROCESS_INTERVAL,
)
from metric_collector import MetricCollector
from mqtt_publisher import MQTTPublisher
from openclaw_client import OpenClawClient
from service_checker import (
    BrowserChecker,
    GitHubChecker,
    GmailChecker,
    ServiceCheckerManager,
)

logger.configure(handlers=[{"sink": "ext://sys.stderr", "level": LOG_LEVEL}])

# Shared state
oc_client = OpenClawClient(OPENCLAW_GATEWAY_URL, OPENCLAW_GATEWAY_TOKEN)
mqtt_pub = MQTTPublisher(MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
collector = MetricCollector(oc_client, mqtt_pub, METRICS_INTERVAL, PROCESS_INTERVAL)
service_checker = ServiceCheckerManager(mqtt_pub)
start_time = time.time()


def _register_service_checkers():
    """Register enabled service checkers from environment variables."""
    if GMAIL_ENABLED and GMAIL_EMAIL and GMAIL_APP_PASSWORD:
        service_checker.register(GmailChecker(GMAIL_EMAIL, GMAIL_APP_PASSWORD, GMAIL_INTERVAL))

    if GITHUB_ENABLED and GITHUB_TOKEN:
        service_checker.register(GitHubChecker(GITHUB_TOKEN, GITHUB_INTERVAL))

    # Browser-based checkers from JSON config
    try:
        import json as _json

        browser_configs = _json.loads(BROWSER_CHECKERS_JSON)
        if browser_configs:
            browser_lock = asyncio.Lock()
            for cfg in browser_configs:
                service_checker.register(
                    BrowserChecker(
                        name=cfg["name"],
                        url=cfg["url"],
                        js_script=cfg["js_script"],
                        oc_client=oc_client,
                        interval=cfg.get("interval", 300),
                        browser_lock=browser_lock,
                    )
                )
    except Exception as e:
        logger.warning(f"Failed to parse HEMS_BROWSER_CHECKERS: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect MQTT
    mqtt_pub.connect()

    # Register and start service checkers
    _register_service_checkers()

    # Start OpenClaw reconnect loop + metric collectors + service checkers
    tasks = [
        asyncio.create_task(oc_client.reconnect_loop()),
        asyncio.create_task(collector.run_metrics_loop()),
        asyncio.create_task(collector.run_process_loop()),
        asyncio.create_task(_bridge_status_loop()),
        asyncio.create_task(service_checker.run()),
    ]
    logger.info(f"OpenClaw Bridge started (gateway={OPENCLAW_GATEWAY_URL})")
    yield
    for t in tasks:
        t.cancel()
    await oc_client.disconnect()
    mqtt_pub.disconnect()


app = FastAPI(title="OpenClaw Bridge", lifespan=lifespan)


async def _bridge_status_loop():
    """Publish bridge status to MQTT every 30s."""
    while True:
        mqtt_pub.publish(
            "hems/pc/bridge/status",
            {
                "connected": oc_client.connected,
                "uptime_s": round(time.time() - start_time),
            },
        )
        await asyncio.sleep(30)


# --- Request models ---


class CommandRequest(BaseModel):
    command: str
    cwd: str | None = None
    timeout: float = 30


class NotifyRequest(BaseModel):
    title: str
    body: str
    priority: str = "active"


class NavigateRequest(BaseModel):
    url: str


class EvalRequest(BaseModel):
    javascript: str


class KillRequest(BaseModel):
    pid: int


# --- REST endpoints ---


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "openclaw_connected": oc_client.connected,
        "uptime_s": round(time.time() - start_time),
    }


@app.get("/api/services/status")
async def get_services_status():
    """Return cached service checker statuses."""
    return service_checker.get_status()


@app.get("/api/pc/status")
async def get_pc_status():
    """Return cached PC metrics."""
    status = collector.get_status()
    status["bridge_connected"] = oc_client.connected
    return status


@app.post("/api/pc/command")
async def run_command(req: CommandRequest):
    """Execute a shell command on the host via OpenClaw."""
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    try:
        result = await oc_client.system_run(req.command, cwd=req.cwd, timeout=req.timeout)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/notify")
async def send_notification(req: NotifyRequest):
    """Send a desktop notification via OpenClaw."""
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    try:
        result = await oc_client.system_notify(req.title, req.body, req.priority)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/browser/navigate")
async def browser_navigate(req: NavigateRequest):
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    # SSRF prevention: only allow http/https schemes
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL scheme: only http:// and https:// are allowed")
    try:
        result = await oc_client.canvas_navigate(req.url)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/browser/eval")
async def browser_eval(req: EvalRequest):
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    try:
        result = await oc_client.canvas_eval(req.javascript)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/browser/get_url")
async def browser_get_url():
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    try:
        result = await oc_client.canvas_get_url()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/browser/get_title")
async def browser_get_title():
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    try:
        result = await oc_client.canvas_get_title()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.post("/api/pc/process/kill")
async def kill_process(req: KillRequest):
    """Kill a process by PID."""
    if not oc_client.connected:
        raise HTTPException(503, "OpenClaw Gateway not connected")
    # Validate PID range to prevent abuse (PID must be positive, non-system)
    if req.pid < 2 or req.pid > 4194304:
        raise HTTPException(400, "Invalid PID: must be between 2 and 4194304")
    try:
        # Use str(int()) to guarantee no shell metacharacters can be injected
        result = await oc_client.system_run(f"kill {int(req.pid)}", timeout=5)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise HTTPException(500, "Internal error")


@app.get("/api/pc/processes")
async def get_processes():
    """Return cached top processes."""
    return {"processes": collector.last_processes}
