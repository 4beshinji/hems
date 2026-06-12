"""Minimal regression tests for the switchbot-bridge W3.2 migration.

Verifies that:
1. The bridge can be imported without errors (hems_common wiring is correct).
2. config module-level MQTT constants are still exported (backward compat).
3. MqttPublisher is constructed with switchbot profile settings:
   default_retain=True, track_connection=False (unconditional publish).
4. publish_bridge_status emits to hems/switchbot/bridge/status with retain=True.
5. ensure_ascii=False: Japanese strings in payloads are emitted as UTF-8,
   not \\uXXXX sequences.

Isolation: switchbot-bridge modules are loaded via importlib to avoid
sys.modules pollution from other bridge test files that share flat module
names (config, device_mapper, etc.).
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import paho.mqtt.client as _mqtt

_SB_SRC = Path(__file__).resolve().parent.parent / "services" / "switchbot-bridge" / "src"


def _load_sb_module(name: str) -> ModuleType:
    """Load a module from switchbot-bridge/src by file path.

    Registers under ``switchbot_bridge.<name>`` to avoid collision with
    same-named flat modules from other bridges. Temporarily exposes the
    switchbot-bridge config as the flat ``config`` so sibling imports resolve.
    """
    ns_key = f"switchbot_bridge.{name}"

    # Save and restore flat ``config`` entry
    saved_config = sys.modules.get("config")
    sb_config_key = "switchbot_bridge.config"

    # Ensure switchbot-bridge config is loaded first
    if sb_config_key not in sys.modules:
        cfg_file = _SB_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(sb_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[sb_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[sb_config_key]

    # Temporarily add switchbot-bridge/src to sys.path for sibling imports
    _src_str = str(_SB_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _SB_SRC / f"{name}.py"
        spec = importlib.util.spec_from_file_location(ns_key, file_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[ns_key] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if added_path and _src_str in sys.path:
            sys.path.remove(_src_str)
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_import_config():
    cfg = _load_sb_module("config")
    assert hasattr(cfg, "MQTT_BROKER")
    assert hasattr(cfg, "MQTT_PORT")
    assert hasattr(cfg, "MQTT_USER")
    assert hasattr(cfg, "MQTT_PASS")


def test_import_device_mapper():
    dm = _load_sb_module("device_mapper")
    assert hasattr(dm, "DeviceMapper")


def test_import_main():
    m = _load_sb_module("main")
    assert hasattr(m, "app")


# ---------------------------------------------------------------------------
# config: MQTT constants come from load_mqtt_config (env-driven)
# ---------------------------------------------------------------------------


def test_config_mqtt_defaults(monkeypatch):
    """With no env overrides the defaults match mosquitto/1883."""
    for var in ("MQTT_BROKER", "MQTT_PORT", "MQTT_USER", "MQTT_PASS"):
        monkeypatch.delenv(var, raising=False)

    from hems_common import load_mqtt_config

    cfg = load_mqtt_config()
    assert cfg.broker == "mosquitto"
    assert cfg.port == 1883
    assert cfg.user == ""
    assert cfg.password == ""


# ---------------------------------------------------------------------------
# MqttPublisher profile: switchbot uses retain=True, track_connection=False
# ---------------------------------------------------------------------------


def _make_mock_publisher():
    """Return a MqttPublisher with the switchbot profile and mocked paho client."""
    from hems_common import MqttPublisher

    pub = MqttPublisher(
        "localhost",
        1883,
        default_retain=True,
        default_qos=0,
        ensure_ascii=False,
        error_level="error",
        raise_on_connect_error=False,
        track_connection=False,
        auto_reconnect=True,
    )
    pub.client = MagicMock()
    pub.client.publish.return_value = MagicMock(rc=_mqtt.MQTT_ERR_SUCCESS)
    return pub


def _last_publish_args(mock_pub):
    """Return (topic, json_payload_str, retain, qos) from the last client.publish call."""
    args, kwargs = mock_pub.client.publish.call_args
    topic = args[0]
    payload_str = args[1]
    return topic, payload_str, kwargs.get("retain"), kwargs.get("qos")


def test_publish_uses_retain_true():
    """With default_retain=True, publish always sets retain=True."""
    pub = _make_mock_publisher()
    pub.publish("hems/switchbot/test", {"state": "on"})
    _, _, retain, _ = _last_publish_args(pub)
    assert retain is True


def test_unconditional_publish_when_not_connected():
    """track_connection=False means publish proceeds even when MQTT is disconnected."""
    pub = _make_mock_publisher()
    # _connected is False by default since track_connection=False means no callbacks
    assert pub._connected is False
    result = pub.publish("hems/switchbot/test", {"state": "on"})
    assert result is True
    pub.client.publish.assert_called_once()


def test_publish_bridge_status_topic_and_retain():
    """publish_bridge_status emits to hems/switchbot/bridge/status with retain=True."""
    from hems_common import publish_bridge_status

    pub = _make_mock_publisher()
    publish_bridge_status(pub, "switchbot", device_count=3, ir_device_count=2)

    topic, payload_str, retain, _qos = _last_publish_args(pub)
    assert topic == "hems/switchbot/bridge/status"
    payload = json.loads(payload_str)
    assert payload["connected"] is True
    assert payload["device_count"] == 3
    assert payload["ir_device_count"] == 2
    assert retain is True


def test_publish_bridge_status_disconnected():
    """publish_bridge_status with connected=False publishes retained False payload."""
    from hems_common import publish_bridge_status

    pub = _make_mock_publisher()
    publish_bridge_status(pub, "switchbot", connected=False)

    topic, payload_str, retain, _ = _last_publish_args(pub)
    assert topic == "hems/switchbot/bridge/status"
    payload = json.loads(payload_str)
    assert payload["connected"] is False
    assert retain is True


def test_publish_uses_ensure_ascii_false():
    """Japanese strings in payloads are emitted as UTF-8, not \\uXXXX sequences."""
    pub = _make_mock_publisher()
    pub.publish("hems/switchbot/test", {"friendly_name": "リビングライト", "state": "on"})
    _, payload_str, _, _ = _last_publish_args(pub)
    assert "リビングライト" in payload_str
    assert "\\u" not in payload_str
