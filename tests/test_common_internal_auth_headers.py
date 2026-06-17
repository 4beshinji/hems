"""
Tests for hems_common.auth.internal_auth_headers — shared Bearer helper.
"""

import sys
from pathlib import Path

_common = Path(__file__).resolve().parent.parent / "services" / "_common"
if str(_common) not in sys.path:
    sys.path.insert(0, str(_common))

from hems_common.auth import internal_auth_headers


def test_returns_bearer_header_when_token_set(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret-token")
    assert internal_auth_headers() == {"Authorization": "Bearer secret-token"}


def test_returns_empty_dict_when_token_unset(monkeypatch):
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    assert internal_auth_headers() == {}


def test_uses_custom_env_var(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOKEN", "custom-value")
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    assert internal_auth_headers(env_var="CUSTOM_TOKEN") == {"Authorization": "Bearer custom-value"}


def test_empty_token_returns_empty_dict(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "")
    assert internal_auth_headers() == {}
