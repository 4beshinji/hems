"""Rollback executor: run a RollbackPlan's compensation actions.

Records success/failure via the backend approval API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from approval.client import ApprovalClient
from approval.rollback_planner import RollbackPlan


class RollbackExecutor:
    """Execute compensation actions produced by RollbackPlanner."""

    def __init__(
        self,
        client: ApprovalClient,
        executor: Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]],
    ):
        self.client = client
        self.executor = executor

    async def execute(self, plan: RollbackPlan, trigger: str) -> dict[str, Any]:
        """Execute rollback plan and report result to backend."""
        if not plan.compensation_actions:
            # Nothing to do — may still record that rollback was considered.
            result = await self.client.record_rollback(
                plan.approval_id,
                trigger=trigger,
                status="success" if not plan.irreversible_actions else "failed",
                error_message=plan.reason if plan.irreversible_actions else None,
            )
            return {
                "success": not plan.irreversible_actions,
                "executed": 0,
                "errors": [plan.reason] if plan.irreversible_actions else [],
                "rollback_log": result,
            }

        exec_result = await self.executor(plan.compensation_actions)
        success = exec_result.get("success", False) and not plan.irreversible_actions
        status = "success" if success else "failed"
        error_message = None
        if plan.irreversible_actions:
            error_message = plan.reason
        elif exec_result.get("errors"):
            error_message = "; ".join(exec_result["errors"])

        log = await self.client.record_rollback(
            plan.approval_id,
            trigger=trigger,
            status=status,
            error_message=error_message,
        )
        return {
            "success": success,
            "executed": exec_result.get("executed", 0),
            "errors": exec_result.get("errors", []),
            "rollback_log": log,
        }
