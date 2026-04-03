"""Serendipity-focused motion retriever for avatar gesture selection.

Scoring pipeline:
  final = 1.0 * bm25 + 0.8 * tone_affinity + 0.5 * (1 - decay) + 0.3 * novelty
  → temperature softmax sampling (not argmax)
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger


@dataclass
class MotionEntry:
    id: str
    file: str
    name: str
    description: str
    tags: list[str]
    duration: float
    category: str
    tokens: set[str] = field(default_factory=set)


# Tone → category affinity bias
AFFINITY: dict[str, dict[str, float]] = {
    "alert": {"alert": 1.0, "reaction": 0.3},
    "caring": {"greeting": 0.6, "reaction": 0.5, "emote": 0.4, "gesture": 0.2},
    "humorous": {"gesture": 0.5, "emote": 0.7, "reaction": 0.3, "greeting": 0.2},
    "neutral": {"gesture": 0.3, "reaction": 0.3, "idle": 0.2, "greeting": 0.1},
}

# Tone → sampling temperature (higher = more exploratory/serendipitous)
TEMPERATURE: dict[str, float] = {
    "humorous": 1.5,
    "alert": 0.5,
    "neutral": 0.8,
    "caring": 1.0,
}

DECAY_HALF_LIFE = 20  # uses


def _find_config_dir() -> Path:
    """Resolve config directory: /config (Docker) or walk up to project root."""
    docker_config = Path("/config")
    if docker_config.is_dir():
        return docker_config
    # Walk up from this file to find config/
    p = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = p / "config"
        if candidate.is_dir():
            return candidate
        p = p.parent
    return Path("config")


def _tokenize(text: str) -> set[str]:
    """Japanese-friendly tokenizer: character bigrams + whitespace/punctuation split.

    No MeCab needed for <200 motion entries. Bigrams capture sufficient
    overlap for Japanese text (e.g., '挨拶' → {'挨拶'}, '注意' → {'注意'}).
    """
    # Remove punctuation, normalize
    cleaned = re.sub(r"[。、！？\s.,!?\-\n]+", " ", text).strip()
    tokens: set[str] = set()
    # Whitespace-split words
    for word in cleaned.split():
        if len(word) >= 2:
            tokens.add(word)
        # Character bigrams
        for i in range(len(word) - 1):
            tokens.add(word[i : i + 2])
    return tokens


class MotionRetriever:
    def __init__(self, config_path: Optional[Path] = None):
        self.motions: list[MotionEntry] = []
        self._usage: dict[str, dict] = {}  # {motion_id: {count, last_seq}}
        self._global_seq = 0

        path = config_path or _find_config_dir() / "motions.yaml"
        if not path.exists():
            logger.warning(f"Motion config not found: {path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load motions.yaml: {e}")
            return

        for m in data.get("motions", []):
            entry = MotionEntry(
                id=m["id"],
                file=m["file"],
                name=m.get("name", ""),
                description=m.get("description", ""),
                tags=m.get("tags", []),
                duration=m.get("duration", 2.0),
                category=m.get("category", "gesture"),
            )
            # Precompute tokens from description + tags + name
            text = f"{entry.description} {entry.name} {' '.join(entry.tags)}"
            entry.tokens = _tokenize(text)
            self.motions.append(entry)
            self._usage[entry.id] = {"count": 0, "last_seq": 0}

        logger.info(f"Loaded {len(self.motions)} motions from {path}")

    def select(self, text: str, tone: str = "neutral") -> Optional[str]:
        """Select a motion_id for the given speech text and tone.

        Uses serendipity-focused scoring:
        1. BM25-like keyword overlap
        2. Tone→category affinity
        3. Usage decay (penalize recent)
        4. Novelty bonus (reward rare)
        5. Temperature softmax sampling
        """
        if not self.motions:
            return None

        query_tokens = _tokenize(text)
        if not query_tokens:
            # No useful tokens — fall back to tone-only selection
            query_tokens = set()

        scores: list[tuple[str, float]] = []
        for m in self.motions:
            bm25 = self._score_bm25(query_tokens, m)
            affinity = self._tone_affinity(tone, m.category)
            decay = self._usage_decay(m.id)
            novelty = self._novelty_bonus(m.id)

            final = 1.0 * bm25 + 0.8 * affinity + 0.5 * (1 - decay) + 0.3 * novelty
            scores.append((m.id, final))

        temperature = TEMPERATURE.get(tone, 0.8)
        selected = self._softmax_sample(scores, temperature)

        if selected:
            self._record_usage(selected)

        return selected

    def _score_bm25(self, query_tokens: set[str], motion: MotionEntry) -> float:
        """Simplified BM25: token overlap normalized by motion token count."""
        if not query_tokens or not motion.tokens:
            return 0.0
        overlap = len(query_tokens & motion.tokens)
        return overlap / (len(motion.tokens) + 5)  # +5 smoothing

    def _tone_affinity(self, tone: str, category: str) -> float:
        """Score based on tone→category alignment."""
        return AFFINITY.get(tone, {}).get(category, 0.0)

    def _usage_decay(self, motion_id: str) -> float:
        """Exponential decay penalty: higher = more recently used."""
        usage = self._usage.get(motion_id)
        if not usage or usage["count"] == 0:
            return 0.0
        uses_since = self._global_seq - usage["last_seq"]
        return math.exp(-0.693 * uses_since / DECAY_HALF_LIFE)

    def _novelty_bonus(self, motion_id: str) -> float:
        """Reward rarely-used motions: log(1 + 1/count)."""
        usage = self._usage.get(motion_id)
        if not usage or usage["count"] == 0:
            return math.log(2)  # max bonus for never-used
        return math.log(1 + 1 / usage["count"])

    def _softmax_sample(
        self, scores: list[tuple[str, float]], temperature: float
    ) -> Optional[str]:
        """Temperature-scaled softmax sampling. Pure Python, no numpy."""
        if not scores:
            return None
        # Subtract max for numerical stability
        max_s = max(s for _, s in scores)
        exps = []
        for mid, s in scores:
            exps.append((mid, math.exp((s - max_s) / max(temperature, 0.01))))
        total = sum(e for _, e in exps)
        if total == 0:
            return random.choice([mid for mid, _ in scores])

        r = random.random() * total
        cumulative = 0.0
        for mid, e in exps:
            cumulative += e
            if r <= cumulative:
                return mid
        return exps[-1][0]

    def _record_usage(self, motion_id: str) -> None:
        self._global_seq += 1
        if motion_id in self._usage:
            self._usage[motion_id]["count"] += 1
            self._usage[motion_id]["last_seq"] = self._global_seq
