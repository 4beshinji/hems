"""Brain classifiers — shopping_category, event lead_time, etc.

Pipeline (per velvety-chasing-pebble plan §3):
  seed rule → cache hit → LLM fallback (P3) → None
Cache is promoted to rule when hit_count ≥ 3 (P5).
"""
from .cache import ClassifierCache
from .event_classifier import EventClassifier, EventPlan
from .rule_promoter import RulePromoter
from .shopping_classifier import ShoppingClassifier

__all__ = [
    "ClassifierCache", "EventClassifier", "EventPlan",
    "RulePromoter", "ShoppingClassifier",
]
