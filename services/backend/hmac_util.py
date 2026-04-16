"""
HMAC signature verification for mobile state-webhook payloads.

Each registered MobileDevice has its own hmac_secret (generated at register time).
Phone signs raw body with HMAC-SHA256 and sends header:
    X-HEMS-Signature: sha256=<hex_digest>

The signing secret is delivered to the phone once at registration time
(via QR code) and stored in the device's secure storage.
"""
import hmac
import hashlib


def compute_signature(secret: str, body: bytes) -> str:
    """Return the hex HMAC-SHA256 digest for *body* using *secret*."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header_value: str) -> bool:
    """Validate *header_value* (format: ``sha256=<hex>``) against *body*.

    Uses :func:`hmac.compare_digest` to prevent timing attacks. Returns False
    on any parse failure so callers can respond with a generic 401.
    """
    if not header_value or not header_value.startswith("sha256="):
        return False
    provided = header_value[7:]
    expected = compute_signature(secret, body)
    return hmac.compare_digest(provided, expected)
