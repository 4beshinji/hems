"""Tests for brain-side approval audit logger (Phase 0 HITL)."""

import pytest

from approval.audit_logger import ApprovalAuditLogger


class _FakeEventWriter:
    def __init__(self):
        self.events = []

    def record_event(self, zone: str, event_type: str, data: dict):
        self.events.append((zone, event_type, data))


@pytest.mark.asyncio
async def test_audit_created_and_decided():
    writer = _FakeEventWriter()
    logger = ApprovalAuditLogger(writer)
    logger.created("app-1", 1, "rule", "high", "compensatable")
    logger.decided("app-1", "approve", "user-1", "looks good")

    assert len(writer.events) == 2
    assert writer.events[0][1] == "approval_created"
    assert writer.events[0][2]["approval_id"] == "app-1"
    assert writer.events[1][1] == "approval_decided"
    assert writer.events[1][2]["decision"] == "approve"


@pytest.mark.asyncio
async def test_audit_logger_is_noop_without_writer():
    logger = ApprovalAuditLogger(None)
    logger.created("app-1", 1, "rule", "high", "compensatable")
    # No exception and no side effects.
