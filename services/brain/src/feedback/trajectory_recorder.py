"""Record decision-to-outcome trajectories for learning."""

from __future__ import annotations

from typing import Any

from loguru import logger


class TrajectoryRecorder:
    """Build and persist trajectories that tie decisions, actions, and feedback."""

    def __init__(self, event_writer: Any | None = None):
        self.event_writer = event_writer
        self._pending_decisions: dict[str, dict[str, Any]] = {}

    def record_decision(
        self,
        cycle_id: str,
        decision_id: str,
        trigger_events: list | None,
        tool_calls: list | None,
        world_state_snapshot: dict | None,
    ) -> None:
        """Stage the decision half of a trajectory."""
        self._pending_decisions[cycle_id] = {
            "cycle_id": cycle_id,
            "decision_id": decision_id,
            "trigger_events": trigger_events or [],
            "tool_calls": tool_calls or [],
            "world_state_snapshot": world_state_snapshot or {},
        }

    def finalize(
        self,
        cycle_id: str,
        outcome_summary: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Add outcome feedback and flush the trajectory to the event store."""
        decision = self._pending_decisions.pop(cycle_id, None)
        if decision is None:
            logger.debug(f"No pending decision for cycle {cycle_id}")
            return None

        trajectory = {**decision, "outcome_summary": outcome_summary}
        if self.event_writer is not None:
            try:
                self.event_writer.record_trajectory(
                    cycle_id=trajectory["cycle_id"],
                    decision_id=trajectory["decision_id"],
                    trigger_events=trajectory["trigger_events"],
                    tool_calls=trajectory["tool_calls"],
                    world_state_snapshot=trajectory["world_state_snapshot"],
                    outcome_summary=trajectory["outcome_summary"],
                )
            except Exception as e:
                logger.debug(f"Failed to record trajectory: {e}")
        return trajectory
