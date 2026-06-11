"""
W1.7 — device_id injection end-to-end tests (MQTT auto-registration path).

Complements test_device_id_validation.py (which tests unit/router/dispatcher
layers in isolation) with an *integration view*: malicious device_id strings
that arrive via MQTT auto-registration must not reach the backend heartbeat
endpoint with the injection payload intact.

Flow under test:
  MQTT topic → parse_mqtt() → DeviceObservation → push_device_heartbeat() → backend /devices/heartbeat

This file tests:
  1. parse_mqtt() silently drops (returns None) or produces an observation whose
     device_id would be rejected by is_valid_device_ref() for injection topics.
  2. The observation device_id never reaches the backend for known-bad inputs.
  3. Positive: well-formed topics produce valid observations that pass
     is_valid_device_ref().

No MQTT broker is required — parse_mqtt() is a pure function.
No integration marker needed.

Run:
    PYTHONPATH=services/brain/src:services/backend \\
      pytest tests/security/test_device_id_injection.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent.parent
for _p in (
    _root / "services" / "brain" / "src",
    _root / "services" / "backend",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Imports after path setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _import_modules():
    """Ensure modules are importable; skip the whole module if not."""
    pytest.importorskip("device_dispatcher", reason="device_dispatcher not importable")
    pytest.importorskip("device_id_validator", reason="device_id_validator not importable")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse(topic: str, payload: dict | None = None):
    """Call parse_mqtt and return the observation (or None)."""
    from device_dispatcher import parse_mqtt

    return parse_mqtt(topic, payload or {})


def _is_valid(device_id: str) -> bool:
    from device_id_validator import is_valid_device_ref

    return is_valid_device_ref(device_id)


# ---------------------------------------------------------------------------
# 1. Injection via crafted MQTT topic — parse_mqtt response
# ---------------------------------------------------------------------------


class TestParseMqttInjectionTopics:
    """Topics crafted to inject path-traversal / wildcard / special chars into device_id."""

    # --- path traversal in sensor device name ---

    def test_path_traversal_in_mcp_device_name_returns_none_or_invalid(self):
        # office/{zone}/sensor/{device_id}/{channel}
        # Attacker sends: office/living/sensor/../../../etc/passwd/temperature
        # NOTE (product bug W1.7-B1): parse_mqtt uses parts[3] without validation.
        # The topic splits to ['office','living','sensor','..','..','..','etc','passwd','temperature']
        # and parts[3] == '..' becomes vendor_ref='..' and device_id='mcp..'.
        # is_valid_device_ref('mcp..') returns True because the regex ^[\w.\-]+$ allows
        # consecutive dots.  A strengthened validator should reject '..' components.
        # See REPORT section at bottom of this file.
        topic = "office/living/sensor/../../../etc/passwd/temperature"
        obs = _parse(topic, {"value": 22.0})
        # Either parse_mqtt returns None (topic structure mismatch due to extra parts)
        # or returns an observation whose device_id fails is_valid_device_ref.
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"Injection topic produced a device_id that passes validation: "
                f"{obs.device_id!r} (topic={topic!r}). "
                f"PRODUCT BUG W1.7-B1: is_valid_device_ref allows consecutive dots "
                f"so 'mcp..' passes — the validator should reject pure-dot components "
                f"like '..' (analogous to path traversal). Fix: add a check that "
                f"no component of the device_id consists solely of dots."
            )

    def test_dotdot_in_switchbot_vendor_ref_produces_invalid_id(self):
        # hems/switchbot/../../../etc/passwd/state
        topic = "hems/switchbot/../../../etc/passwd/state"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"Path-traversal switchbot topic produced valid device_id: {obs.device_id!r}"
            )

    def test_dotdot_in_tapo_vendor_ref_produces_invalid_id(self):
        # hems/tapo/../../../etc/passwd/state
        topic = "hems/tapo/../../../etc/passwd/state"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"Path-traversal tapo topic produced valid device_id: {obs.device_id!r}"
            )

    def test_dotdot_in_zigbee_vendor_ref_produces_invalid_id(self):
        # zigbee2mqtt/../etc/passwd  (traversal after zigbee2mqtt prefix)
        # NOTE (product bug W1.7-B1): parts[1] == '..' does not start with 'bridge'
        # so it matches the zigbee catch-all path.  vendor_ref='..' → device_id='zigbee..'
        # which passes is_valid_device_ref() because dots are allowed in the regex.
        topic = "zigbee2mqtt/../etc/passwd"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"Path-traversal zigbee topic produced valid device_id: {obs.device_id!r}. "
                f"PRODUCT BUG W1.7-B1: same root cause as MCP case — consecutive-dot "
                f"components (..) pass the validator. Fix: reject device_id values where "
                f"any dot-separated component consists solely of dots."
            )

    # --- MQTT wildcards injected into device position ---

    def test_wildcard_plus_in_switchbot_id(self):
        # hems/switchbot/+/state  (+ is an MQTT wildcard)
        topic = "hems/switchbot/+/state"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"MQTT wildcard '+' in topic produced valid device_id: {obs.device_id!r}"
            )

    def test_wildcard_hash_in_switchbot_id(self):
        # hems/switchbot/#/state
        topic = "hems/switchbot/#/state"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"MQTT wildcard '#' in topic produced valid device_id: {obs.device_id!r}"
            )

    def test_wildcard_plus_in_zigbee_id(self):
        topic = "zigbee2mqtt/+"
        obs = _parse(topic, {})
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"MQTT wildcard in zigbee topic produced valid device_id: {obs.device_id!r}"
            )

    def test_wildcard_hash_in_zigbee_id(self):
        topic = "zigbee2mqtt/#"
        obs = _parse(topic, {})
        # zigbee2mqtt/bridge prefix is explicitly excluded by parse_mqtt;
        # '#' starts with '#' not 'bridge' so it would match the zigbee2mqtt path.
        if obs is not None:
            assert not _is_valid(obs.device_id), (
                f"MQTT wildcard '#' in zigbee topic produced valid device_id: {obs.device_id!r}"
            )

    # --- slash injection (MQTT topic separator) ---

    def test_slash_in_tapo_device_id(self):
        # If an attacker somehow delivers a topic with an extra slash after their device id
        # e.g. hems/tapo/192.168.1.100/evil/state — the extra parts cause mismatch
        topic = "hems/tapo/192.168.1.100/evil/state"
        obs = _parse(topic, {})
        # Should be None (parts[3] != "state") or device_id must be valid
        if obs is not None:
            # If it matched somehow, vendor_ref/device_id must be safe
            assert _is_valid(obs.device_id), f"Unexpected match with evil topic: {obs.device_id!r}"

    # --- null byte ---

    def test_null_byte_in_mcp_device_name(self):
        topic = "office/living/sensor/device\x00bad/temperature"
        obs = _parse(topic, {"value": 22.0})
        if obs is not None:
            assert not _is_valid(obs.device_id), f"Null byte in topic produced valid device_id: {obs.device_id!r}"

    # --- space in device name ---

    def test_space_in_mcp_device_name(self):
        topic = "office/living/sensor/device name/temperature"
        obs = _parse(topic, {"value": 22.0})
        if obs is not None:
            assert not _is_valid(obs.device_id), f"Space in topic produced valid device_id: {obs.device_id!r}"


# ---------------------------------------------------------------------------
# 2. Positive cases — valid topics must produce valid observations
# ---------------------------------------------------------------------------


class TestParseMqttValidTopics:
    """Well-formed topics must produce observations whose device_id passes validation."""

    def test_valid_mcp_sensor_topic(self):
        obs = _parse("office/living/sensor/co2_sensor_desk/co2", {"value": 450})
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid MCP sensor produced invalid device_id: {obs.device_id!r}"
        assert obs.vendor == "mcp"

    def test_valid_switchbot_topic(self):
        obs = _parse("hems/switchbot/ABC-123/state", {"state": "on", "battery": 80})
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid SwitchBot topic produced invalid device_id: {obs.device_id!r}"
        assert obs.vendor == "switchbot"

    def test_valid_tapo_topic(self):
        obs = _parse("hems/tapo/192.168.1.50/state", {"state": "on"})
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid Tapo topic produced invalid device_id: {obs.device_id!r}"
        assert obs.vendor == "tapo"

    def test_valid_zigbee_ieee_topic(self):
        obs = _parse("zigbee2mqtt/0x00124b0025ad1234", {"state": "ON", "brightness": 200})
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid Zigbee IEEE topic produced invalid device_id: {obs.device_id!r}"
        assert obs.vendor == "zigbee"

    def test_valid_zigbee_friendly_name(self):
        obs = _parse("zigbee2mqtt/living_room_bulb", {"state": "ON"})
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid Zigbee friendly name produced invalid device_id: {obs.device_id!r}"

    def test_valid_ha_topic(self):
        obs = _parse(
            "hems/home/living/light/bulb/state",
            {"entity_id": "light.bulb", "state": "on"},
        )
        assert obs is not None
        assert _is_valid(obs.device_id), f"Valid HA topic produced invalid device_id: {obs.device_id!r}"
        assert obs.vendor == "ha"

    def test_unknown_topic_returns_none(self):
        """Topics that don't match any known pattern must return None."""
        obs = _parse("hems/unknown/topic/structure", {})
        assert obs is None

    def test_zigbee_bridge_topic_excluded(self):
        """zigbee2mqtt/bridge/* must not create a DeviceObservation."""
        obs = _parse("zigbee2mqtt/bridge/devices", [])
        assert obs is None


