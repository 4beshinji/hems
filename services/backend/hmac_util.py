"""
HMAC signature verification for mobile state-webhook payloads.

Each registered MobileDevice has its own hmac_secret (generated at register time).
Phone signs raw body with HMAC-SHA256 and sends header:
    X-HEMS-Signature: sha256=<hex_digest>

The signing secret is delivered to the phone once at registration time
(via QR code) and stored in the device's secure storage.

Replay protection (W1.3)
------------------------
When WEBHOOK_REPLAY_STRICT=true (default: false) the mobile state-webhook
additionally requires:
  X-Timestamp: <unix_seconds_integer>
  X-Nonce:     <opaque_string, unique per request>

The signing message is then:  <timestamp>.<nonce>.<body_hex_or_b64> — but
the simplest compatible approach is to fold timestamp and nonce into the
HMAC payload: sign(secret, f"{timestamp}:{nonce}:".encode() + body).

Backward-compat window: while STRICT=false, requests that omit the timestamp/
nonce headers are accepted with a WARNING log and the legacy body-only HMAC is
verified instead. Once companion apps are updated, flip STRICT=true.

Note: the in-memory nonce set is cleared on process restart.  This is
acceptable because the ±5-minute timestamp window prevents attackers from
replaying an old request even if the nonce cache is cold; they cannot
construct a future-stamped replay without the HMAC secret.
"""

import hashlib
import hmac
import os
import time
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Replay-protection configuration
# ---------------------------------------------------------------------------

#: Maximum age of a request timestamp in seconds (both past and future).
REPLAY_WINDOW_SECONDS: int = 300  # 5 minutes

#: Maximum number of nonces retained in memory.  Each nonce is a short string;
#: 10 000 entries ≈ a few hundred KB — well within budget for a single-occupant
#: system.  Entries are evicted in insertion order once the cap is reached.
_NONCE_CACHE_MAX: int = 10_000

# OrderedDict gives O(1) LRU-style eviction without a separate TTL thread.
# Nonces older than REPLAY_WINDOW_SECONDS are implicitly irrelevant even if
# still present (timestamp check rejects the outer request), so we only need
# to prevent the set from growing unboundedly between restarts.
_seen_nonces: OrderedDict[str, float] = OrderedDict()


def _prune_nonces(now: float) -> None:
    """Remove expired nonces to keep memory bounded between high-traffic bursts."""
    cutoff = now - REPLAY_WINDOW_SECONDS
    # OrderedDict is insertion-ordered; oldest entries are at the front.
    while _seen_nonces:
        _key, ts = next(iter(_seen_nonces.items()))
        if ts < cutoff:
            _seen_nonces.popitem(last=False)
        else:
            break
    # Hard cap as a backstop against replay storms.
    while len(_seen_nonces) > _NONCE_CACHE_MAX:
        _seen_nonces.popitem(last=False)


def _check_nonce(nonce: str, now: float) -> bool:
    """Return True and record *nonce* if it is fresh; False if already seen."""
    _prune_nonces(now)
    if nonce in _seen_nonces:
        return False
    _seen_nonces[nonce] = now
    return True


# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


def _signing_body(body: bytes, timestamp: str | None, nonce: str | None) -> bytes:
    """Return the byte string that is HMAC-signed.

    New protocol (timestamp + nonce present):
        ``<timestamp>:<nonce>:`` + raw body bytes

    Legacy protocol (no timestamp/nonce):
        raw body bytes only
    """
    if timestamp is not None and nonce is not None:
        prefix = f"{timestamp}:{nonce}:".encode()
        return prefix + body
    return body


def compute_signature(
    secret: str,
    body: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> str:
    """Return the hex HMAC-SHA256 digest for *body* (and optional replay fields).

    Pass *timestamp* and *nonce* to use the new signing protocol.  Omit them
    to fall back to the legacy body-only protocol.
    """
    msg = _signing_body(body, timestamp, nonce)
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header_value: str) -> bool:
    """Validate *header_value* (format: ``sha256=<hex>``) against *body*.

    Uses :func:`hmac.compare_digest` to prevent timing attacks. Returns False
    on any parse failure so callers can respond with a generic 401.

    This function verifies the **legacy** body-only signature.  For replay-
    protected verification use :func:`verify_signature_with_replay`.
    """
    if not header_value or not header_value.startswith("sha256="):
        return False
    provided = header_value[7:]
    expected = compute_signature(secret, body)
    return hmac.compare_digest(provided, expected)


