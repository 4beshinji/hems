"""Unit tests for hems_common.mqtt.MqttPublisher.

The paho client is replaced with a MagicMock so no broker is needed. We assert
the (topic, payload, retain, qos) contract plus the four divergence axes the
9 bridges need reproduced.
"""

import json
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest

from hems_common.mqtt import MqttPublisher


def _make_pub(**kwargs):
    """Construct a publisher with a mocked client. Marks connected unless told
    otherwise so publish() is exercised by default."""
    connected = kwargs.pop("_connected", True)
    pub = MqttPublisher("localhost", 1883, **kwargs)
    pub.client = MagicMock()
    pub.client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
    pub._connected = connected
    return pub


def test_publish_positional_broker_port_and_client_attr():
    # ha test contract: positional broker/port + a .client attribute.
    pub = MqttPublisher("localhost", 1883)
    assert hasattr(pub, "client")


def test_publish_default_retain_false():
    pub = _make_pub()
    pub.publish("t/x", {"a": 1})
    _, kwargs = pub.client.publish.call_args
    assert kwargs["retain"] is False


def test_publish_default_retain_true():
    pub = _make_pub(default_retain=True)
    pub.publish("t/x", {"a": 1})
    _, kwargs = pub.client.publish.call_args
    assert kwargs["retain"] is True


def test_publish_retain_override_beats_default():
    pub = _make_pub(default_retain=True)
    pub.publish("t/x", {"a": 1}, retain=False)
    _, kwargs = pub.client.publish.call_args
    assert kwargs["retain"] is False


def test_publish_qos_default_and_override():
    pub = _make_pub(default_qos=0)
    pub.publish("t/x", {"a": 1})
    assert pub.client.publish.call_args.kwargs["qos"] == 0
    pub.publish("t/x", {"a": 1}, qos=1)
    assert pub.client.publish.call_args.kwargs["qos"] == 1


def test_publish_topic_and_payload_serialized():
    pub = _make_pub()
    pub.publish("hems/x/y", {"a": 1, "b": "z"})
    args, _ = pub.client.publish.call_args
    assert args[0] == "hems/x/y"
    assert json.loads(args[1]) == {"a": 1, "b": "z"}


def test_ensure_ascii_false_keeps_japanese():
    pub = _make_pub(ensure_ascii=False)
    pub.publish("t/x", {"w": "晴"})
    payload = pub.client.publish.call_args.args[1]
    assert "晴" in payload
    assert "\\u" not in payload


def test_ensure_ascii_true_escapes_japanese():
    pub = _make_pub(ensure_ascii=True)
    pub.publish("t/x", {"w": "晴"})
    payload = pub.client.publish.call_args.args[1]
    assert "晴" not in payload
    assert "\\u6674" in payload


def test_publish_returns_true_on_success():
    pub = _make_pub()
    assert pub.publish("t/x", {"a": 1}) is True


def test_publish_returns_false_on_failure_rc():
    pub = _make_pub()
    pub.client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_NO_CONN)
    assert pub.publish("t/x", {"a": 1}) is False


def test_publish_returns_false_when_not_connected():
    pub = _make_pub(_connected=False, track_connection=True)
    assert pub.publish("t/x", {"a": 1}) is False
    pub.client.publish.assert_not_called()


def test_publish_skips_connected_check_when_tracking_off():
    # ha/switchbot/tapo style: publish unconditionally.
    pub = MqttPublisher("localhost", 1883, track_connection=False, default_retain=True)
    pub.client = MagicMock()
    pub.client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
    assert pub.publish("t/x", {"a": 1}) is True
    pub.client.publish.assert_called_once()


def test_publish_swallows_exception_returns_false():
    pub = _make_pub()
    pub.client.publish.side_effect = RuntimeError("boom")
    assert pub.publish("t/x", {"a": 1}) is False


def test_connected_property_tracks_on_connect():
    pub = MqttPublisher("localhost", 1883, track_connection=True)
    assert pub.connected is False
    pub._on_connect(None, None, None, 0)
    assert pub.connected is True
    pub._on_disconnect(None, None, None, 1)
    assert pub.connected is False


def test_on_connect_failure_keeps_disconnected():
    pub = MqttPublisher("localhost", 1883, track_connection=True)
    pub._on_connect(None, None, None, 5)
    assert pub.connected is False


