"""Generic bank — reusable short clips with no specific trigger.

Played manually (e.g. on app launch) or as fallback when the phone can't
match an outgoing situation to a specific capsule clip.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenericSpec:
    id: str      # deterministic clip id, used in the output filename
    tag: str     # semantic hint the phone matches against
    tone: str
    text: str    # seed transcript — passed through PersonaRewriter

    def transcript_seed(self) -> str:
        return self.text


def default_bank() -> list[GenericSpec]:
    """Minimum viable bank — 5 tags × 1 variation.

    Plan §10 marks multi-variation as an open decision; sticking with one
    clip per tag keeps capsule size predictable while the phone-side UX
    settles.
    """
    return [
        GenericSpec(id="ack_yes", tag="ack_yes", tone="neutral", text="はい。"),
        GenericSpec(id="ack_no", tag="ack_no", tone="neutral", text="いいえ。"),
        GenericSpec(id="thinking", tag="thinking", tone="neutral", text="うーん、そうですね。"),
        GenericSpec(id="hello", tag="hello", tone="caring", text="こんにちは。"),
        GenericSpec(id="goodbye", tag="goodbye", tone="caring", text="いってらっしゃい。"),
    ]
