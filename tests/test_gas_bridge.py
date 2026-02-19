"""
Tests for gas-bridge service (GAS client + data poller + REST API).
"""
import importlib.util
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_gas_src = str(Path(__file__).resolve().parent.parent / "services" / "gas-bridge" / "src")


def _gas_import(name: str):
    """Import a module from gas-bridge/src without polluting sys.path permanently."""
    added = _gas_src not in sys.path
    if added:
        sys.path.insert(0, _gas_src)
    old_config = sys.modules.pop("config", None)
    try:
        # Force re-import of gas-bridge's config module
        if "config" in sys.modules:
            del sys.modules["config"]
        mod = __import__(name, fromlist=[name])
        return mod
    finally:
        if added:
            sys.path.remove(_gas_src)
        # Restore previous config module so openclaw-bridge tests aren't affected
        sys.modules.pop("config", None)
        if old_config is not None:
            sys.modules["config"] = old_config


class TestGASClient:
    """Test GASClient HTTP calls."""

    @pytest.fixture
    def gas_client(self):
        mod = _gas_import("gas_client")
        return mod.GASClient(webapp_url="https://script.google.com/test/exec", api_key="test-key")

    @pytest.mark.asyncio
    async def test_fetch_constructs_correct_params(self, gas_client):
        await gas_client.start()
        try:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"events": []})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            with patch.object(gas_client._session, 'get', return_value=mock_resp) as mock_get:
                result = await gas_client.fetch("calendar_today")
                assert result == {"events": []}
                call_kwargs = mock_get.call_args[1]
                assert call_kwargs["params"]["key"] == "test-key"
                assert call_kwargs["params"]["action"] == "calendar_today"
        finally:
            await gas_client.stop()

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_error_response(self, gas_client):
        await gas_client.start()
        try:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"error": "unauthorized"})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            with patch.object(gas_client._session, 'get', return_value=mock_resp):
                result = await gas_client.fetch("health")
                assert result is None
        finally:
            await gas_client.stop()

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_http_error(self, gas_client):
        await gas_client.start()
        try:
            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            with patch.object(gas_client._session, 'get', return_value=mock_resp):
                result = await gas_client.fetch("health")
                assert result is None
        finally:
            await gas_client.stop()

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_not_started(self, gas_client):
        result = await gas_client.fetch("health")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_with_extra_params(self, gas_client):
        await gas_client.start()
        try:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"events": []})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)

            with patch.object(gas_client._session, 'get', return_value=mock_resp) as mock_get:
                await gas_client.fetch("calendar_upcoming", hours="24")
                params = mock_get.call_args[1]["params"]
                assert params["hours"] == "24"
        finally:
            await gas_client.stop()


class TestDataPoller:
    """Test DataPoller caching and status."""

    @pytest.fixture
    def poller(self):
        mod = _gas_import("data_poller")
        gas = AsyncMock()
        mqtt = MagicMock()
        return mod.DataPoller(gas, mqtt)

    def test_initial_status(self, poller):
        status = poller.get_status()
        assert status["connected"] is False
        assert status["calendar_events"] == 0
        assert status["gmail_inbox_unread"] == 0

    def test_status_after_calendar_cache(self, poller):
        poller.calendar_data = {"events": [{"id": "e1"}, {"id": "e2"}]}
        poller._connected = True
        status = poller.get_status()
        assert status["calendar_events"] == 2
        assert status["connected"] is True

    def test_status_tasks_count(self, poller):
        poller.tasks_due_data = {
            "taskLists": [
                {"id": "l1", "title": "Tasks", "tasks": [{"id": "t1"}, {"id": "t2"}]},
                {"id": "l2", "title": "Work", "tasks": [{"id": "t3"}]},
            ],
        }
        status = poller.get_status()
        assert status["tasks_due_today"] == 3

    def test_status_gmail_unread(self, poller):
        poller.gmail_data = {"labels": {"INBOX": {"unread": 15, "total": None}}}
        status = poller.get_status()
        assert status["gmail_inbox_unread"] == 15


class TestGASBridgeAPI:
    """Test gas-bridge REST API endpoints."""

    @pytest.fixture
    def bridge_client(self):
        bridge_main_path = (
            Path(__file__).resolve().parent.parent
            / "services" / "gas-bridge" / "src" / "main.py"
        )
        # Temporarily add gas-bridge/src to sys.path so main.py can resolve its imports
        old_config = sys.modules.pop("config", None)
        sys.path.insert(0, _gas_src)
        try:
            spec = importlib.util.spec_from_file_location("gas_bridge_main", str(bridge_main_path))
            bridge_main = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge_main)
        finally:
            sys.path.remove(_gas_src)
            sys.modules.pop("config", None)
            if old_config is not None:
                sys.modules["config"] = old_config

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        bridge_main.app.router.lifespan_context = noop_lifespan
        return TestClient(bridge_main.app)

    def test_health_without_startup(self, bridge_client):
        resp = bridge_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "starting"

    def test_calendar_503_without_startup(self, bridge_client):
        resp = bridge_client.get("/api/gas/calendar")
        assert resp.status_code == 503

    def test_tasks_503_without_startup(self, bridge_client):
        resp = bridge_client.get("/api/gas/tasks")
        assert resp.status_code == 503

    def test_gmail_503_without_startup(self, bridge_client):
        resp = bridge_client.get("/api/gas/gmail")
        assert resp.status_code == 503

    def test_drive_503_without_startup(self, bridge_client):
        resp = bridge_client.get("/api/gas/drive")
        assert resp.status_code == 503

    def test_status_503_without_startup(self, bridge_client):
        resp = bridge_client.get("/api/gas/status")
        assert resp.status_code == 503
