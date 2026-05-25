import os


def internal_headers() -> dict:
    token = os.getenv("HEMS_INTERNAL_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}
