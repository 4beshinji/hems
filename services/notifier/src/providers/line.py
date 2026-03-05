"""
LINE Notify provider.
Uses LINE Notify API (free, 1000 msgs/hour).
"""
import os
import httpx
from loguru import logger
from .base import NotifyProvider, Notification

LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "")
LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


class LINENotifyProvider(NotifyProvider):
    @property
    def name(self) -> str:
        return "line"

    def is_configured(self) -> bool:
        return bool(LINE_NOTIFY_TOKEN)

    async def send(self, notification: Notification) -> bool:
        msg = _format(notification)
        headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    LINE_NOTIFY_URL,
                    data={"message": msg},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    return True
                logger.error(f"LINE Notify error: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"LINE Notify send failed: {e}")
            return False


def _format(n: Notification) -> str:
    icon = {"CRITICAL": "\n[CRITICAL]", "HIGH": "\n[HIGH]", "NORMAL": "\n[INFO]", "INFO": "\n[REPORT]"}.get(n.level, "\n[INFO]")
    lines = [
        f"{icon} {n.title}",
        "---",
        n.body,
    ]
    if n.zone:
        lines.append(f"Zone: {n.zone}")
    if n.site_name:
        lines.append(f"Site: {n.site_name}")
    return "\n".join(lines)
