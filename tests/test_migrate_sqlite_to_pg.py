"""
Unit tests for infra/scripts/migrate_sqlite_to_pg.py.

Covers:
- dry-run row counting (temp SQLite fixture)
- Type conversion functions (JSON, timestamp, bool)
- id/setval max-id logic
- Row transformation pipeline
- PG-dependent code paths are mocked or marked @pytest.mark.integration
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure script is importable from the tests/ directory.
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "scripts" / "migrate_sqlite_to_pg.py"

# Import the module by spec so we don't rely on a package install.
import importlib.util

spec = importlib.util.spec_from_file_location("migrate_sqlite_to_pg", _SCRIPT)
mig = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mig)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def backend_db(tmp_path):
    """Temp SQLite DB with a subset of backend tables populated with test rows."""
    db_path = tmp_path / "backend.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            is_completed INTEGER DEFAULT 0,
            created_at TEXT,
            completed_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            vendor TEXT,
            kind TEXT DEFAULT 'actuator',
            capabilities TEXT DEFAULT '[]',
            last_state TEXT DEFAULT '{}',
            last_value TEXT DEFAULT '{}'
        )"""
    )
    # Seed data
    conn.execute("INSERT INTO tasks VALUES (1, 'Buy milk', 'Go to supermarket', 0, '2026-01-01 09:00:00', NULL)")
    conn.execute(
        "INSERT INTO tasks VALUES (2, 'Read book', 'Chapter 3', 1, '2026-01-02 10:00:00', '2026-01-02 12:00:00')"
    )
    conn.execute("INSERT INTO users VALUES (1, 'alice', 1, '2026-01-01 08:00:00')")
    conn.execute(
        """INSERT INTO devices VALUES (
            1, 'tapo.desk_plug', 'tapo', 'actuator',
            '["on_off","power_monitor"]',
            '{"on": true}',
            '{}'
        )"""
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture()
def brain_db(tmp_path):
    """Temp SQLite DB with brain event_store tables."""
    db_path = tmp_path / "brain.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE world_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT NOT NULL,
            topic TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            subject_ref TEXT,
            data TEXT DEFAULT '{}'
        )"""
    )
    conn.execute(
        """CREATE TABLE llm_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            cycle_duration_sec REAL,
            iterations INTEGER,
            total_tool_calls INTEGER,
            trigger_events TEXT DEFAULT '[]',
            tool_calls TEXT DEFAULT '[]',
            world_state_snapshot TEXT DEFAULT '{}',
            cause_event_id INTEGER REFERENCES world_events(id),
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            gpu_util_pct REAL,
            gpu_power_w REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE raw_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            zone TEXT,
            event_type TEXT NOT NULL,
            source_device TEXT,
            data TEXT DEFAULT '{}'
        )"""
    )
    conn.execute(
        """CREATE TABLE hourly_aggregates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hub_id TEXT NOT NULL DEFAULT 'hems-brain',
            period_start TEXT NOT NULL,
            zones TEXT DEFAULT '{}',
            tasks_created INTEGER DEFAULT 0,
            llm_cycles INTEGER DEFAULT 0,
            device_health TEXT DEFAULT '{}'
        )"""
    )
    conn.execute(
        """CREATE TABLE aggregation_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_aggregated_hour TEXT,
            last_run_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE intervention_efficacy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            zone TEXT NOT NULL,
            trigger_metric TEXT NOT NULL,
            baseline_value REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            post_value REAL,
            window_sec INTEGER NOT NULL DEFAULT 1800,
            verdict TEXT,
            evaluated_at TEXT
        )"""
    )
    # Seed
    conn.execute(
        """INSERT INTO world_events VALUES (
            1, '2026-01-01 09:00:00', 'sensor', 'office/desk/temp', 'abc123', NULL, '{"temp": 22}'
        )"""
    )
    conn.execute(
        """INSERT INTO llm_decisions VALUES (
            1, '2026-01-01 09:01:00', 10.5, 3, 5,
            '[{"type":"sensor"}]', '[{"tool":"speak"}]', '{"zone":"desk"}',
            1, 100, 50, 45.2, 120.0
        )"""
    )
    conn.execute(
        """INSERT INTO raw_events VALUES (
            1, '2026-01-01 09:00:30', 'desk', 'temperature', 'thermometer', '{"value": 22.5}'
        )"""
    )
    conn.execute(
        """INSERT INTO hourly_aggregates VALUES (
            1, 'hems-brain', '2026-01-01 09:00:00', '{"desk": 5}', 2, 4, '{"tapo.desk": "ok"}'
        )"""
    )
    conn.execute("INSERT INTO aggregation_state VALUES (1, '2026-01-01 09:00:00', '2026-01-01 09:01:00')")
    conn.execute(
        """INSERT INTO intervention_efficacy VALUES (
            1, 'task-001', 'desk', 'temperature', 25.0,
            '2026-01-01 09:00:00', NULL, NULL, 1800, NULL, NULL
        )"""
    )
    conn.commit()
    conn.close()
    return str(db_path)


# ---------------------------------------------------------------------------
# Type conversion tests
# ---------------------------------------------------------------------------


class TestConvertTimestamp:
    def test_none_returns_none(self):
        assert mig.convert_timestamp(None) is None

    def test_empty_string_returns_none(self):
        assert mig.convert_timestamp("") is None

    def test_sqlite_naive_datetime(self):
        result = mig.convert_timestamp("2026-01-01 09:00:00")
        assert "+00:00" in result or "Z" in result or result.endswith("+00:00")
        assert "2026-01-01T09:00:00" in result

    def test_sqlite_naive_datetime_with_microseconds(self):
        result = mig.convert_timestamp("2026-01-01 09:00:00.123456")
        assert "2026-01-01" in result
        assert "09:00:00" in result

    def test_already_aware_datetime(self):
        dt = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        result = mig.convert_timestamp(dt)
        assert "2026-01-01" in result
        assert "09:00:00" in result

    def test_isoformat_string(self):
        result = mig.convert_timestamp("2026-01-01T09:00:00")
        assert "2026-01-01" in result

    def test_passthrough_non_timestamp(self):
        # Non-timestamp strings are passed through unchanged if unrecognised
        result = mig.convert_timestamp("not-a-date")
        # Should not raise and should return the input unchanged
        assert result == "not-a-date"


class TestConvertJson:
    def test_none_returns_none(self):
        assert mig.convert_json(None) is None

    def test_empty_string_returns_none(self):
        assert mig.convert_json("") is None

    def test_json_string_to_dict(self):
        result = mig.convert_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_json_string_to_list(self):
        result = mig.convert_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_already_dict_passthrough(self):
        d = {"a": 1}
        assert mig.convert_json(d) is d

    def test_already_list_passthrough(self):
        lst = [1, 2]
        assert mig.convert_json(lst) is lst

    def test_invalid_json_returns_string(self):
        bad = "{not valid json}"
        result = mig.convert_json(bad)
        assert result == bad  # kept as string, logged warning

    def test_nested_json(self):
        result = mig.convert_json('{"nested": {"a": [1,2,3]}}')
        assert result == {"nested": {"a": [1, 2, 3]}}

    def test_empty_object(self):
        assert mig.convert_json("{}") == {}

    def test_empty_array(self):
        assert mig.convert_json("[]") == []


class TestConvertBool:
    def test_none(self):
        assert mig.convert_bool(None) is None

    def test_int_1_to_true(self):
        assert mig.convert_bool(1) is True

    def test_int_0_to_false(self):
        assert mig.convert_bool(0) is False

    def test_bool_true_passthrough(self):
        assert mig.convert_bool(True) is True

    def test_bool_false_passthrough(self):
        assert mig.convert_bool(False) is False

    def test_other_int(self):
        assert mig.convert_bool(42) is True


# ---------------------------------------------------------------------------
# SQLite helper tests
# ---------------------------------------------------------------------------


class TestSqliteHelpers:
    def test_sqlite_count(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        assert mig.sqlite_count(conn, "tasks") == 2
        assert mig.sqlite_count(conn, "users") == 1
        conn.close()

    def test_sqlite_count_missing_table(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        assert mig.sqlite_count(conn, "nonexistent_table") == 0
        conn.close()

    def test_sqlite_table_exists(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        assert mig.sqlite_table_exists(conn, "tasks") is True
        assert mig.sqlite_table_exists(conn, "nope") is False
        conn.close()

    def test_sqlite_columns(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        cols = mig.sqlite_columns(conn, "tasks")
        assert "id" in cols
        assert "title" in cols
        assert "created_at" in cols
        conn.close()

    def test_sqlite_read_all(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        rows = mig.sqlite_read_all(conn, "tasks")
        assert len(rows) == 2
        assert rows[0]["title"] == "Buy milk"
        assert rows[1]["title"] == "Read book"
        conn.close()

    def test_sqlite_readonly(self, backend_db):
        """Connection should be read-only — writes must fail."""
        conn = mig.sqlite_connect(backend_db)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO tasks (title) VALUES ('should fail')")
        conn.close()


# ---------------------------------------------------------------------------
# Row transformation tests
# ---------------------------------------------------------------------------


class TestTransformRow:
    def test_timestamp_conversion(self):
        row = {"id": 1, "created_at": "2026-01-01 09:00:00", "title": "test"}
        result = mig.transform_row(row, "tasks")
        assert "+00:00" in result["created_at"] or "Z" in result["created_at"]
        assert result["title"] == "test"

    def test_bool_conversion(self):
        row = {"id": 1, "is_completed": 0, "is_queued": 1}
        result = mig.transform_row(row, "tasks")
        assert result["is_completed"] is False
        assert result["is_queued"] is True

    def test_json_column_conversion(self):
        row = {
            "id": 1,
            "capabilities": '["on_off", "brightness"]',
            "last_state": '{"on": true}',
            "vendor": "zigbee",
        }
        result = mig.transform_row(row, "devices", json_cols={"capabilities", "last_state"})
        assert result["capabilities"] == ["on_off", "brightness"]
        assert result["last_state"] == {"on": True}
        assert result["vendor"] == "zigbee"

    def test_null_timestamp_stays_null(self):
        row = {"id": 1, "completed_at": None, "created_at": "2026-01-01 08:00:00"}
        result = mig.transform_row(row, "tasks")
        assert result["completed_at"] is None

    def test_eventstore_jsonb_columns(self):
        row = {
            "id": 1,
            "timestamp": "2026-01-01 09:00:00",
            "trigger_events": '[{"type": "sensor"}]',
            "tool_calls": '[{"tool": "speak"}]',
            "world_state_snapshot": '{"zone": "desk"}',
            "cycle_duration_sec": 10.5,
        }
        json_cols = mig._JSONB_COLUMNS["llm_decisions"]
        result = mig.transform_row(row, "llm_decisions", json_cols=json_cols)
        assert result["trigger_events"] == [{"type": "sensor"}]
        assert result["tool_calls"] == [{"tool": "speak"}]
        assert result["world_state_snapshot"] == {"zone": "desk"}
        assert result["cycle_duration_sec"] == 10.5


# ---------------------------------------------------------------------------
# Dry-run tests (no PG required — mock pg_conn)
# ---------------------------------------------------------------------------


class TestDryRun:
    def _make_pg_mock(self, counts: dict[str, int] | None = None):
        """Return a mock pg_conn where pg_table_count returns specified counts."""
        counts = counts or {}

        def fake_count(conn, schema, table):
            return counts.get(table, 0)

        return MagicMock(), fake_count

    def test_backend_dry_run_counts_rows(self, backend_db):
        """dry-run should return (src_count, 0) for each table — no inserts."""
        pg_conn = MagicMock()
        with patch.object(mig, "pg_table_count", return_value=0):
            results = mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=True)

        assert "tasks" in results
        assert "users" in results
        assert "devices" in results
        src, inserted = results["tasks"]
        assert src == 2
        assert inserted == 0  # dry-run never inserts

        src, inserted = results["users"]
        assert src == 1
        assert inserted == 0

    def test_brain_dry_run_counts_rows(self, brain_db):
        """Event-store dry-run should count all 6 tables correctly."""
        pg_conn = MagicMock()
        with patch.object(mig, "pg_table_count", return_value=0):
            results = mig.migrate_eventstore(brain_db, pg_conn, "skip-nonempty", dry_run=True)

        assert results["world_events"] == (1, 0)
        assert results["llm_decisions"] == (1, 0)
        assert results["raw_events"] == (1, 0)
        assert results["hourly_aggregates"] == (1, 0)
        assert results["aggregation_state"] == (1, 0)
        assert results["intervention_efficacy"] == (1, 0)

    def test_dry_run_does_not_call_insert(self, backend_db):
        """pg_insert_rows must never be called in dry-run mode."""
        pg_conn = MagicMock()
        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows") as mock_insert:
                mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=True)
                mock_insert.assert_not_called()

    def test_dry_run_shows_pg_existing_counts(self, backend_db):
        """In dry-run the PG existing count should be fetched and reported."""
        pg_conn = MagicMock()
        pg_counts_called = []

        def count_spy(conn, schema, table):
            pg_counts_called.append(table)
            return 5  # pretend PG has 5 rows already

        with patch.object(mig, "pg_table_count", side_effect=count_spy):
            mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=True)

        assert "tasks" in pg_counts_called
        assert "users" in pg_counts_called


# ---------------------------------------------------------------------------
# Idempotence: skip-nonempty
# ---------------------------------------------------------------------------


class TestIdempotenceSkipNonempty:
    def test_skip_nonempty_skips_table_with_rows(self, backend_db):
        """If PG table has rows, skip-nonempty must skip and return (src, 0)."""
        pg_conn = MagicMock()

        def pg_count(conn, schema, table):
            if table == "tasks":
                return 5  # non-empty
            return 0

        with patch.object(mig, "pg_table_count", side_effect=pg_count):
            with patch.object(mig, "pg_insert_rows") as mock_insert:
                results = mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=False)
                # tasks table should be skipped
                _src, ins = results["tasks"]
                assert ins == 0
                # pg_insert_rows should not have been called for tasks
                calls = [call.args[2] for call in mock_insert.call_args_list]
                assert "tasks" not in calls


# ---------------------------------------------------------------------------
# Setval (sequence advance) logic
# ---------------------------------------------------------------------------


class TestSetval:
    def test_setval_advances_to_max_id(self):
        """pg_setval should call setval with max(id) from the table."""
        pg_conn = MagicMock()
        cursor = MagicMock()
        pg_conn.cursor.return_value = cursor

        # First fetchone: MAX(id) = 42
        # Second fetchone: seq name
        cursor.fetchone.side_effect = [
            {"id": 42},  # MAX(id)
            {"seq": "public.tasks_id_seq"},  # pg_get_serial_sequence
        ]

        mig.pg_setval(pg_conn, "public", "tasks")

        # Should have called setval(seq, 42)
        calls = [str(c) for c in cursor.execute.call_args_list]
        assert any("setval" in c for c in calls)
        pg_conn.commit.assert_called()

    def test_setval_skips_when_max_is_none(self):
        """If table is empty (MAX(id) = None), setval should not be called."""
        pg_conn = MagicMock()
        cursor = MagicMock()
        pg_conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": None}

        mig.pg_setval(pg_conn, "public", "tasks")

        # Only 1 execute call (the MAX query), no setval
        assert cursor.execute.call_count == 1

    def test_setval_handles_exception_gracefully(self):
        """pg_setval must not raise even if the DB call fails."""
        pg_conn = MagicMock()
        cursor = MagicMock()
        pg_conn.cursor.return_value = cursor
        cursor.execute.side_effect = Exception("DB error")

        # Should not raise
        mig.pg_setval(pg_conn, "public", "tasks")
        pg_conn.rollback.assert_called()


# ---------------------------------------------------------------------------
# Max-id calculation (standalone logic test, no DB)
# ---------------------------------------------------------------------------


class TestMaxIdLogic:
    def test_max_id_from_rows(self):
        """Verify we can compute max(id) from a list of row dicts."""
        rows = [{"id": 1, "title": "a"}, {"id": 5, "title": "b"}, {"id": 3, "title": "c"}]
        max_id = max(r["id"] for r in rows)
        assert max_id == 5

    def test_max_id_empty_rows(self):
        rows = []
        max_id = max((r["id"] for r in rows), default=None)
        assert max_id is None


# ---------------------------------------------------------------------------
# Event-store table ordering
# ---------------------------------------------------------------------------


class TestEventstoreOrdering:
    def test_world_events_before_llm_decisions(self):
        """world_events must appear before llm_decisions in migration order."""
        order = mig._EVENTSTORE_TABLE_ORDER
        assert order.index("world_events") < order.index("llm_decisions")

    def test_all_six_tables_present(self):
        expected = {
            "raw_events",
            "llm_decisions",
            "hourly_aggregates",
            "aggregation_state",
            "world_events",
            "intervention_efficacy",
        }
        assert set(mig._EVENTSTORE_TABLE_ORDER) == expected


# ---------------------------------------------------------------------------
# Backend table ordering
# ---------------------------------------------------------------------------


class TestBackendOrdering:
    def test_conversations_before_messages(self):
        order = mig._BACKEND_TABLE_ORDER
        assert order.index("conversations") < order.index("messages")

    def test_tasks_before_scheduled_blocks(self):
        order = mig._BACKEND_TABLE_ORDER
        assert order.index("tasks") < order.index("scheduled_blocks")

    def test_tasks_before_dismiss_log(self):
        order = mig._BACKEND_TABLE_ORDER
        assert order.index("tasks") < order.index("dismiss_log")

    def test_voice_capsules_before_play_log(self):
        order = mig._BACKEND_TABLE_ORDER
        assert order.index("voice_capsules") < order.index("voice_capsule_play_log")


# ---------------------------------------------------------------------------
# get_backend_tables (dynamic discovery from SQLite)
# ---------------------------------------------------------------------------


class TestGetBackendTables:
    def test_returns_only_existing_tables(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        tables = mig.get_backend_tables(conn)
        conn.close()
        # Only tables that exist in the fixture DB
        assert "tasks" in tables
        assert "users" in tables
        assert "devices" in tables
        # Tables not in the fixture should be absent
        assert "voice_events" not in tables

    def test_tables_in_dependency_order(self, backend_db):
        conn = mig.sqlite_connect(backend_db)
        tables = mig.get_backend_tables(conn)
        conn.close()
        # tasks is in the list and comes before scheduled_blocks IF both present;
        # in the fixture only tasks is present — just assert tasks is present
        assert "tasks" in tables


# ---------------------------------------------------------------------------
# Full pipeline smoke test (backend, no real PG)
# ---------------------------------------------------------------------------


class TestFullPipelineMocked:
    def test_migrate_backend_execute_calls_insert(self, backend_db):
        """
        With dry_run=False and empty PG tables, migrate_backend should call
        pg_insert_rows for each non-empty table.
        """
        pg_conn = MagicMock()
        inserted_calls = []

        def fake_insert(conn, schema, table, rows, mode, chunk_size=1000):
            inserted_calls.append((table, len(rows)))
            return len(rows)

        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows", side_effect=fake_insert):
                with patch.object(mig, "pg_setval"):
                    mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=False)

        inserted_tables = {t for t, _ in inserted_calls}
        assert "tasks" in inserted_tables
        assert "users" in inserted_tables
        assert "devices" in inserted_tables

        # tasks: 2 rows inserted
        task_call = next(c for c in inserted_calls if c[0] == "tasks")
        assert task_call[1] == 2

    def test_migrate_eventstore_execute_calls_insert(self, brain_db):
        """Event-store migration should call pg_insert_rows for seeded tables."""
        pg_conn = MagicMock()
        inserted_calls = []

        def fake_insert(conn, schema, table, rows, mode, chunk_size=1000):
            inserted_calls.append((table, len(rows)))
            return len(rows)

        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows", side_effect=fake_insert):
                with patch.object(mig, "pg_setval"):
                    mig.migrate_eventstore(brain_db, pg_conn, "skip-nonempty", dry_run=False)

        inserted_tables = {t for t, _ in inserted_calls}
        assert "world_events" in inserted_tables
        assert "llm_decisions" in inserted_tables
        assert "raw_events" in inserted_tables

    def test_json_columns_parsed_in_pipeline(self, backend_db):
        """
        Rows reaching pg_insert_rows should have JSON columns parsed
        (not raw strings).
        """
        pg_conn = MagicMock()
        captured_rows: list[dict] = []

        def capture_insert(conn, schema, table, rows, mode, chunk_size=1000):
            if table == "devices":
                captured_rows.extend(rows)
            return len(rows)

        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows", side_effect=capture_insert):
                with patch.object(mig, "pg_setval"):
                    mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=False)

        assert len(captured_rows) == 1
        device = captured_rows[0]
        # capabilities should be a list, not a string
        assert isinstance(device["capabilities"], list)
        assert "on_off" in device["capabilities"]
        # last_state should be a dict
        assert isinstance(device["last_state"], dict)

    def test_timestamps_converted_in_pipeline(self, backend_db):
        """Timestamps should have UTC timezone info after transformation."""
        pg_conn = MagicMock()
        captured_rows: list[dict] = []

        def capture_insert(conn, schema, table, rows, mode, chunk_size=1000):
            if table == "tasks":
                captured_rows.extend(rows)
            return len(rows)

        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows", side_effect=capture_insert):
                with patch.object(mig, "pg_setval"):
                    mig.migrate_backend(backend_db, pg_conn, "skip-nonempty", dry_run=False)

        assert len(captured_rows) == 2
        for row in captured_rows:
            ts = row["created_at"]
            assert ts is not None
            # UTC-aware: ends with +00:00
            assert "+00:00" in ts

    def test_brain_jsonb_columns_parsed_in_pipeline(self, brain_db):
        """llm_decisions JSONB columns should be parsed dicts, not strings."""
        pg_conn = MagicMock()
        captured: list[dict] = []

        def capture(conn, schema, table, rows, mode, chunk_size=1000):
            if table == "llm_decisions":
                captured.extend(rows)
            return len(rows)

        with patch.object(mig, "pg_table_count", return_value=0):
            with patch.object(mig, "pg_insert_rows", side_effect=capture):
                with patch.object(mig, "pg_setval"):
                    mig.migrate_eventstore(brain_db, pg_conn, "skip-nonempty", dry_run=False)

        assert len(captured) == 1
        row = captured[0]
        assert isinstance(row["trigger_events"], list)
        assert isinstance(row["tool_calls"], list)
        assert isinstance(row["world_state_snapshot"], dict)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLIParsing:
    def test_dry_run_is_default(self):
        parser = mig.build_parser()
        args = parser.parse_args([])
        assert args.dry_run is True

    def test_execute_flag_disables_dry_run(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--execute"])
        assert args.dry_run is False

    def test_mode_default(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--execute"])
        assert args.mode == "skip-nonempty"

    def test_mode_truncate(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--execute", "--mode", "truncate"])
        assert args.mode == "truncate"

    def test_mode_upsert(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--execute", "--mode", "upsert"])
        assert args.mode == "upsert"

    def test_custom_paths(self):
        parser = mig.build_parser()
        args = parser.parse_args(
            [
                "--backend-sqlite",
                "/tmp/b.db",
                "--brain-sqlite",
                "/tmp/brain.db",
                "--pg-url",
                "postgresql://user:pass@host:5432/db",
            ]
        )
        assert args.backend_sqlite == "/tmp/b.db"
        assert args.brain_sqlite == "/tmp/brain.db"
        assert args.pg_url == "postgresql://user:pass@host:5432/db"

    def test_skip_backend_flag(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--skip-backend"])
        assert args.skip_backend is True

    def test_skip_brain_flag(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--skip-brain"])
        assert args.skip_brain is True

    def test_verify_only_flag(self):
        parser = mig.build_parser()
        args = parser.parse_args(["--verify-only"])
        assert args.verify_only is True


# ---------------------------------------------------------------------------
# Verify function
# ---------------------------------------------------------------------------


class TestVerify:
    def test_verify_passes_when_counts_match(self, backend_db):
        pg_conn = MagicMock()

        def fake_count(conn, schema, table):
            # Return the same count as SQLite
            sqlite_conn = mig.sqlite_connect(backend_db)
            c = mig.sqlite_count(sqlite_conn, table)
            sqlite_conn.close()
            return c

        with patch.object(mig, "pg_table_count", side_effect=fake_count):
            ok = mig.verify(backend_db, None, pg_conn)
        assert ok is True

    def test_verify_fails_when_counts_differ(self, backend_db):
        pg_conn = MagicMock()

        def fake_count(conn, schema, table):
            # Return wrong count for tasks
            if table == "tasks":
                return 99
            return 0

        with patch.object(mig, "pg_table_count", side_effect=fake_count):
            ok = mig.verify(backend_db, None, pg_conn)
        assert ok is False

    def test_verify_brain_counts(self, brain_db):
        pg_conn = MagicMock()

        def fake_count(conn, schema, table):
            sqlite_conn = mig.sqlite_connect(brain_db)
            c = mig.sqlite_count(sqlite_conn, table)
            sqlite_conn.close()
            return c

        with patch.object(mig, "pg_table_count", side_effect=fake_count):
            ok = mig.verify(None, brain_db, pg_conn)
        assert ok is True


# ---------------------------------------------------------------------------
# Integration marker — skip when no real PG available
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIntegrationWithRealPG:
    """
    These tests require a live PostgreSQL instance.
    Run with: pytest -m integration --pg-url postgresql://...
    They are excluded from the standard CI run (no PG service).
    """

    def test_pg_connect_and_table_count(self, request):
        pg_url = request.config.getoption("--pg-url", default=None, skip=True)
        if not pg_url:
            pytest.skip("No --pg-url provided")
        conn = mig.pg_connect(pg_url)
        # Just test the connection works
        count = mig.pg_table_count(conn, "public", "tasks")
        assert isinstance(count, int)
        conn.close()
