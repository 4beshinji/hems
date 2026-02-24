"""
HEMS Backend — API Key authentication.

Single-user home system: simple Bearer token auth via HEMS_API_KEY env var.
JWT would be over-engineered for a private LAN device.

Usage:
  Set HEMS_API_KEY in environment (required).
  All API requests must include:
    Authorization: Bearer <HEMS_API_KEY>

Internal services (brain → backend) use the same key.
The frontend reads the key from the VITE_API_KEY build var or runtime config.
"""
import os
import secrets
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_API_KEY = os.getenv("HEMS_API_KEY", "")
_bearer_scheme = HTTPBearer(auto_error=False)

if not _API_KEY:
    import logging
    logging.getLogger(__name__).warning(
        "HEMS_API_KEY is not set — ALL API requests will be REJECTED. "
        "Set this environment variable to enable API access."
    )


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> str:
    """FastAPI dependency: verify Bearer token matches HEMS_API_KEY.

    Raises 401 if token is missing or incorrect.
    Returns the token on success (useful for logging).
    """
    if not _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured (HEMS_API_KEY not set)",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, _API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
