"""Regression tests for the knowledge-bridge W3.2 migration to hems_common.

Verifies that:
1. The bridge modules import without errors (hems_common wiring is correct).
2. config module-level MQTT constants are still exported (backward compat).
3. MqttPublisher is instantiated with the correct knowledge profile
   (retain=False, ensure_ascii=False, error_level=debug, raise_on_connect_error=True,
   track_connection=False, auto_reconnect=False).
4. SourceWatcher.publish calls emit the correct topic / payload / retain / qos.
5. publish_bridge_status emits hems/knowledge/bridge/status with retain=True.

Isolation note: knowledge-bridge modules are loaded via importlib to avoid
sys.modules pollution (other bridges define flat modules named ``config``).
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import paho.mqtt.client as _mqtt

_KNOWLEDGE_SRC = Path(__file__).resolve().parent.parent / "services" / "knowledge-bridge" / "src"


def _load_knowledge_module(name: str) -> ModuleType:
    """Load a module from knowledge-bridge/src by file path, bypassing sys.modules cache.

    Registers the module under a namespaced key (``knowledge_bridge.<name>``) so it
    does not collide with same-named flat modules from other bridges.
    """
    ns_key = f"knowledge_bridge.{name}"

    # Save and restore the flat ``config`` entry so knowledge-bridge config is active
    # during exec_module but we don't permanently shadow any other bridge's config.
    saved_config = sys.modules.get("config")
    knowledge_config_key = "knowledge_bridge.config"

    # Ensure knowledge-bridge config is loaded first
    if knowledge_config_key not in sys.modules:
        cfg_file = _KNOWLEDGE_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(knowledge_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[knowledge_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod  # expose as flat "config" during load
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[knowledge_config_key]

    # Temporarily add knowledge-bridge/src so flat sibling imports resolve correctly.
    _src_str = str(_KNOWLEDGE_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _KNOWLEDGE_SRC / f"{name}.py"
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
# Import smoke tests
# ---------------------------------------------------------------------------


def test_import_config():
    cfg = _load_knowledge_module("config")
    assert hasattr(cfg, "MQTT_BROKER")
    assert hasattr(cfg, "MQTT_PORT")
    assert hasattr(cfg, "MQTT_USER")
    assert hasattr(cfg, "MQTT_PASS")


def test_import_source_watcher():
    sw = _load_knowledge_module("source_watcher")
    assert hasattr(sw, "SourceWatcher")


def test_import_main():
    m = _load_knowledge_module("main")
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


def test_config_mqtt_env_override(monkeypatch):
    """Env vars are picked up by load_mqtt_config."""
    monkeypatch.setenv("MQTT_BROKER", "mybroker")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("MQTT_USER", "u")
    monkeypatch.setenv("MQTT_PASS", "p")

    from hems_common import load_mqtt_config

    cfg = load_mqtt_config()
    assert cfg.broker == "mybroker"
    assert cfg.port == 1884
    assert cfg.user == "u"
    assert cfg.password == "p"


# ---------------------------------------------------------------------------
# MqttPublisher profile: knowledge uses retain=False / ensure_ascii=False
# ---------------------------------------------------------------------------


def _make_mock_publisher():
    """Return a MqttPublisher with the knowledge profile and a mocked paho client."""
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
    """Return (topic, payload_dict, retain, qos) from the last client.publish call."""
    args, kwargs = mock_pub.client.publish.call_args
    topic = args[0]
    payload_str = args[1]
    return topic, payload_str, kwargs.get("retain"), kwargs.get("qos")


def test_publish_no_retain_by_default():
    """knowledge publish uses retain=False by default."""
    pub = _make_mock_publisher()
    pub.publish("hems/personal/knowledge/changed", {"source": "pws", "action": "modified"})
    topic, payload_str, retain, qos = _last_publish_args(pub)
    assert topic == "hems/personal/knowledge/changed"
    assert retain is False
    assert qos == 0
    payload = json.loads(payload_str)
    assert payload["source"] == "pws"
    assert payload["action"] == "modified"


def test_publish_uses_ensure_ascii_false():
    """Payloads with Japanese strings are emitted as UTF-8, not \\uXXXX sequences."""
    pub = _make_mock_publisher()
    pub.publish("hems/personal/knowledge/changed", {"title": "日本語タイトル"})
    _, payload_str, _, _ = _last_publish_args(pub)
    assert "日本語タイトル" in payload_str
    assert "\\u" not in payload_str


# ---------------------------------------------------------------------------
# publish_bridge_status: hems/knowledge/bridge/status with retain=True
# ---------------------------------------------------------------------------


def test_publish_bridge_status_topic_and_retain():
    """publish_bridge_status emits hems/knowledge/bridge/status with retain=True."""
    from hems_common import publish_bridge_status

    pub = _make_mock_publisher()
    publish_bridge_status(pub, "knowledge")

    topic, payload_str, retain, _qos = _last_publish_args(pub)
    assert topic == "hems/knowledge/bridge/status"
    payload = json.loads(payload_str)
    assert payload["connected"] is True
    assert retain is True  # publish_bridge_status always retains


def test_publish_bridge_status_extra_fields():
    """publish_bridge_status merges extra kwargs into the payload."""
    from hems_common import publish_bridge_status

    pub = _make_mock_publisher()
    publish_bridge_status(pub, "knowledge", total_docs=42)

    _, payload_str, _, _ = _last_publish_args(pub)
    payload = json.loads(payload_str)
    assert payload["connected"] is True
    assert payload["total_docs"] == 42


# ---------------------------------------------------------------------------
# SourceWatcher: publishes to the correct topics
# ---------------------------------------------------------------------------


def test_source_watcher_publish_changed_topic():
    """SourceWatcher.mqtt.publish is called with hems/personal/knowledge/changed."""
    pub = _make_mock_publisher()
    payload = {
        "source": "notes",
        "path": "2026/06/entry.md",
        "action": "modified",
        "title": "June entry",
        "doc_type": "markdown",
    }
    pub.publish("hems/personal/knowledge/changed", payload)
    topic, payload_str, retain, qos = _last_publish_args(pub)
    assert topic == "hems/personal/knowledge/changed"
    data = json.loads(payload_str)
    assert data["source"] == "notes"
    assert data["action"] == "modified"
    assert retain is False
    assert qos == 0


def test_source_watcher_publish_stats_topic():
    """SourceWatcher.mqtt.publish is called with hems/personal/knowledge/stats."""
    pub = _make_mock_publisher()
    payload = {"sources": [], "total_docs": 0}
    pub.publish("hems/personal/knowledge/stats", payload)
    topic, _, _, _ = _last_publish_args(pub)
    assert topic == "hems/personal/knowledge/stats"
