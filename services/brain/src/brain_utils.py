"""
Shared utilities for HEMS Brain modules.
"""

import json
import re
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------- #
#  Voice / TTS constants                                                       #
# --------------------------------------------------------------------------- #

SPEAK_CHUNK_LIMIT = 70  # max chars per speak tool call


# --------------------------------------------------------------------------- #
#  Text splitting                                                              #
# --------------------------------------------------------------------------- #


def split_for_speak(text: str, limit: int = SPEAK_CHUNK_LIMIT) -> list[str]:
    """Split text into chunks of at most *limit* characters, breaking at 。."""
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    sentences = re.split(r"(?<=。)", text)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) <= limit:
            buf += s
        else:
            if buf:
                chunks.append(buf)
            if len(s) > limit:
                while s:
                    chunks.append(s[:limit])
                    s = s[limit:]
                buf = ""
            else:
                buf = s
    if buf:
        chunks.append(buf)
    return chunks


# --------------------------------------------------------------------------- #
#  Timestamp parsing                                                           #
# --------------------------------------------------------------------------- #


def parse_iso_ts(value: Any) -> float | None:
    """Parse an ISO8601 string (or numeric epoch) to epoch seconds.

    Accepts:
    - ISO8601 strings, including trailing "Z" (e.g. "2026-04-30T12:34:56Z")
    - Numeric epoch (seconds or milliseconds)
    Returns None if the input is not parseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Heuristic: > 1e11 means milliseconds, else seconds
        return float(value) / 1000 if value > 1e11 else float(value)
    if not isinstance(value, str):
        return None
    try:
        s = value.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
#  Provider-specific tool-call message formatting                             #
# --------------------------------------------------------------------------- #


def format_tool_call_blocks(provider: str, calls: list) -> list[dict]:
    """Build assistant `tool_calls` blocks for the given LLM provider.

    Ollama keeps `arguments` as a dict; OpenAI-compatible providers expect a
    JSON-encoded string. Shared by the cognitive loop and the chat server.
    """
    blocks = []
    for tc in calls:
        fn = tc["function"]
        arguments = fn["arguments"] if provider == "ollama" else json.dumps(fn["arguments"], ensure_ascii=False)
        blocks.append(
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": fn["name"], "arguments": arguments},
            }
        )
    return blocks


def format_tool_result_msg(provider: str, tool_name: str, tool_call_id: str, content: str) -> dict:
    """Build a provider-specific `role: tool` result message.

    Ollama identifies the result by `name`; OpenAI by `tool_call_id`.
    """
    msg = {"role": "tool", "content": content}
    if provider == "ollama":
        msg["name"] = tool_name
    else:
        msg["tool_call_id"] = tool_call_id
    return msg
