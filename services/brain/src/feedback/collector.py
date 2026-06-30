"""Normalize and persist agent feedback to the event_store."""

from __future__ import annotations

from typing import Any

from loguru import logger


class FeedbackCollector:
    """Collect explicit/implicit feedback and replicate it to the learning store."""

    def __init__(self, event_writer: Any | None = None):
        self.event_writer = event_writer

    def collect_explicit(
        self,
        target_type: str,
        target_id: str,
        feedback_type: str,
        *,
        channel: str = "mqtt",
        payload: dict | None = None,
        context: dict | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Buffer explicit human feedback."""
        normalized = self._normalize(
            target_type=target_type,
            target_id=target_id,
            feedback_type=feedback_type,
            channel=channel,
            payload=payload,
            context=context,
            user_id=user_id,
        )
        if self.event_writer is not None:
            try:
                self.event_writer.record_feedback(**normalized)
            except Exception as e:
                logger.debug(f"Failed to buffer explicit feedback: {e}")
        return normalized

    def collect_implicit(
        self,
        target_type: str,
        target_id: str,
        feedback_type: str,
        *,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Buffer implicit feedback detected from user behavior."""
        return self.collect_explicit(
            target_type=target_type,
            target_id=target_id,
            feedback_type=feedback_type,
            channel="implicit",
            context=context,
        )

    @staticmethod
    def _normalize(
        target_type: str,
        target_id: str,
        feedback_type: str,
        channel: str,
        payload: dict | None,
        context: dict | None,
        user_id: str | None,
    ) -> dict[str, Any]:
        return {
            "target_type": target_type,
            "target_id": target_id,
            "feedback_type": feedback_type,
            "channel": channel,
            "payload": payload or {},
            "context": context or {},
            "user_id": user_id,
        }
