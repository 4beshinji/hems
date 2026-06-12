"""Unit tests for hems_common.lifespan.bridge_lifespan and
hems_common.status.publish_bridge_status."""

import asyncio
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest
from hems_common.lifespan import bridge_lifespan
from hems_common.mqtt import MqttPublisher
from hems_common.status import publish_bridge_status


def _mock_pub():
    pub = MqttPublisher("localhost", 1883)
    pub.client = MagicMock()
    pub.client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
    pub._connected = True
    return pub


@pytest.mark.asyncio
async def test_bridge_lifespan_order_and_tasks():
    pub = _mock_pub()
    events = []

    async def startup():
        events.append("startup")

    async def shutdown():
        events.append("shutdown")

    started = asyncio.Event()

    async def loop():
        events.append("task")
        started.set()
        await asyncio.sleep(3600)

    async with bridge_lifespan(None, mqtt=pub, on_startup=startup, task_factories=[loop], on_shutdown=shutdown):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert events[:2] == ["startup", "task"]

    assert events[-1] == "shutdown"
    pub.client.connect.assert_called_once()
    pub.client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bridge_lifespan_disconnects_even_if_shutdown_raises():
    pub = _mock_pub()

    async def bad_shutdown():
        raise RuntimeError("boom")

    async with bridge_lifespan(None, mqtt=pub, on_shutdown=bad_shutdown):
        pass

    pub.client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bridge_lifespan_no_hooks():
    pub = _mock_pub()
    async with bridge_lifespan(None, mqtt=pub):
        pass
    pub.client.connect.assert_called_once()
    pub.client.disconnect.assert_called_once()


def test_publish_bridge_status_topic_and_retain():
    pub = _mock_pub()
    assert publish_bridge_status(pub, "obsidian") is True
    args, kwargs = pub.client.publish.call_args
    assert args[0] == "hems/obsidian/bridge/status"
    assert kwargs["retain"] is True


def test_publish_bridge_status_extra_fields():
    import json

    pub = _mock_pub()
    publish_bridge_status(pub, "ha", connected=False, last_error="timeout")
    payload = json.loads(pub.client.publish.call_args.args[1])
    assert payload == {"connected": False, "last_error": "timeout"}
