"""Shared validation helpers for HEMS services.

This module is intentionally small and dependency-light so it can be imported
by both backend (FastAPI/Pydantic) and brain (aiohttp) without pulling in
service-specific code.
"""

import re

DEVICE_REF_PATTERN = re.compile(r"^[\w.\-]+$")
MAX_DEVICE_REF_LEN = 128


def is_valid_device_ref(value: str | None) -> bool:
    """Return True iff *value* is a safe device_id / vendor_ref.

    Rules:
      - non-empty string
      - <= :data:`MAX_DEVICE_REF_LEN` characters
      - characters limited to ``[A-Za-z0-9_.-]``
      - every dot-separated segment is non-empty (rejects leading/trailing
        dots and consecutive dots such as ``a..b``)
    """
    if not isinstance(value, str):
        return False
    if len(value) == 0 or len(value) > MAX_DEVICE_REF_LEN:
        return False
    if not DEVICE_REF_PATTERN.match(value):
        return False
    return all(value.split("."))


def validate_device_ref(value: str | None, field_name: str = "device_ref") -> str:
    """Validate *value* and return it; raise :exc:`ValueError` on invalid input.

    Intended for use in Pydantic field validators and router path-parameter
    checks. ``None`` is rejected; use :func:`is_valid_device_ref` directly when
    optional fields need a boolean result.
    """
    if not is_valid_device_ref(value):
        raise ValueError(
            f"{field_name} must match ^[\\w.\\-]+$ with non-empty dot segments "
            f"and <= {MAX_DEVICE_REF_LEN} chars; got {value!r}"
        )
    return value  # type: ignore[return-value]
