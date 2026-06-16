#!/usr/bin/env python3
"""Generate secure random values for placeholder secrets in .env.

Usage:
    python infra/scripts/init_env.py
    python infra/scripts/init_env.py --dry-run
    python infra/scripts/init_env.py --force

Behavior:
    - If ``.env`` does not exist, it is created by copying ``env.example``.
    - For each configured secret key, the current value is inspected.
    - When ``only_missing`` (default), values that are empty or set to a
      placeholder (``CHANGE_ME_BEFORE_USE`` or ``CHANGE_ME``) are replaced
      with a freshly generated random string.
    - With ``--force``, existing non-placeholder values are also overwritten.
    - With ``--dry-run``, the script prints what it would change but does not
      write to ``.env``.

This script is intentionally dependency-light (stdlib only) so it can run on a
fresh clone before Docker or virtualenv are set up.
"""

from __future__ import annotations

import argparse
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = ROOT / "env.example"
ENV_FILE = ROOT / ".env"

# key -> token length in bytes (urlsafe output is ~4/3 * bytes)
SECRETS = {
    "POSTGRES_PASSWORD": 32,
    "MQTT_PASS": 32,
    "BACKEND_API_KEY": 32,
    "HEMS_INTERNAL_TOKEN": 32,
}

_PLACEHOLDERS = frozenset({"", "CHANGE_ME_BEFORE_USE", "CHANGE_ME"})


def generate(length: int) -> str:
    """Return a URL-safe random string of the requested byte length."""
    return secrets.token_urlsafe(length)


def _is_placeholder(value: str | None) -> bool:
    return value is None or value.strip() in _PLACEHOLDERS


def _get_current_value(content: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}\s*=\s*(.*)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _set_value(content: str, key: str, value: str) -> str:
    pattern = rf"^{re.escape(key)}\s*=\s*.*$"
    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
    # Key not present — append at the end with a small header.
    return content.rstrip() + f"\n\n# Added by init_env.py on {datetime.now(UTC).isoformat()}\n{key}={value}\n"


def init_env(*, only_missing: bool = True, dry_run: bool = False) -> list[tuple[str, str, str | None]]:
    """Generate secrets and (optionally) write them to ``.env``.

    Returns a list of tuples ``(key, new_value, old_value)`` for every key
    that was changed or would be changed.
    """
    if not ENV_FILE.exists():
        if not ENV_EXAMPLE.exists():
            raise FileNotFoundError(
                f"Neither {ENV_FILE} nor {ENV_EXAMPLE} exists. "
                "Run this script from the repository root."
            )
        if dry_run:
            print(f"Would create {ENV_FILE} from {ENV_EXAMPLE}")
        else:
            ENV_FILE.write_text(ENV_EXAMPLE.read_text(), encoding="utf-8")
            print(f"Created {ENV_FILE} from {ENV_EXAMPLE}")

    content = ENV_FILE.read_text(encoding="utf-8")
    changes: list[tuple[str, str, str | None]] = []

    for key, length in SECRETS.items():
        current = _get_current_value(content, key)
        if only_missing and not _is_placeholder(current):
            continue

        new_value = generate(length)
        changes.append((key, new_value, current))
        content = _set_value(content, key, new_value)

    if changes:
        if dry_run:
            print(f"Would update {ENV_FILE} with the following changes:")
        else:
            ENV_FILE.write_text(content, encoding="utf-8")
            print(f"Updated {ENV_FILE}")
        for key, new_value, old_value in changes:
            old_display = "<empty>" if _is_placeholder(old_value) else old_value
            print(f"  {key}: {old_display} -> {new_value}")
    else:
        print(f"No changes needed for {ENV_FILE} (all secrets already set)")

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate secure random secrets for HEMS .env file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without writing to .env",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-placeholder values (use with care)",
    )
    args = parser.parse_args()

    try:
        init_env(only_missing=not args.force, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=__import__("sys").stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
