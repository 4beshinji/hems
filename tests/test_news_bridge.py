"""Minimal regression tests for the news-bridge W3.2 migration.

Verifies that:
1. The bridge can be imported without errors (hems_common wiring is correct).
2. News publish calls pass the correct (topic, payload fields, retain=False, qos=0).
3. publish_bridge_status emits → retain=True, topic=hems/news/bridge/status,
   with the expected extra fields.
4. config module-level MQTT constants are still exported (backward compat).
5. ensure_ascii=False: Japanese strings are emitted as UTF-8, not \\uXXXX.

Isolation note: news-bridge modules are loaded via importlib to avoid
sys.modules pollution from other bridge test files (gas-bridge also defines
flat modules named ``config``). Same pattern as test_weather_bridge.py.
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from paho.mqtt.client import MQTT_ERR_SUCCESS

_NEWS_SRC = Path(__file__).resolve().parent.parent / "services" / "news-bridge" / "src"


def _load_news_module(name: str) -> ModuleType:
    """Load a module from news-bridge/src by file path, bypassing sys.modules cache."""
    ns_key = f"news_bridge.{name}"

    saved_config = sys.modules.get("config")
    news_config_key = "news_bridge.config"

    # Ensure news-bridge config is loaded first
    if news_config_key not in sys.modules:
        cfg_file = _NEWS_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(news_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[news_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[news_config_key]

    _src_str = str(_NEWS_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _NEWS_SRC / f"{name}.py"
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
    cfg = _load_news_module("config")
    assert hasattr(cfg, "MQTT_BROKER")
    assert hasattr(cfg, "MQTT_PORT")
    assert hasattr(cfg, "MQTT_USER")
    assert hasattr(cfg, "MQTT_PASS")


def test_import_main():
    m = _load_news_module("main")
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
# MqttPublisher profile for news: retain=False / qos=0 / ensure_ascii=False
# ---------------------------------------------------------------------------


def _make_mock_publisher():
    """Return a MqttPublisher configured for the news profile with a mocked paho client."""
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
    pub.client.publish.return_value = MagicMock(rc=MQTT_ERR_SUCCESS)
    return pub


def _last_publish_args(mock_pub):
    """Return (topic, json_payload_str, retain, qos) from the last client.publish call."""
    args, kwargs = mock_pub.client.publish.call_args
    topic = args[0]
    payload_str = args[1]
    return topic, payload_str, kwargs.get("retain"), kwargs.get("qos")


def test_news_daily_publish_topic_and_no_retain():
    """hems/news/daily is published without retain."""
    mock_pub = _make_mock_publisher()
    payload = {"summary": "テスト", "chunks": [], "article_count": 3, "timestamp": 0.0}
    mock_pub.publish("hems/news/daily", payload)

    topic, payload_str, retain, qos = _last_publish_args(mock_pub)
    assert topic == "hems/news/daily"
    data = json.loads(payload_str)
    assert data["article_count"] == 3
    assert retain is False
    assert qos == 0


def test_news_urgent_publish_topic_and_no_retain():
    """hems/news/urgent is published without retain."""
    mock_pub = _make_mock_publisher()
    payload = {"title": "速報", "summary": "内容", "score": 0.9, "source": "nhk", "url": "http://x", "timestamp": 0.0}
    mock_pub.publish("hems/news/urgent", payload)

    topic, _payload_str, retain, qos = _last_publish_args(mock_pub)
    assert topic == "hems/news/urgent"
    assert retain is False
    assert qos == 0


def test_bridge_status_topic_and_retain():
    """publish_bridge_status emits hems/news/bridge/status with retain=True."""
    from hems_common import publish_bridge_status

    mock_pub = _make_mock_publisher()
    publish_bridge_status(mock_pub, "news", last_fetch=123.0, articles_count=5)

    topic, payload_str, retain, _qos = _last_publish_args(mock_pub)
    assert topic == "hems/news/bridge/status"
    data = json.loads(payload_str)
    assert data["connected"] is True
    assert data["last_fetch"] == 123.0
    assert data["articles_count"] == 5
    assert retain is True


def test_publish_uses_ensure_ascii_false():
    """Payloads with Japanese strings are emitted as UTF-8, not \\uXXXX sequences."""
    mock_pub = _make_mock_publisher()
    mock_pub.publish("hems/news/daily", {"summary": "速報ニュース"})
    _, payload_str, _, _ = _last_publish_args(mock_pub)
    assert "速報ニュース" in payload_str
    assert "\\u" not in payload_str
