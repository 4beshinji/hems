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


def upgrade() -> None:
    op.add_column("voice_events", sa.Column("motion_id", sa.String(), nullable=True))

    op.add_column("tasks", sa.Column("cognitive_load", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("preferred_time_slot", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("source", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("source_ref", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("tasks", sa.Column("proposal_status", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("dismiss_reason", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("locked_start", sa.DateTime(timezone=True), nullable=True))

    op.add_column("shopping_items", sa.Column("store_category", sa.String(), nullable=True))
    op.create_index("ix_shopping_items_store_category", "shopping_items", ["store_category"], unique=False)

    op.add_column("devices", sa.Column("model_id", sa.String(), nullable=True))
    op.add_column("devices", sa.Column("manufacturer", sa.String(), nullable=True))
    op.add_column("devices", sa.Column("link_quality", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("last_seen_reported", sa.DateTime(timezone=True), nullable=True))

    op.add_column("automation_rules", sa.Column("risk_tier", sa.String(), nullable=True))
    op.add_column("automation_rules", sa.Column("reversibility", sa.String(), nullable=True))
    op.add_column("automation_rules", sa.Column("approval_required", sa.Boolean(), nullable=True))
    op.add_column(
        "automation_rules",
        sa.Column("auto_rollback_window_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError("Backend baseline downgrade is intentionally unsupported")
