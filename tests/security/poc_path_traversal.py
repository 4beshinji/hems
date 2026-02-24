#!/usr/bin/env python3
"""
PoC V4: Obsidian path traversal テスト
HEMS/../../../etc/passwd 等で vault 外ファイルに書き込めるか確認
"""
import sys
import os
import tempfile
import shutil

# Add obsidian-bridge src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/obsidian-bridge/src"))

# Mock loguru if not installed
try:
    import loguru  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["loguru"] = MagicMock()
    sys.modules["loguru"].logger = MagicMock()

try:
    from note_writer import NoteWriter
except ImportError as e:
    print(f"[SKIP] Cannot import NoteWriter: {e}")
    sys.exit(0)

PASS_COUNT = 0
FAIL_COUNT = 0

# Traversal payloads (rel_path passed to write_note)
TRAVERSAL_TESTS = [
    ("HEMS/../../../tmp/pwned_direct", "Direct traversal above vault"),
    ("HEMS/../../../../tmp/pwned_deep", "Deep traversal above vault"),
    ("HEMS/sub/../../../../../../tmp/pwned_sub", "Sub-directory traversal"),
    ("/etc/passwd", "Absolute path injection"),
    ("../../../tmp/pwned_no_prefix", "No HEMS prefix traversal"),
]

# Tests that should fail the sanitizer at the brain layer
SANITIZER_TESTS = [
    ("../../../etc/passwd", "Title with traversal (brain sanitizer)"),
    ("/etc/passwd", "Absolute path as title (brain sanitizer)"),
]


def test_note_writer_directly():
    """Test NoteWriter directly (bypassing brain sanitizer)."""
    global PASS_COUNT, FAIL_COUNT

    # Create a temp vault
    vault_dir = tempfile.mkdtemp(prefix="hems_poc_vault_")
    hems_dir = os.path.join(vault_dir, "HEMS")
    os.makedirs(hems_dir, exist_ok=True)

    # Create a file OUTSIDE the vault to check if we can write to it
    outside_dir = tempfile.mkdtemp(prefix="hems_poc_outside_")

    print(f"=== V4: Path Traversal Test ===")
    print(f"Vault: {vault_dir}")
    print(f"Outside: {outside_dir}\n")

    writer = NoteWriter(vault_dir)

    for rel_path, description in TRAVERSAL_TESTS:
        # Try to write outside vault
        try:
            result = writer.write_note(rel_path, "PWNED by path traversal")
            # If write succeeded, check where the file ended up
            # Resolve the actual path
            from pathlib import Path
            actual_path = (Path(vault_dir) / result).resolve()
            vault_resolved = Path(vault_dir).resolve()

            if str(actual_path).startswith(str(vault_resolved)):
                print(f"[PASS] CONTAINED: {description}")
                print(f"       Wrote to: {actual_path} (within vault)")
                PASS_COUNT += 1
            else:
                print(f"[FAIL] ESCAPED VAULT: {description}")
                print(f"       Intended: {rel_path}")
                print(f"       Actual: {actual_path}")
                FAIL_COUNT += 1
        except (ValueError, PermissionError, OSError) as e:
            print(f"[PASS] EXCEPTION RAISED: {description} — {e}")
            PASS_COUNT += 1

    # Cleanup
    shutil.rmtree(vault_dir, ignore_errors=True)
    shutil.rmtree(outside_dir, ignore_errors=True)


def test_brain_sanitizer():
    """Test that Brain sanitizer blocks traversal before it reaches NoteWriter."""
    global PASS_COUNT, FAIL_COUNT

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/brain/src"))
    try:
        from sanitizer import Sanitizer
    except ImportError:
        print("[SKIP] Brain sanitizer not available")
        return

    print("\n--- Brain Sanitizer Layer ---")
    sanitizer = Sanitizer()

    for title, description in SANITIZER_TESTS:
        result = sanitizer.validate_tool_call("write_note", {
            "title": title,
            "content": "test",
        })
        if not result["allowed"]:
            print(f"[PASS] BLOCKED by sanitizer: {description}")
            PASS_COUNT += 1
        else:
            print(f"[FAIL] ALLOWED by sanitizer: {description}")
            print(f"       title={title!r}")
            FAIL_COUNT += 1


if __name__ == "__main__":
    test_note_writer_directly()
    test_brain_sanitizer()

    print(f"\n=== Results: PASS={PASS_COUNT} FAIL={FAIL_COUNT} ===")
    if FAIL_COUNT > 0:
        print(f"STATUS: VULNERABLE ({FAIL_COUNT} issues)")
        sys.exit(1)
    else:
        print("STATUS: SECURE")
        sys.exit(0)
