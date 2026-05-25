"""
Tests for the backend shared-key gate (auth.verify_api_key).

Open (no-op) when BACKEND_API_KEY is unset so zero-config LAN deployments keep
working; enforced with a constant-time Bearer comparison when the key is set.
"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

_backend = Path(__file__).resolve().parent.parent / "services" / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

import auth


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_open_when_key_unset(monkeypatch):
    monkeypatch.setattr(auth, "BACKEND_API_KEY", "")
    assert await auth.verify_api_key(None) is None
    # A stray header is ignored while the gate is open.
    assert await auth.verify_api_key(_creds("anything")) is None


async def test_missing_credentials_rejected_when_key_set(monkeypatch):
    monkeypatch.setattr(auth, "BACKEND_API_KEY", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await auth.verify_api_key(None)
    assert exc.value.status_code == 401


async def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(auth, "BACKEND_API_KEY", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await auth.verify_api_key(_creds("wrong"))
    assert exc.value.status_code == 401


async def test_correct_key_accepted(monkeypatch):
    monkeypatch.setattr(auth, "BACKEND_API_KEY", "s3cret")
    assert await auth.verify_api_key(_creds("s3cret")) is None
