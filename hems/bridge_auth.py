"""
Shared bridge authentication — reused by all HEMS bridge services.

All bridge REST endpoints require Bearer token auth using the same
HEMS_API_KEY used by the backend. Health endpoints are excluded.
"""
import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

_API_KEY = os.getenv("HEMS_API_KEY", "")
_bearer_scheme = HTTPBearer(auto_error=False)

if not _API_KEY:
    logger.warning(
        "HEMS_API_KEY is not set — bridge API requests will be REJECTED. "
        "Set this environment variable to enable API access."
    )


def verify_bridge_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> str:
    """FastAPI dependency: verify Bearer token matches HEMS_API_KEY."""
    if not _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bridge authentication not configured (HEMS_API_KEY not set)",
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
