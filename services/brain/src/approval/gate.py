"""Human-in-the-loop approval gate for Brain actions.

Wraps action execution so high-risk / irreversible actions pause for human
approval before (and optionally rollback after) execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from approval.action_risk_classifier import RiskClassification, classify_action, classify_rule
from approval.audit_logger import ApprovalAuditLogger
from approval.client import ApprovalClient
from approval.rollback_executor import RollbackExecutor
from approval.rollback_planner import build_rollback_plan


class ApprovalGate:
    """Gate that pauses action execution pending human approval when required."""

    def __init__(
        self,
        client: ApprovalClient,
        executor: Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]],
        state_lookup: Callable[[str], Awaitable[dict[str, Any] | None]] | None = None,
        event_writer: Any | None = None,
        rollback_executor: RollbackExecutor | None = None,
        audit_logger: ApprovalAuditLogger | None = None,
    ):
        self.client = client
        self.executor = executor
        self.state_lookup = state_lookup
        self.event_writer = event_writer
        self.rollback_executor = rollback_executor
        self.audit_logger = audit_logger or ApprovalAuditLogger(event_writer)

    async def execute_rule(
        self,
        rule: dict[str, Any],
        *,
        thread_id: str | None = None,
        extra_context: dict | None = None,
    ) -> dict[str, Any]:
        """Execute an AutomationRule's actions through the approval gate."""
        classification = classify_rule(rule)
        actions = rule.get("actions") or []
        context = {
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "trigger_type": rule.get("trigger_type"),
            **(extra_context or {}),
        }
        return await self._run(
            action_type="rule",
            proposed_payload={"rule_id": rule.get("id"), "actions": actions},
            classification=classification,
            actions=actions,
            context=context,
            rule_id=rule.get("id"),
            thread_id=thread_id,
        )

    async def execute_actions(
        self,
        actions: list[dict[str, Any]],
        *,
        action_type: str = "scene",
        context: dict | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a raw action list through the approval gate."""
        classification = self._classify_actions(actions)
        return await self._run(
            action_type=action_type,
            proposed_payload={"actions": actions},
            classification=classification,
            actions=actions,
            context=context or {},
            thread_id=thread_id,
        )

    def _classify_actions(self, actions: list[dict[str, Any]]) -> RiskClassification:
        max_score = 0
        reasons: list[str] = []
        for a in actions:
            c = classify_action(a)
            if c.score > max_score:
                max_score = c.score
                reasons.append(c.reason)
        tier = ["safe", "low", "medium", "high", "critical"][min(max_score, 4)]
        approval_required = tier in {"high", "critical"}
        return RiskClassification(
            risk_tier=tier,
            reversibility="compensatable" if max_score >= 3 else "reversible",
            approval_required=approval_required,
            score=max_score,
            reason="; ".join(reasons) if reasons else "default low risk",
        )

    async def _run(
        self,
        action_type: str,
        proposed_payload: dict,
        classification: RiskClassification,
        actions: list[dict[str, Any]],
        context: dict,
        rule_id: int | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        if not classification.approval_required:
            logger.debug(f"Approval gate: direct execution ({classification.risk_tier})")
            return await self.executor(actions)

        approval = await self.client.create(
            action_type=action_type,
            proposed_payload=proposed_payload,
            risk_tier=classification.risk_tier,
            reversibility=classification.reversibility,
            context=context,
            rule_id=rule_id,
            thread_id=thread_id,
        )
        approval_id = approval.get("id")
        if not approval_id:
            logger.error("Approval gate: backend did not return approval_id")
            return {"success": False, "error": "approval creation failed", "executed": 0}

        logger.info(f"Approval gate: waiting for decision on {approval_id} (tier={classification.risk_tier})")
        self.audit_logger.created(
            approval_id,
            rule_id=rule_id,
            action_type=action_type,
            risk_tier=classification.risk_tier,
            reversibility=classification.reversibility,
        )

        before_states = await self._capture_states(actions)
        await self._record_snapshots(approval_id, actions, before_states, after=False)

        decision = await self.client.poll_decision(approval_id)
        status = decision.get("status")
        self.audit_logger.decided(
            approval_id,
            decision=decision.get("decision") or status,
            reviewer_id=decision.get("reviewer_id"),
            reason=decision.get("decision_reason"),
        )

        if status == "approved":
            result = await self.executor(actions)
            await self._record_snapshots(approval_id, actions, before_states, after=True)
            await self.client.mark_executed(approval_id)
            self.audit_logger.executed(
                approval_id,
                success=result.get("success", False),
                executed=result.get("executed", 0),
                errors=result.get("errors", []),
            )
            return {**result, "approval_id": approval_id, "approval_status": "approved"}

        if status == "modified":
            modified = decision.get("proposed_payload", {}).get("actions", actions)
            result = await self.executor(modified)
            await self._record_snapshots(approval_id, modified, before_states, after=True)
            await self.client.mark_executed(approval_id)
            self.audit_logger.executed(
                approval_id,
                success=result.get("success", False),
                executed=result.get("executed", 0),
                errors=result.get("errors", []),
            )
            return {**result, "approval_id": approval_id, "approval_status": "modified"}

        # rejected / expired / rolled_back / unknown
        logger.info(f"Approval gate: action cancelled ({status}) for {approval_id}")
        rollback_result: dict[str, Any] | None = None
        if status in {"rejected", "expired"}:
            trigger = "human_reject" if status == "rejected" else "timeout"
            if self.rollback_executor and before_states:
                plan = build_rollback_plan(approval_id, actions, before_states)
                rollback_result = await self.rollback_executor.execute(plan, trigger=trigger)
            else:
                try:
                    await self.client.record_rollback(approval_id, trigger=trigger, status="success")
                except Exception as e:
                    logger.warning(f"Failed to record rollback for {approval_id}: {e}")
            rollback_errors = rollback_result.get("errors") if rollback_result else None
            self.audit_logger.rolled_back(
                approval_id,
                trigger=trigger,
                rollback_success=(rollback_result.get("success") if rollback_result else True),
                error_message=rollback_errors[0] if rollback_errors else None,
            )
        return {
            "success": False,
            "error": f"approval {status}",
            "executed": 0,
            "approval_id": approval_id,
            "approval_status": status,
            "rollback": rollback_result,
        }

    async def _capture_states(self, actions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if self.state_lookup is None:
            return {}
        states: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        for a in actions:
            device_id = a.get("device_id")
            if not device_id or device_id in seen:
                continue
            seen.add(device_id)
            try:
                device = await self.state_lookup(device_id)
                states[device_id] = (device or {}).get("last_state", {})
            except Exception as e:
                logger.debug(f"State capture failed for {device_id}: {e}")
                states[device_id] = {}
        return states

    async def _record_snapshots(
        self,
        approval_id: str,
        actions: list[dict[str, Any]],
        before_states: dict[str, dict[str, Any]],
        *,
        after: bool,
    ):
        seen: set[str] = set()
        for a in actions:
            device_id = a.get("device_id")
            if not device_id or device_id in seen:
                continue
            seen.add(device_id)
            before_state = before_states.get(device_id, {})
            after_state: dict[str, Any] = {}
            if after and self.state_lookup is not None:
                try:
                    device = await self.state_lookup(device_id)
                    after_state = (device or {}).get("last_state", {})
                except Exception as e:
                    logger.debug(f"After-state capture failed for {device_id}: {e}")
            try:
                await self.client.record_snapshot(
                    approval_id,
                    entity_type="device",
                    entity_id=device_id,
                    before_state=before_state,
                    after_state=after_state,
                )
            except Exception as e:
                logger.debug(f"Snapshot failed for {device_id}: {e}")
