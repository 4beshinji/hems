"""Compute outcome reward from intervention efficacy and human feedback."""

from __future__ import annotations

from typing import Any

from loguru import logger


class OutcomeRewardCalculator:
    """Map efficacy verdicts and human decisions to a scalar reward."""

    VERDICT_REWARD = {
        "effective": 1.0,
        "counterproductive": -1.0,
        "inconclusive": 0.0,
    }

    HUMAN_DECISION_REWARD = {
        "approve": 0.2,
        "modify": 0.0,
        "reject": -0.5,
    }

    ROLLBACK_REWARD = {
        True: -0.3,
        False: 0.0,
    }

    def calculate(self, row: dict[str, Any]) -> float:
        """Return a reward in [-1, 1] for an intervention_efficacy row."""
        verdict = row.get("verdict")
        human_decision = row.get("human_decision")
        rolled_back = row.get("rolled_back")

        reward = self.VERDICT_REWARD.get(verdict, 0.0)
        if human_decision:
            reward += self.HUMAN_DECISION_REWARD.get(human_decision, 0.0)
        if rolled_back:
            reward += self.ROLLBACK_REWARD.get(True, 0.0)

        return max(-1.0, min(1.0, reward))

    def calculate_from_explicit_feedback(self, feedback_type: str) -> float | None:
        """Direct reward for simple explicit feedback types."""
        mapping = {
            "explicit_up": 1.0,
            "explicit_down": -1.0,
            "cancel": -0.5,
            "rerun": 0.0,
            "snooze": -0.2,
            "dismiss": -0.3,
            "complete": 0.5,
            "implicit_override": -0.5,
        }
        return mapping.get(feedback_type)

    async def update_efficacy_score(self, event_writer: Any, row_id: int, row: dict[str, Any]) -> float | None:
        """Persist the computed reward as efficacy_score."""
        if event_writer is None:
            return None
        score = self.calculate(row)
        try:
            await event_writer.record_intervention_verdict(
                row_id=row_id,
                post_value=row.get("post_value"),
                verdict=row.get("verdict", "inconclusive"),
                efficacy_score=score,
            )
        except Exception as e:
            logger.debug(f"Failed to update efficacy score: {e}")
            return None
        return score
