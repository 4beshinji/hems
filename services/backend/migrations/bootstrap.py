"""Reconcile an empty or unversioned Backend database to Alembic head."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def upgrade_backend_schema(database_url: str | None = None) -> None:
    """Validate and upgrade the configured Backend schema to head.

    Existing unversioned tables are reconciled by the idempotent revisions;
    this function never stamps a database without running their validation.
    """
    config = Config(str(ALEMBIC_INI))
    resolved_url = database_url or os.environ.get("DATABASE_URL")
    if resolved_url:
        config.attributes["database_url"] = resolved_url
    command.upgrade(config, "head")


def main() -> None:
    upgrade_backend_schema()


if __name__ == "__main__":
    main()
