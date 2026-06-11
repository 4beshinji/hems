"""
device_id_validator -- shared validation for device_id and vendor_ref.

Pattern: ^[\\w.\\-]+$  (alphanumeric, underscore, dot, hyphen only)
Max length: 128 characters
Empty string: rejected

Used by:
  - services/brain/src/device_dispatcher.py  (dispatch-time guard before MQTT/HTTP topic assembly)
  - services/backend/schemas.py              (Pydantic validator on DeviceBase / DeviceHeartbeat)
"""

import re

_DEVICE_ID_RE = re.compile(r"^[\w.\-]+$")
DEVICE_ID_MAX_LEN = 128


def is_valid_device_ref(value: str) -> bool:
    """Return True iff *value* is a safe device_id / vendor_ref.

    Rejects empty strings, strings longer than DEVICE_ID_MAX_LEN, and any
    string containing characters outside [A-Za-z0-9_.-].
    """
    if not value:
        return False
    if len(value) > DEVICE_ID_MAX_LEN:
        return False
    return bool(_DEVICE_ID_RE.match(value))


def validate_device_ref(field_name: str, value: str) -> str:
    """Validate and return *value*; raise ValueError on invalid input.

    Intended for use inside Pydantic field validators.
    """
    if not is_valid_device_ref(value):
        raise ValueError(f"{field_name} must match ^[\\w.\\-]+$ and be ≤{DEVICE_ID_MAX_LEN} chars; got {value!r}")
    return value
