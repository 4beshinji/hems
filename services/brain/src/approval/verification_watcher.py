"""Verification watcher: confirm that a rollback restored the expected state.

Compares current device state (via state lookup) against the before-state
snapshot captured prior to the original action.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class VerificationWatcher:
    """Verify post-rollback state matches the captured before state."""

    def __init__(self, state_lookup: Callable[[str], Awaitable[dict[str, Any] | None]]):
        self.state_lookup = state_lookup

    async def verify(
        self,
        approval_id: str,
        before_states: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Return verification report for each device in before_states."""
        checked: dict[str, dict[str, Any]] = {}
        all_match = True
        for device_id, expected in before_states.items():
            current_device = await self.state_lookup(device_id)
            current = (current_device or {}).get("last_state", {})
            matches = self._state_matches(expected, current)
            checked[device_id] = {
                "expected": expected,
                "current": current,
                "matches": matches,
            }
            if not matches:
                all_match = False
        return {
            "approval_id": approval_id,
            "verified": all_match,
            "devices": checked,
        }

    def _state_matches(self, expected: dict[str, Any], current: dict[str, Any]) -> bool:
        """Check that key fields in expected are present and equal in current."""
        if not expected:
            return True
        for key, value in expected.items():
            if key not in current:
                return False
            if current[key] != value:
                return False
        return True
