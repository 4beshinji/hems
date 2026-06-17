"""VIP sender / repo identification for service edge events."""

import os


def _vip_gmail_senders() -> list[str]:
    """Return configured VIP Gmail senders from env (read each call for testability)."""
    return [s.strip().lower() for s in os.getenv("HEMS_GMAIL_VIP_SENDERS", "").split(",") if s.strip()]


def _vip_github_repos() -> list[str]:
    """Return configured VIP GitHub repos from env (read each call for testability)."""
    return [s.strip().lower() for s in os.getenv("HEMS_GITHUB_VIP_REPOS", "").split(",") if s.strip()]


def _is_vip_gmail_sender(sender: str) -> bool:
    """Return True if the sender address matches a configured VIP Gmail sender."""
    normalized = sender.lower()
    return any(v and v in normalized for v in _vip_gmail_senders())


def _detect_service_vip(service_name: str, payload: dict) -> bool:
    """Return True if the service event is from a VIP sender or repo."""
    if payload.get("vip"):
        return True
    haystack = " ".join(
        str(payload.get(k, "")) for k in ("summary", "details", "subject", "from", "sender", "repo")
    ).lower()
    if not haystack:
        return False
    if service_name == "gmail":
        return any(s and s in haystack for s in _vip_gmail_senders())
    if service_name == "github":
        return any(s and s in haystack for s in _vip_github_repos())
    return False


# Backward-compatible module-level aliases (re-exported by world_model.py).
# Prefer the helper functions above for new code.
# NOTE: these are evaluated once at import time, whereas the helper functions
# read the env var on every call. Keep the aliases for existing callers, but
# prefer the helpers when hot-reloading env changes matters.
_VIP_GMAIL_SENDERS = _vip_gmail_senders()
_VIP_GITHUB_REPOS = _vip_github_repos()
