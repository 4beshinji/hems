"""Unit tests for hems_common.auth.verify_internal_token."""

import pytest
from fastapi import HTTPException

from hems_common.auth import verify_internal_token


def test_dev_skip_when_no_token_configured(monkeypatch):
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    # No env, no explicit token -> skip (returns None, no raise).
    assert verify_internal_token("Bearer whatever") is None
    assert verify_internal_token(None) is None


def test_dev_skip_when_token_empty_string():
    assert verify_internal_token("Bearer x", token="") is None


def test_valid_token_passes():
    assert verify_internal_token("Bearer secret", token="secret") is None


def test_valid_token_without_bearer_prefix():
    # removeprefix is a no-op if "Bearer " missing; bare token still compared.
    assert verify_internal_token("secret", token="secret") is None


def test_wrong_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        verify_internal_token("Bearer nope", token="secret")
    assert exc.value.status_code == 401


def test_missing_header_raises_when_token_set():
    with pytest.raises(HTTPException) as exc:
        verify_internal_token(None, token="secret")
    assert exc.value.status_code == 401


def test_reads_from_env_var(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "envtok")
    assert verify_internal_token("Bearer envtok") is None
    with pytest.raises(HTTPException):
        verify_internal_token("Bearer wrong")


def test_custom_env_var(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "abc")
    assert verify_internal_token("Bearer abc", env_var="MY_TOKEN") is None
