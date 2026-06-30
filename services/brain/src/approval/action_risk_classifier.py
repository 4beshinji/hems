"""Action / automation rule risk classifier for HITL approval gating.

Maps a rule or concrete action payload to a risk tier, reversibility class,
and whether human approval is required before execution. The classifier
combines explicit backend metadata with heuristics on the action content
(device class, action type, safety keywords).

Output tiers (least to most risky):
    safe < low < medium < high < critical

Reversibility classes:
    reversible      — can be undone cleanly (light on/off)
    compensatable   — undoable with extra effort / side effects (open window)
    irreversible    — cannot be undone (send message, irreversible appliance)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskClassification:
    risk_tier: str
    reversibility: str
    approval_required: bool
    score: int
    reason: str


# Ordered tiers with numeric scores.
_RISK_TIERS = ["safe", "low", "medium", "high", "critical"]
_RISK_SCORES = {t: i for i, t in enumerate(_RISK_TIERS)}

_REVERSIBILITY = {"reversible", "compensatable", "irreversible"}

# Device classes and action keywords that push risk upward.
_CRITICAL_DEVICE_CLASSES = {
    "medical",
    "spo2",
    "heart_rate",
    "fall_detector",
    "gas_valve",
    "water_valve",
    "smoke",
    "co",
}
_HIGH_DEVICE_CLASSES = {
    "curtain",
    "lock",
    "pump",
    "heater",
    "fan",
    "ac",
    "aircon",
    "window",
}

_CRITICAL_ACTIONS = {"ir_send", "message_send", "alert", "notify", "call"}
_HIGH_ACTIONS = {"set_position", "pulse", "reboot", "reset"}

# Safety-critical free-text tokens in rule name / description / action params.
_CRITICAL_KEYWORDS = [
    "漏水",
    "水漏れ",
    "火災",
    "煙",
    "co2危険",
    "co危険",
    "spo2",
    "酸素",
    "緊急",
    "fall",
    "倒れ",
    "ガス",
]


def _normalize(text: str | None) -> str:
    return (text or "").lower()


def _tier_score(tier: str | None) -> int:
    return _RISK_SCORES.get(tier or "low", _RISK_SCORES["low"])


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = _normalize(text)
    return any(kw.lower() in lowered for kw in keywords)


def classify_rule(rule: dict) -> RiskClassification:
    """Classify an AutomationRule (backend dict) for approval gating.

    Explicit backend fields (risk_tier, reversibility, approval_required) take
    precedence when they indicate higher risk. Otherwise the action content is
    inspected.
    """
    explicit_tier = rule.get("risk_tier")
    explicit_reversibility = rule.get("reversibility")
    explicit_approval = rule.get("approval_required")

    action_text = ""
    actions = rule.get("actions") or []
    for a in actions:
        action_text += f" {a.get('device_id', '')} {a.get('action', '')} {a.get('params', '')}"

    context_text = f"{rule.get('name', '')} {rule.get('description', '')} {action_text}"

    # Start from explicit tier or low.
    score = _tier_score(explicit_tier)
    reasons: list[str] = []
    if explicit_tier:
        reasons.append(f"rule tier={explicit_tier}")

    # Inspect each action.
    for a in actions:
        ac = classify_action(a)
        if ac.score > score:
            score = ac.score
            reasons.append(ac.reason)

    # Safety keywords override to at least high.
    if _contains_any(context_text, _CRITICAL_KEYWORDS):
        score = max(score, _RISK_SCORES["high"])
        reasons.append("safety keyword matched")

    # Irreversible actions default to at least medium.
    if explicit_reversibility == "irreversible":
        score = max(score, _RISK_SCORES["medium"])
        reasons.append("explicit irreversible")

    tier = _RISK_TIERS[min(score, len(_RISK_TIERS) - 1)]

    # Determine reversibility.
    reversibility = explicit_reversibility or _derive_reversibility(actions, tier)
    if reversibility not in _REVERSIBILITY:
        reversibility = "reversible"

    # Determine approval requirement.
    approval_required = bool(explicit_approval)
    if not approval_required:
        approval_required = tier in {"high", "critical"} or reversibility == "irreversible"
        if approval_required:
            reasons.append(f"auto-required by tier={tier} or irreversibility")

    reason = "; ".join(reasons) if reasons else "default low risk"
    return RiskClassification(
        risk_tier=tier,
        reversibility=reversibility,
        approval_required=approval_required,
        score=score,
        reason=reason,
    )


def classify_action(action: dict) -> RiskClassification:
    """Classify a single scene action dict."""
    device_id = _normalize(action.get("device_id"))
    act = _normalize(action.get("action"))
    params = action.get("params") or {}
    params_text = str(params)

    score = _RISK_SCORES["low"]
    reasons: list[str] = []

    # Device class heuristics embedded in device_id or params.
    for cls in _CRITICAL_DEVICE_CLASSES:
        if cls in device_id or cls in params_text:
            score = _RISK_SCORES["critical"]
            reasons.append(f"critical device class: {cls}")
            break
    else:
        for cls in _HIGH_DEVICE_CLASSES:
            if cls in device_id or cls in params_text:
                score = max(score, _RISK_SCORES["high"])
                reasons.append(f"high-risk device class: {cls}")
                break

    # Action type heuristics.
    if act in _CRITICAL_ACTIONS:
        score = _RISK_SCORES["critical"]
        reasons.append(f"critical action: {act}")
    elif act in _HIGH_ACTIONS:
        score = max(score, _RISK_SCORES["high"])
        reasons.append(f"high-risk action: {act}")

    tier = _RISK_TIERS[min(score, len(_RISK_TIERS) - 1)]
    reversibility = _derive_reversibility([action], tier)
    approval_required = tier in {"high", "critical"}

    return RiskClassification(
        risk_tier=tier,
        reversibility=reversibility,
        approval_required=approval_required,
        score=score,
        reason="; ".join(reasons) if reasons else "default low risk",
    )


def _derive_reversibility(actions: list[dict], tier: str) -> str:
    """Default reversibility based on action content."""
    if tier in {"high", "critical"}:
        return "compensatable"

    for a in actions:
        act = _normalize(a.get("action"))
        if act in _CRITICAL_ACTIONS:
            return "irreversible"
        if act in {"ir_send", "message_send"}:
            return "irreversible"
        if act in {"set_position", "pulse"}:
            return "compensatable"

    # Simple on/off toggle of lights/plugs is reversible.
    if actions and all(_normalize(a.get("action")) in {"on", "off", "toggle"} for a in actions):
        return "reversible"

    return "compensatable"


def override_if_stricter(
    classification: RiskClassification,
    require_confirm: bool | None = None,
    explicit_tier: str | None = None,
    explicit_reversibility: str | None = None,
) -> RiskClassification:
    """Return a new classification that is at least as strict as the inputs."""
    score = max(classification.score, _tier_score(explicit_tier))
    tier = _RISK_TIERS[min(score, len(_RISK_TIERS) - 1)]
    reversibility = explicit_reversibility or classification.reversibility
    approval_required = classification.approval_required or bool(require_confirm) or tier in {"high", "critical"}
    return RiskClassification(
        risk_tier=tier,
        reversibility=reversibility,
        approval_required=approval_required,
        score=score,
        reason=classification.reason + (f"; explicit override tier={explicit_tier}" if explicit_tier else ""),
    )
