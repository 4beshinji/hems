"""
Slack Incoming Webhook provider.
"""
import os
import httpx
from loguru import logger
from .base import NotifyProvider, Notification

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


class SlackWebhookProvider(NotifyProvider):
    @property
    def name(self) -> str:
        return "slack"

    def is_configured(self) -> bool:
        return bool(SLACK_WEBHOOK_URL)

    async def send(self, notification: Notification) -> bool:
        payload = _build_payload(notification)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    SLACK_WEBHOOK_URL,
                    json=payload,
                    timeout=10,
                )
                if resp.status_code == 200:
                    return True
                logger.error(f"Slack webhook error: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Slack webhook send failed: {e}")
            return False


def _build_payload(n: Notification) -> dict:
    emoji = {
        "CRITICAL": ":rotating_light:",
        "HIGH": ":warning:",
        "NORMAL": ":information_source:",
        "INFO": ":chart_with_upwards_trend:",
    }.get(n.level, ":grey_question:")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} [{n.level}] {n.title}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": n.body},
        },
    ]

    context_parts = []
    if n.zone:
        context_parts.append(f"Zone: {n.zone}")
    if n.site_name:
        context_parts.append(f"Site: {n.site_name}")
    if context_parts:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " | ".join(context_parts)}],
        })

    return {"blocks": blocks}
