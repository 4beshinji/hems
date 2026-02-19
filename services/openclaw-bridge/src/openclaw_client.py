"""
WebSocket client for OpenClaw Gateway.
Persistent connection with auto-reconnect and request/response pairing.
"""
import asyncio
import json
import uuid
from loguru import logger

try:
    import websockets
except ImportError:
    websockets = None


class OpenClawClient:
    """WebSocket RPC client for OpenClaw Gateway."""

    def __init__(self, gateway_url: str, token: str = ""):
        self.gateway_url = gateway_url
        self.token = token
        self._ws = None
        self._pending: dict[str, asyncio.Future] = {}
        self._connected = False
        self._reader_task: asyncio.Task | None = None
        self._reconnect_delay = 1.0

    @property
    def connected(self) -> bool:
        return self._connected and self._ws is not None

    async def connect(self):
        """Establish WebSocket connection to OpenClaw Gateway."""
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            self._ws = await websockets.connect(
                self.gateway_url,
                additional_headers=headers if headers else None,
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            self._reconnect_delay = 1.0
            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info(f"Connected to OpenClaw Gateway: {self.gateway_url}")
        except Exception as e:
            self._connected = False
            logger.warning(f"OpenClaw connection failed: {e}")
            raise

    async def disconnect(self):
        """Close the WebSocket connection."""
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        # Cancel all pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    async def reconnect_loop(self):
        """Background task: reconnect on disconnect."""
        while True:
            if not self._connected:
                try:
                    await self.connect()
                except Exception:
                    logger.debug(f"Reconnect in {self._reconnect_delay:.0f}s...")
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 60)
                    continue
            await asyncio.sleep(5)

    async def _read_loop(self):
        """Read responses from WebSocket and resolve pending futures."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                req_id = msg.get("id")
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception as e:
            logger.warning(f"OpenClaw WS read error: {e}")
        finally:
            self._connected = False

    async def _rpc(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        """Send an RPC request and wait for response."""
        if not self.connected:
            raise ConnectionError("Not connected to OpenClaw Gateway")

        req_id = str(uuid.uuid4())
        request = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            request["params"] = params

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        try:
            await self._ws.send(json.dumps(request))
            result = await asyncio.wait_for(fut, timeout=timeout)
            if "error" in result:
                raise RuntimeError(f"RPC error: {result['error']}")
            return result.get("result", {})
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"RPC timeout: {method}")

    async def system_run(self, command: str, cwd: str | None = None, timeout: float = 30) -> dict:
        """Execute a shell command on the host via OpenClaw."""
        params = {"command": command}
        if cwd:
            params["cwd"] = cwd
        return await self._rpc("system.run", params, timeout=timeout)

    async def system_notify(self, title: str, body: str, priority: str = "active") -> dict:
        """Send a desktop notification via OpenClaw."""
        return await self._rpc("system.notify", {
            "title": title, "body": body, "priority": priority,
        })

    async def canvas_navigate(self, url: str) -> dict:
        """Navigate the browser to a URL."""
        return await self._rpc("canvas.navigate", {"url": url})

    async def canvas_eval(self, javascript: str) -> dict:
        """Evaluate JavaScript in the browser."""
        return await self._rpc("canvas.eval", {"javascript": javascript})

    async def canvas_get_url(self) -> dict:
        """Get the current browser URL."""
        return await self._rpc("canvas.getUrl")

    async def canvas_get_title(self) -> dict:
        """Get the current browser tab title."""
        return await self._rpc("canvas.getTitle")
