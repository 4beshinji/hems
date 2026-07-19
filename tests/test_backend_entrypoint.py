"""Backend migration-first startup contract."""

from pathlib import Path

import pytest

import entrypoint


def test_entrypoint_execs_uvicorn_only_after_migration(monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(entrypoint, "upgrade_backend_schema", lambda: calls.append(("migration", None)))
    monkeypatch.setattr(entrypoint.os, "execvp", lambda executable, argv: calls.append((executable, argv)))

    entrypoint.main()

    assert calls[0] == ("migration", None)
    assert calls[1][0] == "uvicorn"
    assert calls[1][1][0:2] == ["uvicorn", "main:app"]


def test_entrypoint_does_not_start_uvicorn_when_migration_fails(monkeypatch):
    def fail_migration() -> None:
        raise RuntimeError("schema mismatch")

    monkeypatch.setattr(entrypoint, "upgrade_backend_schema", fail_migration)
    monkeypatch.setattr(entrypoint.os, "execvp", lambda *_args: pytest.fail("Uvicorn must not start"))

    with pytest.raises(RuntimeError, match="schema mismatch"):
        entrypoint.main()


def test_runtime_lifespan_contains_no_schema_ddl():
    source = (Path(__file__).resolve().parent.parent / "services" / "backend" / "main.py").read_text()

    assert "Base.metadata.create_all" not in source
    assert "ALTER TABLE" not in source
    assert "_add_column_if_missing" not in source
