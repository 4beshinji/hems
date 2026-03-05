"""
ntfy.sh provider — self-hostable push notifications.
"""
import os
import httpx
from loguru import logger
from .base import NotifyProvider, Notification

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")


class NtfyProvider(NotifyProvider):
    @property
    def name(self) -> str:
        return "ntfy"

    def is_configured(self) -> bool:
        return bool(NTFY_TOPIC)

    async def send(self, notification: Notification) -> bool:
        url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
        priority = {
            "CRITICAL": "5",  # max
            "HIGH": "4",      # high
            "NORMAL": "3",    # default
            "INFO": "2",      # low
        }.get(notification.level, "3")

        tags = {
            "CRITICAL": "rotating_light,skull",
            "HIGH": "warning",
            "NORMAL": "information_source",
            "INFO": "chart_with_upwards_trend",
        }.get(notification.level, "")

        headers = {
            "Title": f"[{notification.level}] {notification.title}",
            "Priority": priority,
            "Tags": tags,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    content=notification.body,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    return True
                logger.error(f"ntfy error: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"ntfy send failed: {e}")
            return False
