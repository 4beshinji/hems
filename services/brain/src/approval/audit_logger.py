"""Brain-side audit logger for HITL approval flow events.

Writes immutable approval lifecycle events to the event_store so the full
human-in-the-loop trace is preserved alongside sensor and LLM events.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class ApprovalAuditLogger:
    """Record approval lifecycle events via an EventWriter-compatible object."""

    def __init__(self, event_writer: Any | None):
        self.event_writer = event_writer

    def _record(self, event_type: str, approval_id: str, data: dict[str, Any]):
        if self.event_writer is None:
            return
        try:
            self.event_writer.record_event(
                zone="hems",
                event_type=f"approval_{event_type}",
                data={"approval_id": approval_id, **data},
            )
        except Exception as e:
            logger.debug(f"Approval audit log failed ({event_type}): {e}")

    def created(
        self,
        approval_id: str,
        rule_id: int | None,
        action_type: str,
        risk_tier: str,
        reversibility: str,
    ):
        self._record(
            "created",
            approval_id,
            {
                "rule_id": rule_id,
                "action_type": action_type,
                "risk_tier": risk_tier,
                "reversibility": reversibility,
            },
        )

    def decided(self, approval_id: str, decision: str, reviewer_id: str | None, reason: str | None):
        self._record(
            "decided",
            approval_id,
            {"decision": decision, "reviewer_id": reviewer_id, "reason": reason},
        )

    def executed(self, approval_id: str, success: bool, executed: int, errors: list[str]):
        self._record(
            "executed",
            approval_id,
            {"success": success, "executed": executed, "errors": errors},
        )

    def rolled_back(
        self,
        approval_id: str,
        trigger: str,
        rollback_success: bool,
        error_message: str | None,
    ):
        self._record(
            "rolled_back",
            approval_id,
            {
                "trigger": trigger,
                "rollback_success": rollback_success,
                "error_message": error_message,
            },
        )
