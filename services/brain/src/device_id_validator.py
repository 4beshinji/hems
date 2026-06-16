"""device_id_validator -- shared validation for device_id and vendor_ref.

This module is a thin wrapper around :mod:`hems_common.validation` so that
existing brain imports keep working. The canonical implementation lives in
``services/_common/hems_common/validation.py`` and is shared with the backend.
"""

from hems_common.validation import (
    DEVICE_REF_PATTERN,
    MAX_DEVICE_REF_LEN,
)
from hems_common.validation import (
    is_valid_device_ref as _common_is_valid_device_ref,
)
from hems_common.validation import (
    validate_device_ref as _common_validate_device_ref,
)

__all__ = [
    "DEVICE_REF_PATTERN",
    "MAX_DEVICE_REF_LEN",
    "is_valid_device_ref",
    "validate_device_ref",
]

# Re-export constants for backward compatibility.
DEVICE_ID_MAX_LEN = MAX_DEVICE_REF_LEN


def is_valid_device_ref(value: str) -> bool:
    """Return True iff *value* is a safe device_id / vendor_ref.

    Rejects empty strings, strings longer than ``MAX_DEVICE_REF_LEN``, any
    string containing characters outside ``[A-Za-z0-9_.-]``, and any
    dot-separated component that is empty (consecutive, leading, or trailing
    dots).
    """
    return _common_is_valid_device_ref(value)


def validate_device_ref(field_name: str, value: str) -> str:
    """Validate and return *value*; raise :exc:`ValueError` on invalid input.

    Intended for use inside Pydantic field validators. The argument order
    ``(field_name, value)`` is preserved for backward compatibility with
    existing brain code.
    """
    return _common_validate_device_ref(value, field_name)
