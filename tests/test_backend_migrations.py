"""Focused tests for the fixed Backend Alembic baseline."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = ROOT / "services" / "backend" / "alembic.ini"

BACKEND_TABLES = {
    "action_snapshots",
    "agent_feedback",
    "agent_trajectories",
    "approvals",
    "automation_rules",
    "biometric_readings",
    "bridge_status_log",
    "classifier_cache",
    "conversations",
    "device_action_log",
    "devices",
    "dismiss_log",
    "frequent_places",
    "messages",
    "mobile_devices",
    "purchase_history",
    "rollback_log",
    "scenes",
    "scheduled_blocks",
    "shopping_items",
    "system_stats",
    "task_preferences",
    "tasks",
    "threshold_adjustments",
    "threshold_drift_log",
    "timeseries",
    "users",
    "voice_capsule_play_log",
    "voice_capsules",
    "voice_events",
}

LEGACY_ADDITIVE_COLUMNS = {
    "voice_events": {"motion_id"},
    "tasks": {
        "cognitive_load",
        "preferred_time_slot",
        "deadline",
        "source",
        "source_ref",
        "confidence",
        "proposal_status",
        "dismissed_at",
        "dismiss_reason",
        "locked_start",
    },
    "shopping_items": {"store_category"},
    "devices": {"model_id", "manufacturer", "link_quality", "last_seen_reported"},
    "automation_rules": {"risk_tier", "reversibility", "approval_required", "auto_rollback_window_seconds"},
}


def _run_alembic(database: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def _columns(database: Path, table: str) -> dict[str, str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {row[1]: row[2] for row in rows}


def _schema_fingerprint(database: Path) -> list[tuple[str, str, str | None]]:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()


def test_fixed_baseline_excludes_then_adds_legacy_columns(tmp_path):
    database = tmp_path / "baseline.db"

    _run_alembic(database, "upgrade", "0001_backend_baseline")

    assert _tables(database) - {"alembic_version"} == BACKEND_TABLES
    for table, additive_columns in LEGACY_ADDITIVE_COLUMNS.items():
        assert additive_columns.isdisjoint(_columns(database, table))

    _run_alembic(database, "upgrade", "head")

    for table, additive_columns in LEGACY_ADDITIVE_COLUMNS.items():
        columns = _columns(database, table)
        assert additive_columns <= columns.keys()
    assert _columns(database, "tasks")["deadline"] == "DATETIME"
    assert _columns(database, "tasks")["dismissed_at"] == "DATETIME"
    assert _columns(database, "tasks")["locked_start"] == "DATETIME"
    assert _columns(database, "devices")["last_seen_reported"] == "DATETIME"


def test_fresh_upgrade_is_at_head_idempotent_and_matches_metadata(tmp_path):
    database = tmp_path / "fresh.db"

    _run_alembic(database, "upgrade", "head")
    before = _schema_fingerprint(database)

    current = _run_alembic(database, "current")
    assert "0002_legacy_additive_columns (head)" in current.stdout

    _run_alembic(database, "upgrade", "head")
    assert _schema_fingerprint(database) == before

    check = _run_alembic(database, "check")
    assert "No new upgrade operations detected" in check.stdout
