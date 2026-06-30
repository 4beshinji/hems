"""Detect implicit feedback from user behavior after an agent action."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class TrackedAction:
    """An action that may be implicitly overridden by the user."""

    target_type: str
    target_id: str
    device_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# Simple action -> inverse mapping for implicit override detection.
_INVERSE_ACTIONS = {
    "on": "off",
    "off": "on",
    "lock": "unlock",
    "unlock": "lock",
    "open": "close",
    "close": "open",
}


class ImplicitFeedbackDetector:
    """Watch recent agent actions and flag immediate user overrides."""

    def __init__(
        self,
        collector: Any,
        window_seconds: float = 30.0,
        clock: Callable[[], datetime] | None = None,
    ):
        self.collector = collector
        self.window_seconds = window_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._recent_actions: list[TrackedAction] = []

    def record_action(
        self,
        target_type: str,
        target_id: str,
        device_id: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Register an action the agent just performed."""
        self._prune()
        self._recent_actions.append(
            TrackedAction(
                target_type=target_type,
                target_id=target_id,
                device_id=device_id,
                action=action,
                params=params or {},
                timestamp=self._clock(),
            )
        )

    def observe_state(self, device_id: str, new_state: dict[str, Any]) -> list[dict[str, Any]]:
        """Observe a device state update and emit implicit feedback if it overrides a recent action."""
        self._prune()
        emitted: list[dict[str, Any]] = []
        for tracked in list(self._recent_actions):
            if tracked.device_id != device_id:
                continue
            if self._is_override(tracked, new_state):
                feedback = self.collector.collect_implicit(
                    target_type=tracked.target_type,
                    target_id=tracked.target_id,
                    feedback_type="implicit_override",
                    context={
                        "device_id": device_id,
                        "agent_action": tracked.action,
                        "observed_state": new_state,
                        "seconds_after_action": (self._clock() - tracked.timestamp).total_seconds(),
                    },
                )
                emitted.append(feedback)
                self._recent_actions.remove(tracked)
        return emitted

    def _prune(self) -> None:
        cutoff = self._clock() - timedelta(seconds=self.window_seconds)
        self._recent_actions = [a for a in self._recent_actions if a.timestamp >= cutoff]

    @staticmethod
    def _is_override(tracked: TrackedAction, new_state: dict[str, Any]) -> bool:
        """Heuristic: the new state contradicts the agent's recent action."""
        inverse = _INVERSE_ACTIONS.get(tracked.action)
        if inverse and new_state.get("action") == inverse:
            return True
        # For simple on/off states the new_state may not contain an action key.
        if tracked.action == "on" and new_state.get("on") is False:
            return True
        if tracked.action == "off" and new_state.get("on") is True:
            return True
        return False
