"""Brain-side Human-in-the-Loop (HITL) approval subsystem."""

from approval.action_risk_classifier import RiskClassification, classify_action, classify_rule
from approval.audit_logger import ApprovalAuditLogger
from approval.client import ApprovalClient
from approval.gate import ApprovalGate
from approval.rollback_executor import RollbackExecutor
from approval.rollback_planner import RollbackPlan, build_rollback_plan
from approval.verification_watcher import VerificationWatcher

__all__ = [
    "ApprovalAuditLogger",
    "ApprovalClient",
    "ApprovalGate",
    "RiskClassification",
    "RollbackExecutor",
    "RollbackPlan",
    "VerificationWatcher",
    "build_rollback_plan",
    "classify_action",
    "classify_rule",
]
