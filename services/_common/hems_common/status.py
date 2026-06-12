"""Unified bridge-status publisher.

Publishes ``hems/<service>/bridge/status`` with a ``connected`` flag (retained)
so brain can read each bridge's liveness. W3.3 wires this into obsidian /
knowledge (currently not publishing) and aligns ha onto ``hems/ha/...``. W3.1
only defines the helper; nothing calls it yet.
"""

from hems_common.mqtt import MqttPublisher


def publish_bridge_status(
    mqtt: MqttPublisher,
    service: str,
    *,
    connected: bool = True,
    **extra,
) -> bool:
    """Publish a retained ``hems/<service>/bridge/status`` message.

    Extra keyword args are merged into the payload alongside ``connected``.
    Returns the underlying ``publish`` result.
    """
    return mqtt.publish(
        f"hems/{service}/bridge/status",
        {"connected": connected, **extra},
        retain=True,
    )
