"""
Tests for openclaw-bridge service components.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOpenClawClient:
    """Test the WebSocket RPC client."""

    def _make_client(self):
        from openclaw_client import OpenClawClient
        return OpenClawClient("ws://localhost:18789")

    def test_initial_state(self):
        client = self._make_client()
        assert client.connected is False
        assert client.gateway_url == "ws://localhost:18789"

    def test_connected_property(self):
        client = self._make_client()
        assert client.connected is False
        client._connected = True
        client._ws = MagicMock()
        assert client.connected is True

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        client = self._make_client()
        client._connected = True
        client._ws = AsyncMock()
        client._reader_task = MagicMock()
        client._reader_task.cancel = MagicMock()

        future = asyncio.get_event_loop().create_future()
        client._pending["test-id"] = future

        await client.disconnect()
        assert client.connected is False
        assert client._ws is None
        assert len(client._pending) == 0

    @pytest.mark.asyncio
    async def test_rpc_raises_when_disconnected(self):
        client = self._make_client()
        with pytest.raises(ConnectionError, match="Not connected"):
            await client._rpc("test.method")


class TestMQTTPublisher:
    """Test the MQTT publisher."""

    def test_publish_calls_client(self):
        from mqtt_publisher import MQTTPublisher
        pub = MQTTPublisher("localhost", 1883)
        pub.client = MagicMock()

        pub.publish("hems/pc/metrics/cpu", {"usage_percent": 42})
        pub.client.publish.assert_called_once()
        call_args = pub.client.publish.call_args
        assert call_args[0][0] == "hems/pc/metrics/cpu"
        payload = json.loads(call_args[0][1])
        assert payload["usage_percent"] == 42

    def test_publish_handles_error(self):
        from mqtt_publisher import MQTTPublisher
        pub = MQTTPublisher("localhost", 1883)
        pub.client = MagicMock()
        pub.client.publish.side_effect = Exception("MQTT error")

        # Should not raise
        pub.publish("hems/pc/test", {"key": "value"})


class TestMetricCollector:
    """Test the metric collector."""

    def _make_collector(self):
        from metric_collector import MetricCollector
        oc = AsyncMock()
        mqtt = MagicMock()
        return MetricCollector(oc, mqtt, metrics_interval=10, process_interval=30)

    def test_initial_state(self):
        collector = self._make_collector()
        assert collector.last_metrics == {}
        assert collector.last_processes == []

    def test_get_status_empty(self):
        collector = self._make_collector()
        status = collector.get_status()
        assert status == {"top_processes": []}

    def test_get_status_with_data(self):
        collector = self._make_collector()
        collector.last_metrics = {
            "cpu": {"usage_percent": 42},
            "timestamp": 12345,
        }
        collector.last_processes = [{"pid": 1, "name": "init"}]
        status = collector.get_status()
        assert status["cpu"]["usage_percent"] == 42
        assert status["top_processes"][0]["name"] == "init"

    def test_threshold_edge_detection_cpu(self):
        collector = self._make_collector()

        # Below threshold — no event
        collector._check_events({"usage_percent": 50}, {}, {}, {})
        collector.mqtt.publish.assert_not_called()

        # Cross threshold — event
        collector._check_events({"usage_percent": 95}, {}, {}, {})
        collector.mqtt.publish.assert_called_once()
        topic = collector.mqtt.publish.call_args[0][0]
        assert topic == "hems/pc/events/cpu_high"

    def test_threshold_no_duplicate_events(self):
        collector = self._make_collector()

        # First crossing
        collector._check_events({"usage_percent": 95}, {}, {}, {})
        assert collector.mqtt.publish.call_count == 1

        # Still high — no new event
        collector._check_events({"usage_percent": 96}, {}, {}, {})
        assert collector.mqtt.publish.call_count == 1

    def test_threshold_memory_high(self):
        collector = self._make_collector()
        collector._check_events({}, {"percent": 95}, {}, {})
        assert collector.mqtt.publish.call_count == 1
        topic = collector.mqtt.publish.call_args[0][0]
        assert topic == "hems/pc/events/memory_high"

    def test_threshold_gpu_hot(self):
        collector = self._make_collector()
        collector._check_events({}, {}, {"temp_c": 90}, {})
        assert collector.mqtt.publish.call_count == 1
        topic = collector.mqtt.publish.call_args[0][0]
        assert topic == "hems/pc/events/gpu_hot"

    def test_threshold_disk_low(self):
        collector = self._make_collector()
        collector._check_events({}, {}, {}, {
            "partitions": [{"mount": "/", "percent": 95}],
        })
        assert collector.mqtt.publish.call_count == 1
        topic = collector.mqtt.publish.call_args[0][0]
        assert topic == "hems/pc/events/disk_low"


class TestBridgeAPIEndpoints:
    """Test the FastAPI endpoints of the bridge."""

    @pytest.fixture
    def bridge_client(self):
        import importlib.util
        import sys
        from pathlib import Path
        from fastapi.testclient import TestClient
        from contextlib import asynccontextmanager

        # Load the bridge's main.py explicitly to avoid collision with
        # backend/main.py which is also on sys.path.
        bridge_main_path = (
            Path(__file__).resolve().parent.parent
            / "services" / "openclaw-bridge" / "src" / "main.py"
        )
        # Ensure openclaw-bridge config.py is found (not gas-bridge's config.py)
        oc_src = str(bridge_main_path.parent)
        old_config = sys.modules.pop("config", None)
        sys.path.insert(0, oc_src)
        try:
            spec = importlib.util.spec_from_file_location(
                "bridge_main", str(bridge_main_path),
            )
            bridge_main = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge_main)
        finally:
            sys.path.remove(oc_src)
            sys.modules.pop("config", None)
            if old_config is not None:
                sys.modules["config"] = old_config

        # Override lifespan to be a no-op
        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        bridge_main.app.router.lifespan_context = noop_lifespan
        return TestClient(bridge_main.app)

    def test_health_endpoint(self, bridge_client):
        resp = bridge_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "openclaw_connected" in data

    def test_get_status_endpoint(self, bridge_client):
        resp = bridge_client.get("/api/pc/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "bridge_connected" in data

    def test_get_processes_endpoint(self, bridge_client):
        resp = bridge_client.get("/api/pc/processes")
        assert resp.status_code == 200
        data = resp.json()
        assert "processes" in data

    def test_command_endpoint_requires_connection(self, bridge_client):
        """When OpenClaw is not connected, commands should return 503."""
        resp = bridge_client.post("/api/pc/command", json={
            "command": "ls", "timeout": 5,
        })
        assert resp.status_code == 503

    def test_notify_endpoint_requires_connection(self, bridge_client):
        resp = bridge_client.post("/api/pc/notify", json={
            "title": "Test", "body": "Hello",
        })
        assert resp.status_code == 503

    def test_browser_navigate_requires_connection(self, bridge_client):
        resp = bridge_client.post("/api/pc/browser/navigate", json={
            "url": "https://example.com",
        })
        assert resp.status_code == 503

    def test_process_kill_requires_connection(self, bridge_client):
        resp = bridge_client.post("/api/pc/process/kill", json={"pid": 1234})
        assert resp.status_code == 503
