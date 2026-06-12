"""Unit tests for hems_common.config (MqttConfig, load_mqtt_config, load_json_env)."""

from hems_common.config import MqttConfig, load_json_env, load_mqtt_config


def test_mqtt_config_defaults():
    cfg = MqttConfig()
    assert cfg.broker == "mosquitto"
    assert cfg.port == 1883
    assert cfg.user == ""
    assert cfg.password == ""


def test_load_mqtt_config_defaults(monkeypatch):
    for k in ("MQTT_BROKER", "MQTT_PORT", "MQTT_USER", "MQTT_PASS"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_mqtt_config()
    assert cfg == MqttConfig("mosquitto", 1883, "", "")


def test_load_mqtt_config_from_env(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER", "broker.local")
    monkeypatch.setenv("MQTT_PORT", "1893")
    monkeypatch.setenv("MQTT_USER", "u")
    monkeypatch.setenv("MQTT_PASS", "p")
    cfg = load_mqtt_config()
    assert cfg == MqttConfig("broker.local", 1893, "u", "p")


def test_load_mqtt_config_default_user(monkeypatch):
    monkeypatch.delenv("MQTT_USER", raising=False)
    cfg = load_mqtt_config(default_user="hems-tapo-bridge")
    assert cfg.user == "hems-tapo-bridge"


def test_load_json_env_valid(monkeypatch):
    monkeypatch.setenv("DEVS", '{"a": "1.2.3.4"}')
    assert load_json_env("DEVS") == {"a": "1.2.3.4"}


def test_load_json_env_missing_uses_default(monkeypatch):
    monkeypatch.delenv("DEVS", raising=False)
    assert load_json_env("DEVS") == {}


def test_load_json_env_blank_returns_empty(monkeypatch):
    monkeypatch.setenv("DEVS", "   ")
    assert load_json_env("DEVS") == {}


def test_load_json_env_invalid_returns_empty(monkeypatch):
    monkeypatch.setenv("DEVS", "{not json")
    assert load_json_env("DEVS") == {}
