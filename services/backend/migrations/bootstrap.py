"""Reconcile an empty or unversioned Backend database to Alembic head."""

import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
LEGACY_MOBILE_OBSERVATION_REVISION = "0004_mobile_observation_foundation"
MOBILE_OBSERVATION_REVISION = "0004_mobile_observation"


def _sqlite_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser()


def _prepare_sqlite(config: Config, database_url: str) -> None:
    database = _sqlite_path(database_url)
    if database is None:
        return
    database.parent.mkdir(parents=True, exist_ok=True)
    if not database.exists():
        return

    with sqlite3.connect(database) as connection:
        has_version_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
        ).fetchone()
        current = (
            connection.execute("SELECT version_num FROM alembic_version").fetchone() if has_version_table else None
        )
        current_revision = current[0] if current else None
        if current_revision == LEGACY_MOBILE_OBSERVATION_REVISION:
            connection.execute(
                "UPDATE alembic_version SET version_num = ? WHERE version_num = ?",
                (MOBILE_OBSERVATION_REVISION, LEGACY_MOBILE_OBSERVATION_REVISION),
            )
            connection.commit()
            current_revision = MOBILE_OBSERVATION_REVISION

    head = ScriptDirectory.from_config(config).get_current_head()
    if current_revision == head:
        return

    backup = Path(f"{database}.pre-{head}.bak")
    if backup.exists():
        return
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)


def upgrade_backend_schema(database_url: str | None = None) -> None:
    """Validate and upgrade the configured Backend schema to head.

    Existing unversioned tables are reconciled by the idempotent revisions;
    this function never stamps a database without running their validation.
    """
    config = Config(str(ALEMBIC_INI))
    resolved_url = database_url or os.environ.get("DATABASE_URL")
    if resolved_url:
        config.attributes["database_url"] = resolved_url
        _prepare_sqlite(config, resolved_url)
    command.upgrade(config, "head")


def main() -> None:
    upgrade_backend_schema()


if __name__ == "__main__":
    main()
