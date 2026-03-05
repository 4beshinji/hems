"""
Discord Webhook provider.
"""
import os
import httpx
from loguru import logger
from .base import NotifyProvider, Notification

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


class DiscordWebhookProvider(NotifyProvider):
    @property
    def name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        return bool(DISCORD_WEBHOOK_URL)

    async def send(self, notification: Notification) -> bool:
        embed = _build_embed(notification)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    DISCORD_WEBHOOK_URL,
                    json={"embeds": [embed]},
                    timeout=10,
                )
                if resp.status_code in (200, 204):
                    return True
                logger.error(f"Discord webhook error: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Discord webhook send failed: {e}")
            return False


def _build_embed(n: Notification) -> dict:
    color = {
        "CRITICAL": 0xFF0000,
        "HIGH": 0xFF8C00,
        "NORMAL": 0x3498DB,
        "INFO": 0x2ECC71,
    }.get(n.level, 0x95A5A6)

    fields = []
    if n.zone:
        fields.append({"name": "Zone", "value": n.zone, "inline": True})
    if n.source:
        fields.append({"name": "Source", "value": n.source, "inline": True})

    return {
        "title": f"[{n.level}] {n.title}",
        "description": n.body,
        "color": color,
        "fields": fields,
        "footer": {"text": n.site_name or n.site_id},
    }
