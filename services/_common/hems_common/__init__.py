"""hems_common — shared bridge infrastructure for HEMS services.

Provides a unified MQTT publisher, a bridge lifespan helper, config loaders,
internal-token auth, and a bridge-status publisher so the 9 bridges can drop
their per-service copies (W3.2).

Import as::

    from hems_common.mqtt import MqttPublisher
    from hems_common.lifespan import bridge_lifespan
    from hems_common.config import MqttConfig, load_mqtt_config, load_json_env
    from hems_common.auth import verify_internal_token
    from hems_common.status import publish_bridge_status
"""

from hems_common.auth import verify_internal_token
from hems_common.biometric import (
    BiometricAggregation,
    BiometricMetrics,
    BiometricObservationIn,
    canonical_observation_payload,
)
from hems_common.config import MqttConfig, load_json_env, load_mqtt_config
from hems_common.lifespan import bridge_lifespan
from hems_common.mqtt import MqttPublisher
from hems_common.status import publish_bridge_status

__all__ = [
    "BiometricAggregation",
    "BiometricMetrics",
    "BiometricObservationIn",
    "MqttConfig",
    "MqttPublisher",
    "bridge_lifespan",
    "canonical_observation_payload",
    "load_json_env",
    "load_mqtt_config",
    "publish_bridge_status",
    "verify_internal_token",
]
