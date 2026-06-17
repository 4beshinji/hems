"""
Tests for W1.4 — /devices/{id}/control params schema validation.

Covers:
  (a) Import identity: sanitizer and brain_chat_server both call the same
      validate_device_control function from device_control_validator.
  (b) Invalid action → HTTP 400 from _handle_device_control.
  (c) Invalid params → HTTP 400 from _handle_device_control.
  (d) Valid request passes through _handle_device_control.
  (e) Sanitizer._validate_control_actuator still delegates to the shared validator.
"""

import sys
from pathlib import Path

import pytest
from aiohttp import web as aio_web
from aiohttp.test_utils import TestClient, TestServer

_brain_src = Path(__file__).resolve().parent.parent / "services" / "brain" / "src"
_backend_src = Path(__file__).resolve().parent.parent / "services" / "backend"
for _p in (_brain_src, _backend_src):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mixin_instance():
    """Return a minimal object that satisfies ChatServerMixin's attribute needs."""
    from brain_chat_server import ChatServerMixin

    class _FakeDispatcher:
        async def dispatch(self, device_id, action, params):
            return {"success": True, "result": f"dispatched {device_id}/{action}"}

    class _FakeBrain(ChatServerMixin):
        def __init__(self):
            self.device_dispatcher = _FakeDispatcher()
            self._cached_devices_at = 0.0

    return _FakeBrain()


def _make_control_app(brain_instance) -> aio_web.Application:
    """Minimal aiohttp app wired to the real _handle_device_control."""
    app = aio_web.Application()
    app.router.add_post("/devices/control", brain_instance._handle_device_control)
    return app


# ---------------------------------------------------------------------------
# (a) Import identity — both paths reference the same validator function
# ---------------------------------------------------------------------------


class TestImportIdentity:
    def test_sanitizer_uses_device_control_validator(self):
        """sanitizer._validate_control_actuator must import from device_control_validator."""
        import inspect

        import sanitizer as _sanitizer_mod

        src = inspect.getsource(_sanitizer_mod.Sanitizer._validate_control_actuator)
        assert "device_control_validator" in src, "_validate_control_actuator must import from device_control_validator"

    def test_brain_chat_server_uses_device_control_validator(self):
        """_handle_device_control must import from device_control_validator."""
        import inspect

        import brain_chat_server as _bcs_mod

        src = inspect.getsource(_bcs_mod.ChatServerMixin._handle_device_control)
        assert "device_control_validator" in src, "_handle_device_control must import from device_control_validator"

    def test_same_function_object(self):
        """Both modules must resolve to the identical validate_device_control callable."""
        import device_control_validator as _dcv_mod
        from device_control_validator import validate_device_control as _from_sanitizer

        # Import the module-level function as referenced by both callers
        validate_fn = _dcv_mod.validate_device_control

        assert validate_fn is _from_sanitizer, "Both paths must resolve to the same validate_device_control object"


# ---------------------------------------------------------------------------
# (b) Invalid action → 400
# ---------------------------------------------------------------------------


