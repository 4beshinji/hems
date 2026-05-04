"""
Shared bridge authentication — no-op for LAN-trusted deployment.

All bridge REST endpoints are open on the internal Docker network.
For external exposure, protect via nginx/reverse-proxy auth.
"""


def verify_bridge_key() -> None:
    return None