# ---------------------------------------------------------------------------
# Replay-protected verification
# ---------------------------------------------------------------------------


class ReplayCheckResult:
    """Structured result from :func:`check_replay_headers`."""

    __slots__ = ("legacy_fallback", "ok", "reject_reason", "strict_mode")

    def __init__(
        self,
        ok: bool,
        reject_reason: str = "",
        strict_mode: bool = False,
        legacy_fallback: bool = False,
    ) -> None:
        self.ok = ok
        self.reject_reason = reject_reason
        self.strict_mode = strict_mode
        self.legacy_fallback = legacy_fallback


def check_replay_headers(
    timestamp_header: str | None,
    nonce_header: str | None,
    *,
    strict: bool = False,
    now: float | None = None,
) -> ReplayCheckResult:
    """Validate timestamp + nonce replay-prevention headers.

    Returns a :class:`ReplayCheckResult`.  The caller decides whether to
    reject based on ``result.ok`` and ``result.strict_mode``.

    When *strict* is False and headers are absent, returns
    ``ok=True, legacy_fallback=True`` — the caller should then re-verify the
    HMAC using the body-only legacy protocol and emit a WARNING.

    Nonce uniqueness is only enforced when the timestamp is within the window
    (no point burning a nonce slot on an already-expired request).
    """
    if now is None:
        now = time.time()

    if timestamp_header is None or nonce_header is None:
        if strict:
            return ReplayCheckResult(
                ok=False,
                reject_reason="X-Timestamp and X-Nonce headers are required (WEBHOOK_REPLAY_STRICT=true)",
                strict_mode=True,
            )
        # Non-strict: allow legacy requests.
        return ReplayCheckResult(ok=True, strict_mode=False, legacy_fallback=True)

    # --- Validate timestamp ---
    try:
        req_ts = float(timestamp_header)
    except (ValueError, TypeError):
        return ReplayCheckResult(ok=False, reject_reason="X-Timestamp must be a unix epoch integer")

    age = abs(now - req_ts)
    if age > REPLAY_WINDOW_SECONDS:
        return ReplayCheckResult(
            ok=False,
            reject_reason=f"X-Timestamp outside ±{REPLAY_WINDOW_SECONDS}s window (age={age:.0f}s)",
            strict_mode=strict,
        )

    # --- Validate nonce ---
    nonce = str(nonce_header).strip()
    if not nonce:
        return ReplayCheckResult(ok=False, reject_reason="X-Nonce must not be empty")

    if not _check_nonce(nonce, now):
        return ReplayCheckResult(ok=False, reject_reason="X-Nonce already used (replay detected)")

    return ReplayCheckResult(ok=True, strict_mode=strict, legacy_fallback=False)


def verify_signature_with_replay(
    secret: str,
    body: bytes,
    sig_header: str,
    timestamp_header: str | None,
    nonce_header: str | None,
    *,
    strict: bool | None = None,
    now: float | None = None,
) -> tuple[bool, str]:
    """Full verification: HMAC + replay protection.

    *strict* defaults to the ``WEBHOOK_REPLAY_STRICT`` env-var (false by default).

    Returns ``(ok: bool, reason: str)``.  On success reason is empty.
    On failure reason describes why — useful for structured logging.
    """
    if strict is None:
        strict = os.getenv("WEBHOOK_REPLAY_STRICT", "false").lower() in ("1", "true", "yes")

    if now is None:
        now = time.time()

    # --- Replay check ---
    replay = check_replay_headers(timestamp_header, nonce_header, strict=strict, now=now)

    if not replay.ok:
        return False, replay.reject_reason

    # --- HMAC verification ---
    if replay.legacy_fallback:
        # Headers absent in non-strict mode: verify body-only legacy HMAC.
        ok = verify_signature(secret, body, sig_header)
        if not ok:
            return False, "Invalid HMAC signature (legacy protocol)"
        # Signature is valid but caller should emit a warning.
        return True, "legacy"
    else:
        # New protocol: timestamp+nonce are folded into the signing input.
        if not sig_header or not sig_header.startswith("sha256="):
            return False, "Missing or malformed X-HEMS-Signature"
        provided = sig_header[7:]
        expected = compute_signature(secret, body, timestamp=timestamp_header, nonce=nonce_header)
        if not hmac.compare_digest(provided, expected):
            return False, "Invalid HMAC signature (new protocol)"
        return True, ""