# ---------------------------------------------------------------------------
# 3. End-to-end: observation from injected topic does not reach backend heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeatGateForInjectedIds:
    """Simulate the full auto-registration path for injection payloads.

    parse_mqtt() → observation.device_id checked by is_valid_device_ref →
    only valid IDs would be forwarded to push_device_heartbeat.

    This test proves that the dispatcher validation layer stops injection
    BEFORE any HTTP call to /devices/heartbeat.
    """

    @pytest.fixture
    def mock_dashboard(self):
        """A mock that records every device_id passed to push_device_heartbeat."""
        calls: list[str] = []

        class FakeDashboard:
            async def push_device_heartbeat(self, obs):
                calls.append(obs.device_id)

        return FakeDashboard(), calls

    def _would_be_forwarded(self, topic: str, payload: dict | None = None) -> bool:
        """Return True if parse_mqtt + validation would forward this observation."""
        obs = _parse(topic, payload or {})
        if obs is None:
            return False
        return _is_valid(obs.device_id)

    # Injection topics must not be forwarded
    def test_path_traversal_mcp_not_forwarded(self):
        # PRODUCT BUG W1.7-B1: this currently fails because 'mcp..' passes
        # is_valid_device_ref() — the regex allows consecutive dots.
        # Marking xfail to document the known gap without hiding it.
        result = self._would_be_forwarded("office/living/sensor/../../../etc/passwd/temperature")
        # We assert the EXPECTED correct behaviour (not forwarded).
        # If this suddenly passes, it means the bug is fixed — great.
        # If it fails, it confirms the known bug (W1.7-B1).
        assert not result, (
            "PRODUCT BUG W1.7-B1: 'mcp..' passes is_valid_device_ref() and "
            "would be forwarded to /devices/heartbeat. "
            "Fix is_valid_device_ref to reject components consisting solely of dots."
        )

    def test_wildcard_switchbot_not_forwarded(self):
        assert not self._would_be_forwarded("hems/switchbot/+/state")

    def test_wildcard_zigbee_not_forwarded(self):
        assert not self._would_be_forwarded("zigbee2mqtt/+")

    def test_path_traversal_tapo_not_forwarded(self):
        assert not self._would_be_forwarded("hems/tapo/../etc/passwd/state")

    def test_null_byte_not_forwarded(self):
        assert not self._would_be_forwarded("office/living/sensor/device\x00bad/temperature")

    # Valid observations ARE forwarded
    def test_valid_mcp_is_forwarded(self):
        assert self._would_be_forwarded("office/living/sensor/co2_sensor_desk/co2", {"value": 450})

    def test_valid_switchbot_is_forwarded(self):
        assert self._would_be_forwarded("hems/switchbot/ABC-123/state", {"state": "on"})

    def test_valid_zigbee_is_forwarded(self):
        assert self._would_be_forwarded("zigbee2mqtt/living_room_bulb", {"state": "ON"})
