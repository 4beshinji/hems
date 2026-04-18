"""
HEMS Backend — authentication.

- :func:`verify_api_key` — no-op (LAN-trusted, no API key required).
- :func:`verify_mobile_device` — per-device key stored hashed in the
  ``mobile_devices`` table; used by endpoints under ``/mobile/*``
  (except ``/mobile/register`` which is gated by the admin key).

Device keys are high-entropy random secrets (>= 32 bytes hex), so SHA-256
digest storage is sufficient.
"""

import hashlib
import os
import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db

_bearer_scheme = HTTPBearer(auto_error=False)

_DEVICE_KEY_BYTES = int(os.getenv("MOBILE_DEVICE_KEY_BYTES", "32"))
_HMAC_SECRET_BYTES = int(os.getenv("MOBILE_HMAC_SECRET_BYTES", "32"))


async def verify_api_key():
    return None


# --- Mobile device keys --------------------------------------------------


def hash_device_key(device_key: str) -> str:
    """Return the SHA-256 hex digest used as the lookup key in ``mobile_devices.api_key_hash``."""
    return hashlib.sha256(device_key.encode("utf-8")).hexdigest()


def generate_device_credentials() -> tuple[str, str, str]:
    """Create (device_key_plaintext, api_key_hash, hmac_secret).

    The plaintext key is returned exactly once to the caller (embedded in the
    registration QR) and MUST NOT be persisted.
    """
    device_key = secrets.token_hex(_DEVICE_KEY_BYTES)
    hmac_secret = secrets.token_hex(_HMAC_SECRET_BYTES)
    return device_key, hash_device_key(device_key), hmac_secret


async def verify_mobile_device(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency: resolve a registered :class:`models.MobileDevice`.

    Looks the Bearer token's hashed form up in the ``mobile_devices`` table.
    Returns the ORM row on success; raises 401 when missing, unknown, or disabled.
    """
    import models  # local import avoids circular import at module load

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key_hash = hash_device_key(credentials.credentials)
    result = await db.execute(select(models.MobileDevice).where(models.MobileDevice.api_key_hash == key_hash))
    device = result.scalars().first()
    if device is None or not device.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled device key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return device
