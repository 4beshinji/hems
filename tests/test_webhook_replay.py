"""
W1.3 — Webhook replay-protection tests.

Covers both surfaces:
  1. backend mobile state-webhook  (via FastAPI TestClient + hmac_util)
  2. biometric-bridge webhook       (via FastAPI TestClient)

Legend
------
new-form:   X-Timestamp + X-Nonce present, HMAC signs "<ts>:<nonce>:" + body
legacy:     X-Timestamp / X-Nonce absent,  HMAC signs raw body only
strict:     WEBHOOK_REPLAY_STRICT=true  → legacy requests rejected
non-strict: WEBHOOK_REPLAY_STRICT=false (default) → legacy accepted with WARNING
"""

import hashlib
import hmac as _hmac
import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module availability guards
# ---------------------------------------------------------------------------

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = [
    pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed"),
    pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed"),
]


# ===========================================================================
# Helpers — HMAC signing
# ===========================================================================


def _sign(secret: str, body: bytes, *, ts: str | None = None, nonce: str | None = None) -> str:
    """Compute X-HEMS-Signature for new or legacy protocol."""
    if ts is not None and nonce is not None:
        msg = f"{ts}:{nonce}:".encode() + body
    else:
        msg = body
    return "sha256=" + _hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _ts_now() -> str:
    return str(int(time.time()))


def _ts_expired() -> str:
    """A timestamp 10 minutes in the past — outside the ±5-min window."""
    return str(int(time.time()) - 700)


# ===========================================================================
# Backend mobile webhook fixture
# ===========================================================================

ADMIN_KEY = "test_admin_key_12345"


@pytest.fixture()
def mobile_client(monkeypatch, tmp_path):
    """TestClient wired to the backend mobile router with a fresh SQLite DB."""
    import asyncio

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    db_file = tmp_path / "replay_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("CHARACTER_VERSION", "test-char@v1")
    monkeypatch.delenv("WEBHOOK_REPLAY_STRICT", raising=False)

    for name in (
        "database",
        "models",
        "auth",
        "hmac_util",
        "routers",
        "routers.mobile",
    ):
        sys.modules.pop(name, None)

    from fastapi import FastAPI

    import database
    from routers import mobile

    app = FastAPI()
    app.include_router(mobile.admin_router)
    app.include_router(mobile.device_router)

    asyncio.new_event_loop().run_until_complete(_create_tables(database.engine, database.Base))

    return TestClient(app)


@pytest.fixture()
def mobile_client_strict(monkeypatch, tmp_path):
    """Same as mobile_client but WEBHOOK_REPLAY_STRICT=true."""
    import asyncio

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    db_file = tmp_path / "replay_strict_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("CHARACTER_VERSION", "test-char@v1")
    monkeypatch.setenv("WEBHOOK_REPLAY_STRICT", "true")

    for name in (
        "database",
        "models",
        "auth",
        "hmac_util",
        "routers",
        "routers.mobile",
    ):
        sys.modules.pop(name, None)

    from fastapi import FastAPI

    import database
    from routers import mobile

    app = FastAPI()
    app.include_router(mobile.admin_router)
    app.include_router(mobile.device_router)

    asyncio.new_event_loop().run_until_complete(_create_tables(database.engine, database.Base))

    return TestClient(app)


async def _create_tables(engine, base):
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)


