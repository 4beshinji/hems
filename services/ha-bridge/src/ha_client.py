"""
Home Assistant REST + WebSocket client.
"""
import asyncio
import aiohttp
from loguru import logger


class HAClient:
    """Client for Home Assistant REST API and WebSocket event stream."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_id: int = 0
        self.connected: bool = False

    async def start(self, session: aiohttp.ClientSession):
        self._session = session

    async def stop(self):
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self.connected = False

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    # --- REST API ---

    async def get_states(self) -> list[dict]:
        """Fetch all entity states from HA."""
        try:
            async with self._session.get(
                f"{self.url}/api/states",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    self.connected = True
                    return await resp.json()
                logger.warning(f"HA get_states failed: {resp.status}")
        except Exception as e:
            logger.warning(f"HA get_states error: {e}")
            self.connected = False
        return []

    async def get_state(self, entity_id: str) -> dict | None:
        """Fetch single entity state."""
        try:
            async with self._session.get(
                f"{self.url}/api/states/{entity_id}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"HA get_state({entity_id}) failed: {resp.status}")
        except Exception as e:
            logger.warning(f"HA get_state error: {e}")
        return None

    async def call_service(self, domain: str, service: str,
                           entity_id: str = "", data: dict | None = None) -> bool:
        """Call a Home Assistant service (e.g. light/turn_on)."""
        payload = dict(data or {})
        if entity_id:
            payload["entity_id"] = entity_id
        try:
            async with self._session.post(
                f"{self.url}/api/services/{domain}/{service}",
                headers=self._headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"HA service call: {domain}/{service} entity={entity_id}")
                    return True
                logger.warning(f"HA service call failed: {resp.status}")
        except Exception as e:
            logger.error(f"HA service call error: {e}")
        return False

    # --- WebSocket ---

    async def connect_ws(self) -> bool:
        """Establish WebSocket connection and authenticate."""
        try:
            self._ws = await self._session.ws_connect(
                f"{self.url}/api/websocket",
                timeout=aiohttp.ClientTimeout(total=10),
            )
            # HA sends auth_required first
            msg = await self._ws.receive_json(timeout=10)
            if msg.get("type") != "auth_required":
                logger.warning(f"Unexpected WS message: {msg}")
                return False

            await self._ws.send_json({"type": "auth", "access_token": self.token})
            msg = await self._ws.receive_json(timeout=10)
            if msg.get("type") != "auth_ok":
                logger.error(f"HA WS auth failed: {msg}")
                return False

            self.connected = True
            logger.info("HA WebSocket connected and authenticated")
            return True
        except Exception as e:
            logger.error(f"HA WebSocket connect error: {e}")
            self.connected = False
            return False

    async def subscribe_events(self) -> bool:
        """Subscribe to state_changed events via WebSocket."""
        if not self._ws or self._ws.closed:
            return False
        self._ws_id += 1
        await self._ws.send_json({
            "id": self._ws_id,
            "type": "subscribe_events",
            "event_type": "state_changed",
        })
        msg = await self._ws.receive_json(timeout=10)
        return msg.get("success", False)

    async def ws_events(self):
        """Async generator yielding state_changed event data."""
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()
                    if data.get("type") == "event":
                        event = data.get("event", {})
                        if event.get("event_type") == "state_changed":
                            yield event.get("data", {})
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except Exception as e:
            logger.warning(f"HA WS event stream error: {e}")
        finally:
            self.connected = False

    async def reconnect_loop(self, on_state_changed, poll_fallback, interval: int = 5):
        """Maintain WebSocket connection with polling fallback.

        Args:
            on_state_changed: async callback(entity_id, new_state_dict)
            poll_fallback: async callback() for full state poll
            interval: seconds between reconnect attempts
        """
        while True:
            try:
                if await self.connect_ws():
                    if await self.subscribe_events():
                        logger.info("HA WS subscribed to state_changed events")
                        async for event_data in self.ws_events():
                            new_state = event_data.get("new_state", {})
                            entity_id = new_state.get("entity_id", "")
                            if entity_id:
                                await on_state_changed(entity_id, new_state)
                    else:
                        logger.warning("HA WS subscribe failed, falling back to polling")
                        await poll_fallback()
                else:
                    logger.warning("HA WS connect failed, falling back to polling")
                    await poll_fallback()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"HA reconnect loop error: {e}")
                self.connected = False

            logger.info(f"HA WS disconnected, reconnecting in {interval}s...")
            await asyncio.sleep(interval)
