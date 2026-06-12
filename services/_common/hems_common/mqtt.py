"""Unified MQTT publisher for HEMS bridges.

This single class subsumes the 9 per-bridge ``MQTTPublisher`` copies. The four
axes of divergence (retain default, error policy, connection tracking +
auto-reconnect, ensure_ascii) are all expressed as constructor knobs, with
per-call overrides for ``retain``/``qos`` on ``publish``.

Behaviour matrix (how each legacy bridge maps onto this class):

* ha / switchbot / tapo:
    ``MqttPublisher(..., default_retain=True, error_level="error")``
* gas / obsidian / weather:
    ``MqttPublisher(..., default_retain=False, error_level="debug",
                    raise_on_connect_error=True)``
* news / knowledge:
    same as above (ensure_ascii=False is the new default, matching their
    legacy explicit ``ensure_ascii=False``)
* biometric:
    ``MqttPublisher(...)`` (defaults: track_connection=True,
    auto_reconnect=True) and ``publish(topic, data, retain=...)``

Compatibility contracts preserved for the migration:

* ``broker, port`` are positional (ha's ``TestMQTTPublisher.test_publish``).
* ``self.client`` holds the paho client (asserted by ha test).
* ``connected`` property + ``publish() -> bool`` (biometric send queue).
"""

import json

import paho.mqtt.client as mqtt
from loguru import logger


class MqttPublisher:
    """Publishes structured JSON dicts to MQTT topics.

    All behavioural variation between the legacy bridges is captured here so a
    single instance can reproduce any of them.
    """

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        user: str = "",
        password: str = "",
        *,
        client_id: str = "",
        default_retain: bool = False,
        default_qos: int = 0,
        ensure_ascii: bool = False,
        error_level: str = "error",
        raise_on_connect_error: bool = False,
        track_connection: bool = True,
        auto_reconnect: bool = True,
    ):
        self._broker = broker
        self._port = port
        self._default_retain = default_retain
        self._default_qos = default_qos
        self._ensure_ascii = ensure_ascii
        self._error_level = error_level
        self._raise_on_connect_error = raise_on_connect_error
        self._track_connection = track_connection
        self._connected = False

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if user:
            self.client.username_pw_set(user, password)
        if track_connection:
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
        if auto_reconnect:
            self.client.reconnect_delay_set(min_delay=1, max_delay=60)

    # -- connection tracking -------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the broker connection is currently established.

        When ``track_connection`` is disabled this is always ``False`` (no
        callbacks update it); such bridges should not rely on it.
        """
        return self._connected

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info(f"MQTT connected to {self._broker}:{self._port}")
        else:
            self._connected = False
            logger.warning(f"MQTT connect failed with rc={rc}")

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}), auto-reconnecting...")

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        """Connect to the broker and start the network loop.

        On failure, behaviour depends on ``raise_on_connect_error``: when
        True the exception propagates (gas/obsidian/weather/news/knowledge
        legacy behaviour); when False it is logged and swallowed
        (ha/switchbot/tapo legacy behaviour).
        """
        try:
            self.client.connect(self._broker, self._port, 60)
            self.client.loop_start()
            logger.info(f"MQTT connected to {self._broker}:{self._port}")
        except Exception as e:
            self._log_error(f"MQTT connection failed: {e}")
            if self._raise_on_connect_error:
                raise

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        self._connected = False

    # -- publish -------------------------------------------------------------

    def publish(
        self,
        topic: str,
        payload: dict,
        *,
        retain: bool | None = None,
        qos: int | None = None,
    ) -> bool:
        """Publish a JSON dict to ``topic``. Returns True on success.

        ``retain``/``qos`` fall back to the constructor defaults when None.
        When connection tracking is active and the broker is not connected,
        the publish is skipped and ``False`` returned (biometric send-queue
        contract).
        """
        if self._track_connection and not self._connected:
            return False

        retain = self._default_retain if retain is None else retain
        qos = self._default_qos if qos is None else qos
        try:
            data = json.dumps(payload, ensure_ascii=self._ensure_ascii)
            result = self.client.publish(topic, data, qos=qos, retain=retain)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            self._log_error(f"MQTT publish error on {topic}: {e}")
            return False

    # -- helpers -------------------------------------------------------------

    def _log_error(self, msg: str) -> None:
        if self._error_level == "debug":
            logger.debug(msg)
        else:
            logger.error(msg)
