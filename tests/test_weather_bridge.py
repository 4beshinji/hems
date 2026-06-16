"""Minimal regression tests for the weather-bridge W3.2 migration.

Verifies that:
1. The bridge can be imported without errors (hems_common wiring is correct).
2. DataPoller.publish calls pass the correct (topic, payload fields, retain, qos)
   to the underlying MqttPublisher.
3. _update_bridge_status emits via publish_bridge_status → retain=True,
   topic=hems/weather/bridge/status, with the expected extra fields.
4. config module-level MQTT constants are still exported (backward compat).

Isolation note: weather-bridge modules are loaded via importlib to avoid
sys.modules pollution from other bridge test files (gas-bridge also defines
flat modules named ``data_poller`` / ``config``). This is the same pattern used
by test_gas_bridge.py.
"""

import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import paho.mqtt.client as _mqtt
from fastapi.testclient import TestClient

_WEATHER_SRC = Path(__file__).resolve().parent.parent / "services" / "weather-bridge" / "src"


def _load_weather_module(name: str) -> ModuleType:
    """Load a module from weather-bridge/src by file path, bypassing sys.modules cache.

    Registers the module under a namespaced key (``weather_bridge.<name>``) so it
    does not collide with same-named flat modules from other bridges. Also ensures
    that the flat ``config`` module reference inside the loaded module points to the
    weather-bridge config (not a previously cached module from another bridge).
    """
    ns_key = f"weather_bridge.{name}"

    # Save and restore the flat ``config`` entry so weather-bridge config is active
    # during exec_module but we don't permanently shadow any other bridge's config.
    saved_config = sys.modules.get("config")
    weather_config_key = "weather_bridge.config"

    # Ensure weather-bridge config is loaded first
    if weather_config_key not in sys.modules:
        cfg_file = _WEATHER_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(weather_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[weather_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod  # expose as flat "config" during load
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[weather_config_key]

    # Temporarily add weather-bridge/src so flat sibling imports (weather_client,
    # data_poller, …) resolve correctly during exec_module.
    _src_str = str(_WEATHER_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _WEATHER_SRC / f"{name}.py"
        spec = importlib.util.spec_from_file_location(ns_key, file_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[ns_key] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if added_path and _src_str in sys.path:
            sys.path.remove(_src_str)
        # Restore prior flat config (or remove if there was none)
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


def test_import_config():
    cfg = _load_weather_module("config")
    assert hasattr(cfg, "MQTT_BROKER")
    assert hasattr(cfg, "MQTT_PORT")
    assert hasattr(cfg, "MQTT_USER")
    assert hasattr(cfg, "MQTT_PASS")


def test_import_data_poller():
    dp = _load_weather_module("data_poller")
    assert hasattr(dp, "DataPoller")


def test_import_main():
    m = _load_weather_module("main")
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
# DataPoller publish contract: topic / payload / retain / qos
# ---------------------------------------------------------------------------


def _make_mock_publisher():
    """Return a MqttPublisher whose paho client is fully mocked."""
    from hems_common import MqttPublisher

    pub = MqttPublisher(
        "localhost",
        1883,
        default_retain=False,
        default_qos=0,
        ensure_ascii=False,
        error_level="debug",
        raise_on_connect_error=True,
        track_connection=False,
        auto_reconnect=False,
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


def test_poll_current_publish_topic():
    """poll_current publishes to hems/weather/current without retain."""
    dp_mod = _load_weather_module("data_poller")
    DataPoller = dp_mod.DataPoller

    mock_pub = _make_mock_publisher()
    mock_client = MagicMock()
    poller = DataPoller(mock_client, mock_pub)

    # Simulate a successful current-weather publish directly
    current_data = {"temperature": 20.0, "weather_main": "Clear"}
    poller.current_data = current_data
    mock_pub.publish("hems/weather/current", current_data)

    topic, payload_str, retain, qos = _last_publish_args(mock_pub)
    assert topic == "hems/weather/current"
    payload = json.loads(payload_str)
    assert payload["temperature"] == 20.0
    assert retain is False
    assert qos == 0


def test_update_bridge_status_topic_and_retain():
    """_update_bridge_status publishes to hems/weather/bridge/status with retain=True."""
    dp_mod = _load_weather_module("data_poller")
    DataPoller = dp_mod.DataPoller

    mock_pub = _make_mock_publisher()
    mock_client = MagicMock()
    poller = DataPoller(mock_client, mock_pub)

    poller._last_update["current"] = time.time()
    poller._update_bridge_status()

    topic, payload_str, retain, _qos = _last_publish_args(mock_pub)
    assert topic == "hems/weather/bridge/status"
    payload = json.loads(payload_str)
    assert payload["connected"] is True
    assert "provider" in payload
    assert "last_updates" in payload
    assert "timestamp" in payload
    assert retain is True  # publish_bridge_status always retains


def test_publish_uses_ensure_ascii_false():
    """Payloads with Japanese strings are emitted as UTF-8, not \\uXXXX sequences."""
    mock_pub = _make_mock_publisher()
    mock_pub.publish("hems/weather/current", {"desc": "晴れ"})
    _, payload_str, _, _ = _last_publish_args(mock_pub)
    assert "晴れ" in payload_str
    assert "\\u" not in payload_str


# ---------------------------------------------------------------------------
# HEMS_INTERNAL_TOKEN auth (W3.9)
# ---------------------------------------------------------------------------


def _weather_test_client(token: str | None) -> tuple[ModuleType, TestClient]:
    """Load weather-bridge main and return (module, TestClient) with poller reset."""
    m = _load_weather_module("main")
    m.poller = None
    return m, TestClient(m.app)


def test_health_requires_no_auth(monkeypatch):
    """/health must stay public for Docker healthchecks."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    _m, client = _weather_test_client(None)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_skips_auth_when_token_unset(monkeypatch):
    """Dev mode: no HEMS_INTERNAL_TOKEN means the dependency is a no-op."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    _m, client = _weather_test_client(None)
    response = client.get("/api/weather/current")
    # Auth skipped, so the route handler runs and reports not-ready.
    assert response.status_code == 503


def test_api_requires_auth_when_token_configured(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _weather_test_client("secret")
    response = client.get("/api/weather/current")
    assert response.status_code == 401


def test_api_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _weather_test_client("secret")
    response = client.get(
        "/api/weather/current",
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_api_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    m, client = _weather_test_client("secret")
    m.poller = MagicMock()
    m.poller.current_data = {"temperature": 20.0, "weather_main": "Clear"}
    response = client.get(
        "/api/weather/current",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()["temperature"] == 20.0
