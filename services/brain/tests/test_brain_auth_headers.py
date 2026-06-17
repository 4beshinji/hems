"""
Tests for brain_constants.brain_auth_headers — brain-side internal Bearer helper.
"""

from brain_constants import brain_auth_headers


def test_returns_bearer_header_when_token_set(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret-token")
    assert brain_auth_headers() == {"Authorization": "Bearer secret-token"}


def test_returns_empty_dict_when_token_unset(monkeypatch):
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    assert brain_auth_headers() == {}


def test_empty_token_returns_empty_dict(monkeypatch):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "")
    assert brain_auth_headers() == {}
