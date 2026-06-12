"""Minimal regression tests for the obsidian-bridge W3.2 migration.

Verifies that:
1. The bridge can be imported without errors (hems_common wiring is correct).
2. mqtt_pub.publish calls pass the correct topic/payload/retain/qos.
3. publish_bridge_status emits via hems/obsidian/bridge/status with retain=True.
4. config module-level MQTT constants are still exported (backward compat).
5. ensure_ascii=False: Japanese payloads are emitted as raw UTF-8.

Isolation: obsidian-bridge modules are loaded via importlib to avoid sys.modules
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

_OBSIDIAN_SRC = Path(__file__).resolve().parent.parent / "services" / "obsidian-bridge" / "src"


def _load_obsidian_module(name: str) -> ModuleType:
    """Load a module from obsidian-bridge/src by file path, bypassing sys.modules cache."""
    ns_key = f"obsidian_bridge.{name}"

    saved_config = sys.modules.get("config")
    obsidian_config_key = "obsidian_bridge.config"

    # Ensure obsidian-bridge config is loaded first
    if obsidian_config_key not in sys.modules:
        cfg_file = _OBSIDIAN_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(obsidian_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[obsidian_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[obsidian_config_key]

    _src_str = str(_OBSIDIAN_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _OBSIDIAN_SRC / f"{name}.py"
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
    cfg_mod = _load_obsidian_module("config")
    assert hasattr(cfg_mod, "MQTT_BROKER")
    assert hasattr(cfg_mod, "MQTT_PORT")
    assert hasattr(cfg_mod, "VAULT_PATH")


def test_import_vault_watcher():
    # watchdog is available in the test env (standard dep)
    m = _load_obsidian_module("vault_watcher")
    assert hasattr(m, "VaultWatcher")


def test_config_mqtt_defaults(monkeypatch):
    """config module exports the expected MQTT constant names (backward compat)."""
    # Clear cached module to re-exec with fresh env
    sys.modules.pop("obsidian_bridge.config", None)
    sys.modules.pop("config", None)
    cfg_mod = _load_obsidian_module("config")

    # Verify the module-level names exist and have the correct types
    assert isinstance(cfg_mod.MQTT_BROKER, str)
    assert isinstance(cfg_mod.MQTT_PORT, int)
    assert isinstance(cfg_mod.MQTT_USER, str)
    assert isinstance(cfg_mod.MQTT_PASS, str)


# ---------------------------------------------------------------------------
# MqttPublisher helper
# ---------------------------------------------------------------------------


def _make_obsidian_publisher():
    """Return a MqttPublisher configured as obsidian-bridge uses it."""
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


# ---------------------------------------------------------------------------
# Publish contract: topic / payload / retain / qos
# ---------------------------------------------------------------------------


def test_notes_changed_publish_topic_and_retain():
    """Note change events publish to hems/personal/notes/changed with retain=False."""
    mock_pub = _make_obsidian_publisher()
    payload = {
        "path": "HEMS/decisions/2026-06-12.md",
        "action": "modified",
        "title": "2026-06-12",
        "tags": ["decision"],
    }
    mock_pub.publish("hems/personal/notes/changed", payload)

    topic, payload_str, retain, qos = _last_publish_args(mock_pub)
    assert topic == "hems/personal/notes/changed"
    parsed = json.loads(payload_str)
    assert parsed["path"] == "HEMS/decisions/2026-06-12.md"
    assert parsed["action"] == "modified"
    assert retain is False
    assert qos == 0


def test_bridge_status_topic_and_retain():
    """publish_bridge_status publishes to hems/obsidian/bridge/status with retain=True."""
    from hems_common import publish_bridge_status

    mock_pub = _make_obsidian_publisher()
    publish_bridge_status(mock_pub, "obsidian")

    topic, payload_str, retain, _qos = _last_publish_args(mock_pub)
    assert topic == "hems/obsidian/bridge/status"
    parsed = json.loads(payload_str)
    assert parsed["connected"] is True
    assert retain is True


def test_publish_ensure_ascii_false():
    """Payloads with Japanese strings are emitted as raw UTF-8 (not \\uXXXX)."""
    mock_pub = _make_obsidian_publisher()
    mock_pub.publish("hems/personal/notes/changed", {"title": "決定ログ"})
    _, payload_str, _, _ = _last_publish_args(mock_pub)
    assert "決定ログ" in payload_str
    assert "\\u" not in payload_str


def test_track_connection_false_publishes_unconditionally():
    """With track_connection=False, publish succeeds even when _connected=False."""
    mock_pub = _make_obsidian_publisher()
    assert mock_pub._connected is False
    result = mock_pub.publish("hems/personal/notes/stats", {"total_notes": 42})
    assert result is True
    assert mock_pub.client.publish.called
