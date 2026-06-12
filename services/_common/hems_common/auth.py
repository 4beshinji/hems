"""Internal-token auth for HEMS HTTP endpoints.

Generalises stt-bridge's ``_check_auth`` (``services/stt/src/main.py``). Uses a
constant-time comparison and, when no token is configured, skips auth entirely
(dev mode). S3 (token across bridge HTTP routes) drops this into each REST
path.
"""

import hmac
import os

from fastapi import HTTPException


def verify_internal_token(
    authorization: str | None,
    *,
    token: str | None = None,
    env_var: str = "HEMS_INTERNAL_TOKEN",
) -> None:
    """Verify a ``Bearer`` token against the configured internal token.

    The expected token is ``token`` if given, otherwise read from ``env_var``.
    When the expected token is empty/unset, auth is skipped (dev mode). On
    mismatch, raises ``HTTPException(401)``. Comparison is constant-time.
    """
    expected = token if token is not None else os.getenv(env_var, "")
    if not expected:
        return
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
