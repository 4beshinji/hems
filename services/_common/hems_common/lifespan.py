"""Shared FastAPI lifespan helper for HEMS bridges.

All bridges share the same skeleton: connect MQTT, run some setup, spawn a set
of polling/background tasks, then on shutdown cancel the tasks, run teardown,
and disconnect MQTT. ``bridge_lifespan`` factors that out.

Bridge-specific resources (aiohttp sessions, watchdog watchers, send queues,
client.start()/stop()) are closed over in the ``on_startup`` / ``on_shutdown``
hooks. Each background loop is supplied as a *factory* — a zero-arg callable
returning a coroutine — so that ha's ``reconnect_loop`` and biometric's flush
loop both fit the same shape.

Using this helper is optional: a bridge with awkward needs can keep its own
lifespan and still use :class:`~hems_common.mqtt.MqttPublisher`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from loguru import logger

from hems_common.mqtt import MqttPublisher


@asynccontextmanager
async def bridge_lifespan(
    app,
    *,
    mqtt: MqttPublisher,
    on_startup: Callable[[], Awaitable[None]] | None = None,
    task_factories: list[Callable[[], Awaitable]] | tuple[Callable[[], Awaitable], ...] = (),
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
):
    """Common bridge lifespan.

    Order: ``mqtt.connect()`` -> ``on_startup()`` -> spawn ``task_factories``
    -> yield -> cancel tasks -> ``on_shutdown()`` -> ``mqtt.disconnect()``.

    Teardown is best-effort: a failing ``on_shutdown`` is logged but never
    prevents ``mqtt.disconnect()`` from running.
    """
    mqtt.connect()
    if on_startup is not None:
        try:
            await on_startup()
        except Exception:
            mqtt.disconnect()
            raise

    tasks = [asyncio.create_task(factory()) for factory in task_factories]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if on_shutdown is not None:
            try:
                await on_shutdown()
            except Exception as e:
                logger.error(f"bridge_lifespan on_shutdown error: {e}")
        mqtt.disconnect()
