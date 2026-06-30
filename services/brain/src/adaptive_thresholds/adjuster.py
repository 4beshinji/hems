"""Translate feedback and efficacy verdicts into threshold offsets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdjusterConfig:
    step: float = 0.5
    min_offset: float = -5.0
    max_offset: float = 5.0


class ThresholdAdjuster:
    """Nudge threshold offsets based on human feedback and intervention efficacy.

    The mapping is intentionally conservative: a single piece of feedback does
    not swing the threshold wildly. The offset is clamped to prevent runaway.
    """

    def __init__(self, config: AdjusterConfig | None = None):
        self.config = config or AdjusterConfig()

    def compute_offset(
        self,
        current_offset: float,
        feedback_type: str | None = None,
        efficacy_verdict: str | None = None,
    ) -> float:
        """Return a new offset after applying feedback/efficacy nudges."""
        delta = 0.0

        if feedback_type:
            delta += self._feedback_delta(feedback_type)

        if efficacy_verdict:
            delta += self._efficacy_delta(efficacy_verdict)

        new_offset = current_offset + delta
        return max(self.config.min_offset, min(self.config.max_offset, new_offset))

    def _feedback_delta(self, feedback_type: str) -> float:
        """Map explicit/implicit feedback to an offset direction.

        Positive delta relaxes the threshold (harder to trigger);
        negative delta tightens it (easier to trigger).
        """
        mapping = {
            "explicit_up": -self.config.step,  # user liked it -> keep/tighten
            "explicit_down": self.config.step,  # user disliked -> relax
            "cancel": self.config.step,
            "dismiss": self.config.step * 0.5,
            "snooze": self.config.step * 0.3,
            "complete": -self.config.step * 0.5,
            "implicit_override": self.config.step,
        }
        return mapping.get(feedback_type, 0.0)

    def _efficacy_delta(self, verdict: str) -> float:
        """Map intervention efficacy verdict to an offset direction.

        effective   -> tighten slightly (system is helping)
        ineffective -> no change
        counterproductive -> relax (threshold was too aggressive)
        """
        mapping = {
            "effective": -self.config.step * 0.5,
            "ineffective": 0.0,
            "counterproductive": self.config.step,
        }
        return mapping.get(verdict, 0.0)