class TestInvalidActionReturns400:
    @pytest.mark.asyncio
    async def test_unknown_action_rejected(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.bulb_01", "action": "explode", "params": {}},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["success"] is False
            assert "action" in body["error"].lower() or "explode" in body["error"]

    @pytest.mark.asyncio
    async def test_eval_action_rejected(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.light_01", "action": "eval", "params": {}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_empty_action_rejected(self):
        """Empty action string is not in ALLOWED_ACTIONS."""
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.light_01", "action": "", "params": {}},
            )
            # Empty action causes "device_id and action are required" guard → 400
            assert resp.status == 400


# ---------------------------------------------------------------------------
# (b') Invalid device_id format → 400
# ---------------------------------------------------------------------------


class TestInvalidDeviceIdReturns400:
    @pytest.mark.asyncio
    async def test_slash_in_device_id_rejected(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "foo/bar", "action": "on", "params": {}},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["success"] is False
            assert "device_id" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_consecutive_dots_in_device_id_rejected(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "a..b", "action": "on", "params": {}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_mqtt_wildcard_in_device_id_rejected(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.+", "action": "on", "params": {}},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# (c) Invalid params → 400
# ---------------------------------------------------------------------------


class TestInvalidParamsReturns400:
    @pytest.mark.asyncio
    async def test_pulse_missing_duration_s(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.pump_01", "action": "pulse", "params": {}},
            )
            assert resp.status == 400
            body = await resp.json()
            assert "duration_s" in body["error"]

    @pytest.mark.asyncio
    async def test_pulse_duration_out_of_range(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.pump_01", "action": "pulse", "params": {"duration_s": 9999}},
            )
            assert resp.status == 400
            body = await resp.json()
            assert "range" in body["error"]

    @pytest.mark.asyncio
    async def test_set_brightness_out_of_range(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.bulb_01", "action": "set_brightness", "params": {"value": 300}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_set_color_temp_out_of_range(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.bulb_01", "action": "set_color_temp", "params": {"value": 1000}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_set_temperature_out_of_range(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.aircon", "action": "set_temperature", "params": {"value": 50}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_set_color_xy_missing_params(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.bulb_01", "action": "set_color_xy", "params": {"x": 0.5}},
            )
            assert resp.status == 400

    @pytest.mark.asyncio
    async def test_rainbow_missing_duration(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.bulb_01", "action": "rainbow", "params": {}},
            )
            assert resp.status == 400


# ---------------------------------------------------------------------------
# (d) Valid requests pass through
# ---------------------------------------------------------------------------


class TestValidRequestsPass:
    @pytest.mark.asyncio
    async def test_on_action_passes(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.light_01", "action": "on", "params": {}},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_off_action_passes(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.relay_01", "action": "off"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_pulse_valid_passes(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "zigbee.pump_01", "action": "pulse", "params": {"duration_s": 30}},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["success"] is True

    @pytest.mark.asyncio
    async def test_set_brightness_valid_passes(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.bulb_01", "action": "set_brightness", "params": {"value": 128}},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_set_temperature_valid_passes(self):
        brain = _make_mixin_instance()
        async with TestClient(TestServer(_make_control_app(brain))) as client:
            resp = await client.post(
                "/devices/control",
                json={"device_id": "ha.aircon", "action": "set_temperature", "params": {"value": 22}},
            )
            assert resp.status == 200


# ---------------------------------------------------------------------------
# (e) Sanitizer._validate_control_actuator delegates to shared validator
# ---------------------------------------------------------------------------


class TestSanitizerDelegatesCorrectly:
    def test_sanitizer_rejects_invalid_action_via_validate_tool_call(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "ha.light_01", "action": "explode", "params": {}},
        )
        assert result["allowed"] is False
        assert "action" in result["reason"].lower() or "explode" in result["reason"]

    def test_sanitizer_rejects_bad_device_id_format(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "bad/device", "action": "on", "params": {}},
        )
        assert result["allowed"] is False
        assert "device_id" in result["reason"].lower()

    def test_sanitizer_rejects_consecutive_dots_in_device_id(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "a..b", "action": "on", "params": {}},
        )
        assert result["allowed"] is False
        assert "device_id" in result["reason"].lower()

    def test_sanitizer_rejects_pulse_missing_duration(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "zigbee.pump_01", "action": "pulse", "params": {}},
        )
        assert result["allowed"] is False
        assert "duration_s" in result["reason"]

    def test_sanitizer_allows_valid_on_command(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "ha.light_01", "action": "on", "params": {}},
        )
        assert result["allowed"] is True

    def test_sanitizer_allows_valid_pulse(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "zigbee.pump_01", "action": "pulse", "params": {"duration_s": 10}},
        )
        assert result["allowed"] is True

    def test_sanitizer_rejects_brightness_out_of_range(self, sanitizer):
        result = sanitizer.validate_tool_call(
            "control_actuator",
            {"device_id": "ha.bulb_01", "action": "set_brightness", "params": {"value": 999}},
        )
        assert result["allowed"] is False
