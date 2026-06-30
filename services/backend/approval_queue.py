"""Backend-side approval request lifecycle manager.

Handles creation, timeout expiry, and decision application for HITL approval
requests. Keeps the router thin and testable.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300
_APPROVAL_STATUSES = {"proposed", "pending", "approved", "rejected", "modified", "expired", "rolled_back"}
_DECISIONS = {"approve", "reject", "modify"}
_RISK_TIERS = {"safe", "low", "medium", "high", "critical"}
_REVERSIBILITY = {"reversible", "compensatable", "irreversible"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApprovalQueueManager:
    """CRUD + timeout logic for approval requests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        body: schemas.ApprovalCreate,
        timeout_seconds: int | None = None,
    ) -> models.Approval:
        if body.risk_tier not in _RISK_TIERS:
            raise ValueError(f"risk_tier must be one of {sorted(_RISK_TIERS)}")
        if body.reversibility not in _REVERSIBILITY:
            raise ValueError(f"reversibility must be one of {sorted(_REVERSIBILITY)}")

        timeout = timeout_seconds if timeout_seconds is not None else _DEFAULT_TIMEOUT_SECONDS
        approval = models.Approval(
            id=uuid.uuid4(),
            thread_id=body.thread_id,
            rule_id=body.rule_id,
            action_type=body.action_type,
            risk_tier=body.risk_tier,
            reversibility=body.reversibility,
            confidence=body.confidence,
            proposed_payload=body.proposed_payload,
            context=body.context,
            status="pending",
            requested_at=_utcnow(),
            expires_at=_utcnow() + timedelta(seconds=timeout),
            audit_log=[{"event": "created", "at": _utcnow().isoformat()}],
        )
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def list_requests(
        self,
        status: str | None = None,
        thread_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[models.Approval]:
        query = select(models.Approval).order_by(models.Approval.requested_at.desc())
        if status:
            query = query.filter(models.Approval.status == status)
        if thread_id:
            query = query.filter(models.Approval.thread_id == thread_id)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get(self, approval_id: str | uuid.UUID) -> models.Approval | None:
        if isinstance(approval_id, str):
            try:
                approval_id = uuid.UUID(approval_id)
            except ValueError:
                return None
        result = await self.session.execute(select(models.Approval).filter(models.Approval.id == approval_id))
        return result.scalars().first()

    async def decide(
        self,
        approval: models.Approval,
        decision: schemas.ApprovalDecision,
    ) -> models.Approval:
        if approval.status not in {"proposed", "pending"}:
            raise ValueError(f"Cannot decide approval in status '{approval.status}'")
        if decision.decision not in _DECISIONS:
            raise ValueError(f"decision must be one of {sorted(_DECISIONS)}")

        now = _utcnow()
        approval.reviewer_id = decision.reviewer_id
        approval.decision = decision.decision
        approval.decision_reason = decision.reason
        approval.decided_at = now

        if decision.decision == "approve":
            approval.status = "approved"
        elif decision.decision == "reject":
            approval.status = "rejected"
        elif decision.decision == "modify":
            approval.status = "modified"
            if decision.modified_payload is not None:
                approval.proposed_payload = decision.modified_payload

        approval.audit_log.append(
            {
                "event": f"decided:{decision.decision}",
                "at": now.isoformat(),
                "reviewer_id": decision.reviewer_id,
                "reason": decision.reason,
            }
        )
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def mark_executed(self, approval: models.Approval) -> models.Approval:
        if approval.status not in {"approved", "modified"}:
            raise ValueError(f"Cannot execute approval in status '{approval.status}'")
        approval.executed_at = _utcnow()
        approval.audit_log.append({"event": "executed", "at": _utcnow().isoformat()})
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def mark_rolled_back(
        self,
        approval: models.Approval,
        rollback_status: str,
        trigger: str,
        error_message: str | None = None,
    ) -> models.RollbackLog:
        approval.status = "rolled_back"
        approval.rollback_status = rollback_status
        approval.audit_log.append(
            {
                "event": "rolled_back",
                "at": _utcnow().isoformat(),
                "trigger": trigger,
                "status": rollback_status,
            }
        )
        log = models.RollbackLog(
            approval_id=approval.id,
            trigger=trigger,
            compensation_plan=approval.rollback_plan,
            execution_status=rollback_status,
            completed_at=_utcnow() if rollback_status in {"success", "failed"} else None,
            error_message=error_message,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(approval)
        await self.session.refresh(log)
        return log

    async def record_snapshot(
        self, approval_id: str | uuid.UUID, snapshot: schemas.ActionSnapshotCreate
    ) -> models.ActionSnapshot:
        if isinstance(approval_id, str):
            approval_id = uuid.UUID(approval_id)
        record = models.ActionSnapshot(
            approval_id=approval_id,
            entity_type=snapshot.entity_type,
            entity_id=snapshot.entity_id,
            before_state=snapshot.before_state,
            after_state=snapshot.after_state,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def expire_stale(self) -> list[models.Approval]:
        """Mark pending/proposed requests past their expiry as expired."""
        result = await self.session.execute(
            select(models.Approval).filter(
                models.Approval.status.in_({"proposed", "pending"}),
                models.Approval.expires_at < _utcnow(),
            )
        )
        expired: list[models.Approval] = []
        for approval in result.scalars().all():
            approval.status = "expired"
            approval.audit_log.append({"event": "expired", "at": _utcnow().isoformat()})
            expired.append(approval)
        if expired:
            await self.session.commit()
        return expired
