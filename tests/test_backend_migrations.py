"""Focused tests for the fixed Backend Alembic baseline."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

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


def _run_bootstrap(database: Path, *, succeeds: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env["PYTHONPATH"] = str(ROOT / "services" / "backend")
    result = subprocess.run(
        [sys.executable, "-m", "migrations.bootstrap"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if succeeds:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, "bootstrap unexpectedly succeeded"
    return result


def _create_full_legacy(database: Path, *, incompatible_tasks_title: bool = False) -> None:
    from models import Base

    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    if incompatible_tasks_title:
        metadata.tables["tasks"].c.title.type = sa.Integer()

    engine = sa.create_engine(f"sqlite:///{database}")
    metadata.create_all(engine)
    engine.dispose()


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

    _run_bootstrap(database)
    before = _schema_fingerprint(database)

    current = _run_alembic(database, "current")
    assert "0002_legacy_additive_columns (head)" in current.stdout

    _run_alembic(database, "upgrade", "head")
    assert _schema_fingerprint(database) == before

    check = _run_alembic(database, "check")
    assert "No new upgrade operations detected" in check.stdout


def test_bootstrap_reconciles_full_legacy_and_preserves_unknown_schema(tmp_path):
    database = tmp_path / "full-legacy.db"
    _create_full_legacy(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO tasks (title) VALUES ('sentinel-full')")
        connection.execute("ALTER TABLE tasks ADD COLUMN legacy_extra TEXT")
        connection.execute("CREATE TABLE external_plugin_data (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO external_plugin_data (value) VALUES ('keep-me')")
        connection.commit()

    _run_bootstrap(database)

    assert _tables(database) >= BACKEND_TABLES | {"alembic_version", "external_plugin_data"}
    assert "legacy_extra" in _columns(database, "tasks")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT title FROM tasks").fetchall() == [("sentinel-full",)]
        assert connection.execute("SELECT value FROM external_plugin_data").fetchall() == [("keep-me",)]
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0002_legacy_additive_columns",
        )

    before = _schema_fingerprint(database)
    _run_bootstrap(database)
    assert _schema_fingerprint(database) == before


def test_bootstrap_reconciles_partial_legacy_schema(tmp_path):
    database = tmp_path / "partial-legacy.db"
    _run_alembic(database, "upgrade", "0001_backend_baseline")
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO tasks (title) VALUES ('sentinel-partial')")
        connection.execute("ALTER TABLE voice_events ADD COLUMN motion_id VARCHAR")
        connection.execute("ALTER TABLE tasks ADD COLUMN cognitive_load INTEGER")
        connection.execute("DROP TABLE bridge_status_log")
        connection.execute("DROP TABLE alembic_version")
        connection.commit()

    _run_bootstrap(database)

    assert _tables(database) - {"alembic_version"} == BACKEND_TABLES
    for table, additive_columns in LEGACY_ADDITIVE_COLUMNS.items():
        assert additive_columns <= _columns(database, table).keys()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT title FROM tasks").fetchall() == [("sentinel-partial",)]


def test_bootstrap_rejects_incompatible_known_column_type(tmp_path):
    database = tmp_path / "incompatible.db"
    _create_full_legacy(database, incompatible_tasks_title=True)

    result = _run_bootstrap(database, succeeds=False)

    assert "Incompatible legacy column type for tasks.title" in result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == []


def test_bootstrap_rejects_missing_required_baseline_column(tmp_path):
    database = tmp_path / "missing-required.db"
    _run_alembic(database, "upgrade", "0001_backend_baseline")
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE tasks DROP COLUMN description")
        connection.execute("DROP TABLE alembic_version")
        connection.commit()

    result = _run_bootstrap(database, succeeds=False)

    assert "Legacy table tasks is missing required baseline columns: description" in result.stderr


def test_bootstrap_rejects_unknown_alembic_revision(tmp_path):
    database = tmp_path / "unknown-revision.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('unknown_revision')")
        connection.commit()

    result = _run_bootstrap(database, succeeds=False)

    assert "Can't locate revision identified by 'unknown_revision'" in result.stderr
