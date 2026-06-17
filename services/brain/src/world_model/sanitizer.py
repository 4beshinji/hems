"""Text sanitization helpers for MQTT-sourced strings before LLM context."""

import re

# Prompt injection patterns to strip from MQTT-sourced text before LLM context
_INJECTION_RE = re.compile(
    r"\[SYSTEM|<\|system\|>|###\s*(System|Instruction|Override)|"
    r"Ignore\s+previous\s+instructions|Override\s+(all\s+)?(previous\s+)?instructions|"
    r"\[INST\]|<\|im_start\|>|<\|im_end\|>",
    re.IGNORECASE,
)


def _sanitize_text(text: str, max_len: int = 200) -> str:
    """Sanitize MQTT-sourced text before including it in LLM context.

    - Removes prompt-injection marker patterns
    - Collapses newlines (prevents multi-line injection)
    - Truncates to max_len
    """
    if not isinstance(text, str):
        return str(text)[:max_len]
    cleaned = _INJECTION_RE.sub("[FILTERED]", text)
    cleaned = " ".join(cleaned.splitlines()).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "…"
    return cleaned