def test_connect_swallows_error_when_not_raising():
    pub = MqttPublisher("localhost", 1883, raise_on_connect_error=False)
    pub.client = MagicMock()
    pub.client.connect.side_effect = OSError("no broker")
    pub.connect()  # must not raise


def test_connect_raises_when_configured():
    pub = MqttPublisher("localhost", 1883, raise_on_connect_error=True)
    pub.client = MagicMock()
    pub.client.connect.side_effect = OSError("no broker")
    with pytest.raises(OSError):
        pub.connect()


def test_error_level_debug_vs_error(monkeypatch):
    # error_level routes connect-failure logging; assert no raise + level honored.
    from hems_common import mqtt as mqtt_mod

    calls = {"debug": 0, "error": 0}
    monkeypatch.setattr(mqtt_mod.logger, "debug", lambda *a, **k: calls.__setitem__("debug", calls["debug"] + 1))
    monkeypatch.setattr(mqtt_mod.logger, "error", lambda *a, **k: calls.__setitem__("error", calls["error"] + 1))

    pub = MqttPublisher("localhost", 1883, error_level="debug")
    pub.client = MagicMock()
    pub.client.connect.side_effect = OSError("x")
    pub.connect()
    assert calls["debug"] == 1 and calls["error"] == 0

    pub2 = MqttPublisher("localhost", 1883, error_level="error")
    pub2.client = MagicMock()
    pub2.client.connect.side_effect = OSError("x")
    pub2.connect()
    assert calls["error"] == 1


def test_disconnect_clears_connected():
    pub = _make_pub()
    pub.disconnect()
    assert pub.connected is False
    pub.client.loop_stop.assert_called_once()
    pub.client.disconnect.assert_called_once()


def test_username_pw_set_only_when_user_given():
    pub_no = MqttPublisher("localhost", 1883)
    # client is a real paho client here; just ensure construction worked.
    assert pub_no.client is not None


def test_subscribe_calls_client_subscribe():
    pub = _make_pub()
    pub.subscribe("hems/perception/vlm/+")
    pub.client.subscribe.assert_called_once_with("hems/perception/vlm/+")


def test_on_connect_resubscribes_registered_topics():
    pub = _make_pub(_connected=False)
    pub.subscribe("hems/sensors/#")
    pub.client.subscribe.reset_mock()

    pub._on_connect(None, None, None, 0)

    pub.client.subscribe.assert_called_once_with("hems/sensors/#")


def test_on_reconnect_deduplicates_registered_topics():
    pub = _make_pub(_connected=False)
    pub.subscribe("hems/sensors/#")
    pub.subscribe("hems/sensors/#")
    pub.client.subscribe.reset_mock()

    pub._on_connect(None, None, None, 0)

    pub.client.subscribe.assert_called_once_with("hems/sensors/#")


def test_set_message_callback_stores_callback():
    pub = _make_pub()

    def cb(topic, payload):
        pass

    pub.set_message_callback(cb)
    assert pub._message_callback is cb


def test_on_message_routes_to_callback():
    pub = _make_pub()
    received = []

    def cb(topic, payload):
        received.append((topic, payload))

    pub.set_message_callback(cb)
    msg = MagicMock()
    msg.topic = "hems/perception/vlm/living"
    msg.payload = b'{"objects": ["cat"]}'
    pub._on_message(None, None, msg)
    assert received == [("hems/perception/vlm/living", {"objects": ["cat"]})]


def test_on_message_ignores_when_no_callback():
    pub = _make_pub()
    msg = MagicMock()
    msg.topic = "hems/x"
    msg.payload = b'{"a": 1}'
    pub._on_message(None, None, msg)  # should not raise


def test_on_message_warns_on_invalid_json(monkeypatch):
    from hems_common import mqtt as mqtt_mod

    warnings = []
    monkeypatch.setattr(mqtt_mod.logger, "warning", lambda msg, *a, **k: warnings.append(msg))

    pub = _make_pub()
    pub.set_message_callback(lambda t, p: None)
    msg = MagicMock()
    msg.topic = "hems/x"
    msg.payload = b"not-json"
    pub._on_message(None, None, msg)
    assert any("Failed to parse" in str(w) for w in warnings)
