"""Tests for brain chat server ``HEMS_INTERNAL_TOKEN`` Bearer authentication.

Covers:
  (a) token unset → middleware is no-op, all requests pass (dev mode)
  (b) token set + no Authorization header → 401
  (c) token set + wrong token → 401
  (d) token set + correct token → 200
  (e) /health endpoint is always exempt regardless of token configuration
  (f) backend-side helpers generate the correct header dict

The brain middleware is tested via aiohttp's built-in test client so no Docker
or real brain instance is required.
"""

import sys
from pathlib import Path

import pytest
from aiohttp import web as aio_web
from aiohttp.test_utils import TestClient, TestServer

# Ensure brain src is on sys.path (conftest.py does this project-wide, but
# guard against running this file in isolation).
_brain_src = Path(__file__).resolve().parent.parent / "services" / "brain" / "src"
_backend_src = Path(__file__).resolve().parent.parent / "services" / "backend"
for _p in (_brain_src, _backend_src):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Helpers — build a minimal aiohttp app wired with brain_auth_middleware
# ---------------------------------------------------------------------------


def _make_app() -> aio_web.Application:
    """Return a minimal aiohttp app with the brain auth middleware attached."""
    from brain_chat_server import brain_auth_middleware

    async def _echo(request):
        return aio_web.json_response({"ok": True})

    async def _health(request):
        return aio_web.json_response({"status": "ok"})

    app = aio_web.Application(middlewares=[brain_auth_middleware])
    app.router.add_post("/chat", _echo)
    app.router.add_get("/health", _health)
    app.router.add_get("/health/", _health)
    app.router.add_post("/devices/control", _echo)
    app.router.add_post("/devices/zigbee/permit_join", _echo)
    app.router.add_post("/scenes/execute", _echo)
    app.router.add_post("/automations/evaluate", _echo)
    return app


# ---------------------------------------------------------------------------
# (a) Token unset — dev mode, all requests pass
# ---------------------------------------------------------------------------


class TestAuthDisabledWhenTokenUnset:
    @pytest.mark.asyncio
    async def test_chat_no_header_200_when_token_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/chat", json={})
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_device_control_no_header_200_when_token_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/devices/control", json={})
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_scenes_no_header_200_when_token_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/scenes/execute", json={})
            assert resp.status == 200


# ---------------------------------------------------------------------------
# (b) Token set + no Authorization header → 401
# ---------------------------------------------------------------------------


class TestAuthRequiredWhenTokenSet:
    @pytest.mark.asyncio
    async def test_chat_no_header_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/chat", json={})
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_device_control_no_header_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/devices/control", json={})
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_zigbee_permit_join_no_header_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/devices/zigbee/permit_join", json={})
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_scenes_execute_no_header_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/scenes/execute", json={})
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_automations_evaluate_no_header_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post("/automations/evaluate", json={})
            assert resp.status == 401


# ---------------------------------------------------------------------------
# (c) Token set + wrong token → 401
# ---------------------------------------------------------------------------


class TestWrongTokenRejected:
    @pytest.mark.asyncio
    async def test_chat_wrong_token_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/chat",
                json={},
                headers={"Authorization": "Bearer wrongtoken"},
            )
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_device_control_wrong_token_401(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/devices/control",
                json={},
                headers={"Authorization": "Bearer wrongtoken"},
            )
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_empty_authorization_value_401(self, monkeypatch):
        """An empty Authorization header value must be rejected."""
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/chat",
                json={},
                headers={"Authorization": ""},
            )
            assert resp.status == 401


# ---------------------------------------------------------------------------
# (d) Token set + correct token → 200
# ---------------------------------------------------------------------------


class TestCorrectTokenAccepted:
    @pytest.mark.asyncio
    async def test_chat_correct_token_200(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/chat",
                json={},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_device_control_correct_token_200(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/devices/control",
                json={},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_zigbee_permit_join_correct_token_200(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/devices/zigbee/permit_join",
                json={},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_scenes_execute_correct_token_200(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/scenes/execute",
                json={},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_automations_evaluate_correct_token_200(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.post(
                "/automations/evaluate",
                json={},
                headers={"Authorization": "Bearer s3cret"},
            )
            assert resp.status == 200


# ---------------------------------------------------------------------------
# (e) /health is always exempt
# ---------------------------------------------------------------------------


class TestHealthEndpointExempt:
    @pytest.mark.asyncio
    async def test_health_no_header_200_when_token_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get("/health")
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_trailing_slash_no_header_200_when_token_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "s3cret")
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get("/health/")
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_200_when_token_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        async with TestClient(TestServer(_make_app())) as client:
            resp = await client.get("/health")
            assert resp.status == 200


# ---------------------------------------------------------------------------
# (f) Backend-side brain_auth_headers helpers generate correct header dict
# ---------------------------------------------------------------------------


class TestBackendInternalAuthHeaders:
    """Verify each backend router's internal_auth_headers() function."""

    def _get_helper(self, module_path: str):
        import importlib

        mod = importlib.import_module(module_path)
        return mod.internal_auth_headers

    def test_devices_router_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        from routers import devices

        assert devices.internal_auth_headers() == {}

    def test_devices_router_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "tok123")
        from routers import devices

        assert devices.internal_auth_headers() == {"Authorization": "Bearer tok123"}

    def test_scenes_router_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        from routers import scenes

        assert scenes.internal_auth_headers() == {}

    def test_scenes_router_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "tok123")
        from routers import scenes

        assert scenes.internal_auth_headers() == {"Authorization": "Bearer tok123"}

    def test_automations_router_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        from routers import automations

        assert automations.internal_auth_headers() == {}

    def test_automations_router_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "tok456")
        from routers import automations

        assert automations.internal_auth_headers() == {"Authorization": "Bearer tok456"}

    def test_chat_router_internal_headers_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        from routers import chat

        assert chat.internal_auth_headers() == {}

    def test_chat_router_internal_headers_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "chattoken")
        from routers import chat

        assert chat.internal_auth_headers() == {"Authorization": "Bearer chattoken"}

    def test_home_router_internal_headers_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        from routers import home

        assert home.internal_auth_headers() == {}

    def test_home_router_internal_headers_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "hatoken")
        from routers import home

        assert home.internal_auth_headers() == {"Authorization": "Bearer hatoken"}

    def test_reads_env_each_call(self, monkeypatch):
        """No module-level caching — hot-reload friendliness."""
        from routers import devices

        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        assert devices.internal_auth_headers() == {}
        monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "newval")
        assert devices.internal_auth_headers() == {"Authorization": "Bearer newval"}