def _register(client) -> dict:
    resp = client.post(
        "/mobile/register",
        json={"device_label": "replay-test-phone", "platform": "android"},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _webhook(client, reg: dict, body: bytes, extra_headers: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {reg['device_key']}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/mobile/state/webhook", content=body, headers=headers)


# ===========================================================================
# Backend — non-strict (default) mode
# ===========================================================================


class TestMobileWebhookNonStrict:
    """WEBHOOK_REPLAY_STRICT=false (default)."""

    def _body(self):
        return json.dumps({"ts": "2026-06-11T10:00:00+00:00"}).encode()

    def test_new_form_accepted(self, mobile_client):
        """Valid new-protocol request (timestamp + nonce + HMAC) is accepted."""
        reg = _register(mobile_client)
        body = self._body()
        ts = _ts_now()
        nonce = "unique-nonce-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        resp = _webhook(
            mobile_client,
            reg,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["received"] is True

    def test_replay_rejected_same_nonce(self, mobile_client):
        """Second request with same nonce is rejected even in non-strict mode."""
        reg = _register(mobile_client)
        body = self._body()
        ts = _ts_now()
        nonce = "replay-nonce-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        headers = {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce}

        resp1 = _webhook(mobile_client, reg, body, headers)
        assert resp1.status_code == 200

        # Same nonce — must be rejected.
        resp2 = _webhook(mobile_client, reg, body, headers)
        assert resp2.status_code == 401

    def test_expired_timestamp_rejected(self, mobile_client):
        """Requests with timestamp > 5 minutes old are rejected."""
        reg = _register(mobile_client)
        body = self._body()
        ts = _ts_expired()
        nonce = "expire-nonce-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        resp = _webhook(
            mobile_client,
            reg,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 401

    def test_legacy_request_accepted(self, mobile_client):
        """Legacy request (no timestamp/nonce) is accepted in non-strict mode."""
        reg = _register(mobile_client)
        body = self._body()
        sig = _sign(reg["hmac_secret"], body)  # body-only sig
        resp = _webhook(mobile_client, reg, body, {"X-HEMS-Signature": sig})
        assert resp.status_code == 200, resp.text

    def test_legacy_wrong_sig_rejected(self, mobile_client):
        """Legacy request with bad HMAC is still rejected."""
        reg = _register(mobile_client)
        body = self._body()
        resp = _webhook(mobile_client, reg, body, {"X-HEMS-Signature": "sha256=deadbeef"})
        assert resp.status_code == 401


# ===========================================================================
# Backend — strict mode
# ===========================================================================


class TestMobileWebhookStrict:
    """WEBHOOK_REPLAY_STRICT=true."""

    def _body(self):
        return json.dumps({"ts": "2026-06-11T10:00:00+00:00"}).encode()

    def test_new_form_accepted(self, mobile_client_strict):
        """Valid new-protocol request is accepted in strict mode."""
        reg = _register(mobile_client_strict)
        body = self._body()
        ts = _ts_now()
        nonce = "strict-nonce-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        resp = _webhook(
            mobile_client_strict,
            reg,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 200, resp.text

    def test_legacy_request_rejected_in_strict_mode(self, mobile_client_strict):
        """Legacy request (no timestamp/nonce) is rejected when strict=true."""
        reg = _register(mobile_client_strict)
        body = self._body()
        sig = _sign(reg["hmac_secret"], body)
        resp = _webhook(mobile_client_strict, reg, body, {"X-HEMS-Signature": sig})
        assert resp.status_code == 401

    def test_replay_rejected_same_nonce(self, mobile_client_strict):
        """Replay (same nonce) is rejected in strict mode."""
        reg = _register(mobile_client_strict)
        body = self._body()
        ts = _ts_now()
        nonce = "strict-replay-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        headers = {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce}

        r1 = _webhook(mobile_client_strict, reg, body, headers)
        assert r1.status_code == 200

        r2 = _webhook(mobile_client_strict, reg, body, headers)
        assert r2.status_code == 401

    def test_expired_timestamp_rejected(self, mobile_client_strict):
        reg = _register(mobile_client_strict)
        body = self._body()
        ts = _ts_expired()
        nonce = "strict-expire-001"
        sig = _sign(reg["hmac_secret"], body, ts=ts, nonce=nonce)
        resp = _webhook(
            mobile_client_strict,
            reg,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 401


# ===========================================================================
# Biometric bridge fixture + tests
# ===========================================================================

_BIOMETRIC_SECRET = "test_bio_secret_xyz"
_BIOMETRIC_PATH = Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src"


def _make_bio_client(monkeypatch, strict: bool):
    """Import biometric-bridge main and return a TestClient with mocked I/O.

    The bridge's auth logic lives entirely in _verify_webhook_signature, which
    only needs BIOMETRIC_WEBHOOK_SECRET, WEBHOOK_REPLAY_STRICT, and the
    _seen_nonces cache — no MQTT broker or DataProcessor required.

    We patch _mqtt_publish and the module-level processor/gadgetbridge objects
    so that successfully-authenticated webhook calls don't crash trying to
    reach real infrastructure.
    """
    biometric_path = str(_BIOMETRIC_PATH)
    while biometric_path in sys.path:
        sys.path.remove(biometric_path)
    sys.path.insert(0, biometric_path)

    monkeypatch.setenv("BIOMETRIC_WEBHOOK_SECRET", _BIOMETRIC_SECRET)
    if strict:
        monkeypatch.setenv("WEBHOOK_REPLAY_STRICT", "true")
    else:
        monkeypatch.delenv("WEBHOOK_REPLAY_STRICT", raising=False)

    # Evict cached modules so env vars take effect on re-import.
    for mod in list(sys.modules.keys()):
        if "biometric" in mod or mod in (
            "main",
            "config",
            "send_queue",
            "mqtt_publisher",
            "data_processor",
            "providers.gadgetbridge",
            "providers.huami",
            "providers.zepp",
        ):
            sys.modules.pop(mod, None)

    # Import under patches so module-level class instantiations don't fail.
    with (
        patch("hems_common.MqttPublisher"),
        patch("send_queue.SendQueue"),
        patch("providers.gadgetbridge.GadgetbridgeProvider"),
        patch("data_processor.DataProcessor"),
    ):
        alias = "biometric_bridge_webhook_main"
        spec = importlib.util.spec_from_file_location(alias, _BIOMETRIC_PATH / "main.py")
        bio_main = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[alias] = bio_main
        spec.loader.exec_module(bio_main)

    # Patch the module-level objects that the webhook handler uses after auth.
    from data_processor import BiometricReading

    fake_reading = BiometricReading(heart_rate=72)

    gb_mock = MagicMock()
    gb_mock.process_webhook.return_value = fake_reading
    monkeypatch.setattr(bio_main, "gadgetbridge", gb_mock)

    dp_mock = MagicMock()
    dp_mock.is_duplicate.return_value = False
    dp_mock.process.return_value = fake_reading
    dp_mock.compute_fatigue.return_value = {"score": 0}
    monkeypatch.setattr(bio_main, "processor", dp_mock)

    # Patch _mqtt_publish to a no-op so no broker or send-queue is needed.
    monkeypatch.setattr(bio_main, "_mqtt_publish", lambda *a, **kw: None)

    return TestClient(bio_main.app)


@pytest.fixture()
def bio_client(monkeypatch, tmp_path):
    """TestClient for the biometric-bridge FastAPI app (non-strict)."""
    return _make_bio_client(monkeypatch, strict=False)


@pytest.fixture()
def bio_client_strict(monkeypatch, tmp_path):
    """TestClient for the biometric-bridge app (strict mode)."""
    return _make_bio_client(monkeypatch, strict=True)


def _bio_post(client, body: bytes, extra_headers: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/api/biometric/webhook", content=body, headers=headers)


class TestBiometricWebhookNonStrict:
    """Biometric bridge — WEBHOOK_REPLAY_STRICT=false (default)."""

    def _body(self):
        return json.dumps({"heart_rate": 72}).encode()

    def test_new_form_accepted(self, bio_client):
        body = self._body()
        ts = _ts_now()
        nonce = "bio-nonce-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        resp = _bio_post(
            bio_client,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 200, resp.text

    def test_replay_rejected_same_nonce(self, bio_client):
        body = self._body()
        ts = _ts_now()
        nonce = "bio-replay-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        headers = {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce}

        r1 = _bio_post(bio_client, body, headers)
        assert r1.status_code == 200

        r2 = _bio_post(bio_client, body, headers)
        assert r2.status_code == 401

    def test_expired_timestamp_rejected(self, bio_client):
        body = self._body()
        ts = _ts_expired()
        nonce = "bio-expire-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        resp = _bio_post(
            bio_client,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 401

    def test_legacy_request_accepted(self, bio_client):
        body = self._body()
        sig = _sign(_BIOMETRIC_SECRET, body)
        resp = _bio_post(bio_client, body, {"X-HEMS-Signature": sig})
        assert resp.status_code == 200, resp.text

    def test_legacy_wrong_sig_rejected(self, bio_client):
        body = self._body()
        resp = _bio_post(bio_client, body, {"X-HEMS-Signature": "sha256=badhex"})
        assert resp.status_code == 401


class TestBiometricWebhookStrict:
    """Biometric bridge — WEBHOOK_REPLAY_STRICT=true."""

    def _body(self):
        return json.dumps({"heart_rate": 72}).encode()

    def test_new_form_accepted(self, bio_client_strict):
        body = self._body()
        ts = _ts_now()
        nonce = "bio-strict-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        resp = _bio_post(
            bio_client_strict,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 200, resp.text

    def test_legacy_rejected_in_strict(self, bio_client_strict):
        body = self._body()
        sig = _sign(_BIOMETRIC_SECRET, body)
        resp = _bio_post(bio_client_strict, body, {"X-HEMS-Signature": sig})
        assert resp.status_code == 401

    def test_replay_rejected(self, bio_client_strict):
        body = self._body()
        ts = _ts_now()
        nonce = "bio-strict-replay-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        headers = {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce}

        r1 = _bio_post(bio_client_strict, body, headers)
        assert r1.status_code == 200

        r2 = _bio_post(bio_client_strict, body, headers)
        assert r2.status_code == 401

    def test_expired_timestamp_rejected(self, bio_client_strict):
        body = self._body()
        ts = _ts_expired()
        nonce = "bio-strict-expire-001"
        sig = _sign(_BIOMETRIC_SECRET, body, ts=ts, nonce=nonce)
        resp = _bio_post(
            bio_client_strict,
            body,
            {"X-HEMS-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce},
        )
        assert resp.status_code == 401


# ===========================================================================
# Unit tests for hmac_util (no HTTP stack required)
# ===========================================================================


class TestHmacUtilReplay:
    """Direct tests of check_replay_headers and verify_signature_with_replay."""

    @pytest.fixture(autouse=True)
    def _clear_nonces(self):
        """Clear the nonce cache before each test for isolation."""
        backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        import hmac_util

        hmac_util._seen_nonces.clear()
        yield
        hmac_util._seen_nonces.clear()

    def test_check_replay_non_strict_no_headers(self):
        import hmac_util

        result = hmac_util.check_replay_headers(None, None, strict=False)
        assert result.ok is True
        assert result.legacy_fallback is True

    def test_check_replay_strict_no_headers(self):
        import hmac_util

        result = hmac_util.check_replay_headers(None, None, strict=True)
        assert result.ok is False

    def test_check_replay_valid(self):
        import hmac_util

        now = time.time()
        ts = str(int(now))
        result = hmac_util.check_replay_headers(ts, "nonce-unit-001", strict=True, now=now)
        assert result.ok is True
        assert result.legacy_fallback is False

    def test_check_replay_expired(self):
        import hmac_util

        now = time.time()
        ts = str(int(now) - 700)
        result = hmac_util.check_replay_headers(ts, "nonce-expire-001", strict=False, now=now)
        assert result.ok is False

    def test_check_replay_duplicate_nonce(self):
        import hmac_util

        now = time.time()
        ts = str(int(now))
        hmac_util.check_replay_headers(ts, "nonce-dup", strict=False, now=now)
        result2 = hmac_util.check_replay_headers(ts, "nonce-dup", strict=False, now=now)
        assert result2.ok is False

    def test_verify_signature_with_replay_new_protocol(self):
        import hmac_util

        secret = "test-secret-abc"
        body = b'{"test": true}'
        now = time.time()
        ts = str(int(now))
        nonce = "unit-nonce-001"
        sig = _sign(secret, body, ts=ts, nonce=nonce)
        ok, reason = hmac_util.verify_signature_with_replay(secret, body, sig, ts, nonce, strict=True, now=now)
        assert ok is True
        assert reason == ""

    def test_verify_signature_with_replay_bad_sig(self):
        import hmac_util

        secret = "test-secret-abc"
        body = b'{"test": true}'
        now = time.time()
        ts = str(int(now))
        nonce = "unit-nonce-002"
        ok, _reason = hmac_util.verify_signature_with_replay(
            secret, body, "sha256=badhex", ts, nonce, strict=True, now=now
        )
        assert ok is False

    def test_verify_signature_with_replay_legacy_non_strict(self):
        import hmac_util

        secret = "test-secret-abc"
        body = b'{"test": true}'
        sig = _sign(secret, body)  # body-only
        ok, reason = hmac_util.verify_signature_with_replay(secret, body, sig, None, None, strict=False)
        assert ok is True
        assert reason == "legacy"

    def test_verify_signature_with_replay_legacy_strict(self):
        import hmac_util

        secret = "test-secret-abc"
        body = b'{"test": true}'
        sig = _sign(secret, body)
        ok, _reason = hmac_util.verify_signature_with_replay(secret, body, sig, None, None, strict=True)
        assert ok is False
