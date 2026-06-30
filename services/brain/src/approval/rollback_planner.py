"""Rollback planner: turn an executed action + before-state snapshot into a
compensation plan that restores the previous device state.

The planner is best-effort: some actions (notifications, IR blasts, messages)
are inherently irreversible and are recorded as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RollbackPlan:
    approval_id: str
    can_compensate: bool
    compensation_actions: list[dict[str, Any]] = field(default_factory=list)
    irreversible_actions: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


# Action -> inverse action mapping for simple reversible actions.
_SIMPLE_INVERSE = {
    "on": "off",
    "off": "on",
    "lock": "unlock",
    "unlock": "lock",
    "open": "close",
    "close": "open",
}

# Actions that cannot be rolled back.
_IRREVERSIBLE_ACTIONS = {"ir_send", "message_send", "alert", "notify", "call", "pulse"}


def build_rollback_plan(
    approval_id: str,
    original_actions: list[dict[str, Any]],
    before_states: dict[str, dict[str, Any]],
) -> RollbackPlan:
    """Generate a compensation plan from original actions and before snapshots.

    before_states maps device_id -> last_state captured before execution.
    """
    compensation: list[dict[str, Any]] = []
    irreversible: list[dict[str, Any]] = []
    reasons: list[str] = []

    for a in original_actions:
        device_id = a.get("device_id", "")
        action = a.get("action", "")
        before = before_states.get(device_id, {})

        if action in _IRREVERSIBLE_ACTIONS:
            irreversible.append(a)
            reasons.append(f"{device_id}.{action} is irreversible")
            continue

        # Prefer captured before-state over a simple inverse action.
        restored = _restore_from_state(device_id, action, before)
        if restored:
            compensation.append(restored)
            continue

        inverse = _SIMPLE_INVERSE.get(action)
        if inverse:
            compensation.append({"device_id": device_id, "action": inverse, "params": {}, "delay_s": 0})
            continue

        irreversible.append(a)
        reasons.append(f"{device_id}.{action} has no inverse")

    can_compensate = not irreversible or bool(compensation)
    return RollbackPlan(
        approval_id=approval_id,
        can_compensate=can_compensate,
        compensation_actions=compensation,
        irreversible_actions=irreversible,
        reason="; ".join(reasons) if reasons else "full compensation possible",
    )


def _restore_from_state(device_id: str, action: str, before: dict[str, Any]) -> dict[str, Any] | None:
    """Try to synthesize a state-restoring action from a before snapshot."""
    if not before:
        return None

    # On/off actions restored from captured on/off state.
    if action in ("on", "off") and "on" in before:
        return {"device_id": device_id, "action": "on" if before["on"] else "off", "params": {}, "delay_s": 0}

    # Lock/unlock actions restored from captured lock state.
    if action in ("lock", "unlock") and "locked" in before:
        return {
            "device_id": device_id,
            "action": "lock" if before["locked"] else "unlock",
            "params": {},
            "delay_s": 0,
        }

    # Open/close actions restored from captured open state or position.
    if action in ("open", "close") and "open" in before:
        return {
            "device_id": device_id,
            "action": "open" if before["open"] else "close",
            "params": {},
            "delay_s": 0,
        }

    if action in ("open", "close", "set_position") and "position" in before:
        return {
            "device_id": device_id,
            "action": "set_position",
            "params": {"position": before["position"]},
            "delay_s": 0,
        }

    # Brightness restore.
    if action == "set_brightness" and "brightness" in before:
        return {
            "device_id": device_id,
            "action": "set_brightness",
            "params": {"brightness": before["brightness"]},
            "delay_s": 0,
        }

    # Color temperature restore.
    if action == "set_color_temp" and "color_temp" in before:
        return {
            "device_id": device_id,
            "action": "set_color_temp",
            "params": {"color_temp": before["color_temp"]},
            "delay_s": 0,
        }

    return None
