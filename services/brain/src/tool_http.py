from brain_constants import brain_auth_headers


def internal_headers() -> dict:
    """Return the HEMS internal Bearer auth header.

    This is a thin wrapper around :func:`brain_constants.brain_auth_headers` so
    that existing callers can keep importing from ``tool_http`` while the
    canonical token-to-header logic lives in one place.
    """
    return brain_auth_headers()
