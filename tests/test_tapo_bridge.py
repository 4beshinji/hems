"""Minimal regression tests for the tapo-bridge W3.2 migration.

Verifies that:
1. The bridge can be imported without errors (hems_common wiring is correct).
2. mqtt_pub.publish calls pass the correct topic/payload/retain/qos.
3. publish_bridge_status emits via hems/tapo/bridge/status with retain=True.
4. config module exports (load_config, Config) still work.
5. ensure_ascii=False: Japanese payloads are emitted as raw UTF-8.

Isolation: tapo-bridge modules are loaded via importlib to avoid sys.modules
pollution from other bridge test files.
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import paho.mqtt.client as _mqtt

_TAPO_SRC = Path(__file__).resolve().parent.parent / "services" / "tapo-bridge" / "src"


def _load_tapo_module(name: str) -> ModuleType:
    """Load a module from tapo-bridge/src by file path, bypassing sys.modules cache."""
    ns_key = f"tapo_bridge.{name}"

    saved_config = sys.modules.get("config")
    tapo_config_key = "tapo_bridge.config"

    # Ensure tapo-bridge config is loaded first
    if tapo_config_key not in sys.modules:
        cfg_file = _TAPO_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(tapo_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[tapo_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[tapo_config_key]

    _src_str = str(_TAPO_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _TAPO_SRC / f"{name}.py"
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
    cfg_mod = _load_tapo_module("config")
    assert hasattr(cfg_mod, "load_config")
    assert hasattr(cfg_mod, "Config")


def test_import_main():
    # kasa is a Docker-only dependency; stub it before loading main
    kasa_stub = MagicMock()
    kasa_stub.Credentials = MagicMock()
    kasa_stub.Device = MagicMock()
    kasa_stub.Discover = MagicMock()
    sys.modules.setdefault("kasa", kasa_stub)

    m = _load_tapo_module("main")
    assert hasattr(m, "app")


def test_config_load_defaults(monkeypatch):
    """load_config returns sensible defaults from env."""
    for var in (
        "TAPO_USERNAME",
        "TAPO_PASSWORD",
        "TAPO_DEVICES",
        "TAPO_POLL_INTERVAL",
        "MQTT_BROKER",
        "MQTT_PORT",
        "MQTT_USER",
        "MQTT_PASS",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg_mod = _load_tapo_module("config")
    # Re-exec to pick up monkeypatched env
    sys.modules.pop("tapo_bridge.config", None)
    sys.modules.pop("config", None)
    cfg_mod = _load_tapo_module("config")
    cfg = cfg_mod.load_config()
    assert cfg.mqtt_broker == "mosquitto"
    assert cfg.mqtt_port == 1883
    assert cfg.devices == {}
    assert cfg.poll_interval_sec == 30


# ---------------------------------------------------------------------------
# MqttPublisher helper
# ---------------------------------------------------------------------------


def _make_tapo_publisher():
    """Return a MqttPublisher configured as tapo-bridge uses it."""
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


# ---------------------------------------------------------------------------
# Publish contract: topic / payload / retain / qos
# ---------------------------------------------------------------------------


def test_state_publish_topic_and_retain():
    """Device state publishes to hems/tapo/{ref}/state with retain=True."""
    mock_pub = _make_tapo_publisher()
    payload = {
        "entity_id": "tapo.plug_desk",
        "vendor_ref": "plug_desk",
        "zone": "home",
        "friendly_name": "plug_desk",
        "domain": "switch",
        "on": True,
        "power_w": 12.5,
    }
    mock_pub.publish("hems/tapo/plug_desk/state", payload)

    topic, payload_str, retain, qos = _last_publish_args(mock_pub)
    assert topic == "hems/tapo/plug_desk/state"
    parsed = json.loads(payload_str)
    assert parsed["entity_id"] == "tapo.plug_desk"
    assert parsed["domain"] == "switch"
    assert retain is True
    assert qos == 0


def test_bridge_status_topic_and_retain():
    """publish_bridge_status publishes to hems/tapo/bridge/status with retain=True."""
    from hems_common import publish_bridge_status

    mock_pub = _make_tapo_publisher()
    publish_bridge_status(mock_pub, "tapo", device_count=2)

    topic, payload_str, retain, _qos = _last_publish_args(mock_pub)
    assert topic == "hems/tapo/bridge/status"
    parsed = json.loads(payload_str)
    assert parsed["connected"] is True
    assert parsed["device_count"] == 2
    assert retain is True


def test_publish_ensure_ascii_false():
    """Payloads with Japanese strings are emitted as raw UTF-8 (not \\uXXXX)."""
    mock_pub = _make_tapo_publisher()
    mock_pub.publish("hems/tapo/plug_desk/state", {"friendly_name": "デスクライト"})
    _, payload_str, _, _ = _last_publish_args(mock_pub)
    assert "デスクライト" in payload_str
    assert "\\u" not in payload_str


def test_track_connection_false_publishes_unconditionally():
    """With track_connection=False, publish succeeds even when _connected=False."""
    mock_pub = _make_tapo_publisher()
    # _connected is False by default when track_connection=False (no callback updates it)
    assert mock_pub._connected is False
    result = mock_pub.publish("hems/tapo/plug_desk/state", {"on": True})
    assert result is True
    assert mock_pub.client.publish.called


# ---------------------------------------------------------------------------
# W3.9 internal-token auth regression tests
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient


def _load_main_fresh():
    """Reload tapo-bridge main.py so auth tests see a clean module state."""
    kasa_stub = MagicMock()
    kasa_stub.Credentials = MagicMock()
    kasa_stub.Device = MagicMock()
    kasa_stub.Discover = MagicMock()
    sys.modules.setdefault("kasa", kasa_stub)

    for key in ("tapo_bridge.main", "main"):
        sys.modules.pop(key, None)

    return _load_tapo_module("main")


def test_health_public_no_token(monkeypatch):
    """/health must be reachable without an Authorization header."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    mod = _load_main_fresh()
    client = TestClient(mod.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_private_endpoint_reachable_in_dev_mode(monkeypatch):
    """When HEMS_INTERNAL_TOKEN is unset, private endpoints skip auth (dev mode)."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    mod = _load_main_fresh()
    client = TestClient(mod.app)
    response = client.get("/api/devices")
    assert response.status_code == 200


def test_private_endpoint_requires_auth_when_token_set_no_header(monkeypatch):
    """With HEMS_INTERNAL_TOKEN configured, missing Authorization header returns 401."""
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    mod = _load_main_fresh()
    client = TestClient(mod.app)
    response = client.get("/api/devices")
    assert response.status_code == 401


def test_private_endpoint_requires_auth_when_token_set_wrong_bearer(monkeypatch):
    """With HEMS_INTERNAL_TOKEN configured, an invalid bearer token returns 401."""
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    mod = _load_main_fresh()
    client = TestClient(mod.app)
    response = client.get("/api/devices", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_private_endpoint_allows_valid_bearer(monkeypatch):
    """With HEMS_INTERNAL_TOKEN configured, the correct bearer token is accepted."""
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    mod = _load_main_fresh()
    client = TestClient(mod.app)

    # Mock device_mapper so the endpoint returns 200 rather than 503.
    mod.device_mapper = MagicMock()
    mod.device_mapper.all_refs.return_value = []

    response = client.get("/api/devices", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.json() == {"devices": []}
