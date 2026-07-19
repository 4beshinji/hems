"""Add durable mobile observation inbox and delivery outbox.

Revision ID: 0004_mobile_observation_foundation
Revises: 0003_canonical_biometric_store
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_mobile_observation_foundation"
down_revision: str | None = "0003_canonical_biometric_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mobile_observation_inbox",
        sa.Column("observation_id", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("mobile_device_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aggregation", sa.String(length=32), nullable=True),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["mobile_device_id"], ["mobile_devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    for column in ("mobile_device_id", "kind", "observed_at", "aggregation", "status", "received_at"):
        op.create_index(f"ix_mobile_observation_inbox_{column}", "mobile_observation_inbox", [column], unique=False)

    op.create_table(
        "mobile_delivery_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.String(length=128), nullable=False),
        sa.Column("destination", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["observation_id"], ["mobile_observation_inbox.observation_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "destination", "target", name="uq_mobile_delivery_destination"),
    )
    for column in (
        "observation_id",
        "destination",
        "status",
        "next_attempt_at",
        "lease_until",
        "created_at",
    ):
        op.create_index(f"ix_mobile_delivery_outbox_{column}", "mobile_delivery_outbox", [column], unique=False)


def downgrade() -> None:
    raise RuntimeError("Mobile observation foundation downgrade would destroy durable delivery state")
