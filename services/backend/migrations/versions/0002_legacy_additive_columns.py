"""Add the columns previously managed by Backend lifespan DDL.

Revision ID: 0002_legacy_additive_columns
Revises: 0001_backend_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_legacy_additive_columns"
down_revision: str | None = "0001_backend_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_column(table_name: str, expected: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        raise RuntimeError(f"Required baseline table is missing: {table_name}")
    actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    actual = actual_columns.get(expected.name)
    if actual is None:
        op.add_column(table_name, expected)
        return

    reflected = sa.Column(expected.name, actual["type"], nullable=actual["nullable"])
    if op.get_context().impl.compare_type(reflected, expected):
        raise RuntimeError(
            f"Incompatible legacy column type for {table_name}.{expected.name}: "
            f"found {actual['type']}, expected {expected.type}"
        )
    if bool(actual["nullable"]) != bool(expected.nullable):
        raise RuntimeError(
            f"Incompatible legacy nullability for {table_name}.{expected.name}: "
            f"found nullable={actual['nullable']}, expected nullable={expected.nullable}"
        )


def _create_index(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {index["name"]: index for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)
        return
    index = existing[index_name]
    if list(index["column_names"]) != columns or bool(index["unique"]) != unique:
        raise RuntimeError(f"Incompatible legacy index {index_name} on {table_name}")


def upgrade() -> None:
    _add_column("voice_events", sa.Column("motion_id", sa.String(), nullable=True))

    _add_column("tasks", sa.Column("cognitive_load", sa.Integer(), nullable=True))
    _add_column("tasks", sa.Column("preferred_time_slot", sa.String(), nullable=True))
    _add_column("tasks", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))
    _add_column("tasks", sa.Column("source", sa.String(), nullable=True))
    _add_column("tasks", sa.Column("source_ref", sa.String(), nullable=True))
    _add_column("tasks", sa.Column("confidence", sa.Float(), nullable=True))
    _add_column("tasks", sa.Column("proposal_status", sa.String(), nullable=True))
    _add_column("tasks", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
    _add_column("tasks", sa.Column("dismiss_reason", sa.String(), nullable=True))
    _add_column("tasks", sa.Column("locked_start", sa.DateTime(timezone=True), nullable=True))

    _add_column("shopping_items", sa.Column("store_category", sa.String(), nullable=True))
    _create_index("ix_shopping_items_store_category", "shopping_items", ["store_category"], unique=False)

    _add_column("devices", sa.Column("model_id", sa.String(), nullable=True))
    _add_column("devices", sa.Column("manufacturer", sa.String(), nullable=True))
    _add_column("devices", sa.Column("link_quality", sa.Integer(), nullable=True))
    _add_column("devices", sa.Column("last_seen_reported", sa.DateTime(timezone=True), nullable=True))

    _add_column("automation_rules", sa.Column("risk_tier", sa.String(), nullable=True))
    _add_column("automation_rules", sa.Column("reversibility", sa.String(), nullable=True))
    _add_column("automation_rules", sa.Column("approval_required", sa.Boolean(), nullable=True))
    _add_column(
        "automation_rules",
        sa.Column("auto_rollback_window_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError("Backend baseline downgrade is intentionally unsupported")
