"""Separate biometric latest projection from canonical observation history.

Revision ID: 0003_canonical_biometric_store
Revises: 0002_legacy_additive_columns
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_canonical_biometric_store"
down_revision: str | None = "0002_legacy_additive_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "biometric_latest",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("resting_heart_rate", sa.Integer(), nullable=True),
        sa.Column("spo2", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("active_minutes", sa.Integer(), nullable=True),
        sa.Column("stress_level", sa.Integer(), nullable=True),
        sa.Column("fatigue_score", sa.Integer(), nullable=True),
        sa.Column("sleep_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("sleep_quality_score", sa.Integer(), nullable=True),
        sa.Column("hrv_ms", sa.Integer(), nullable=True),
        sa.Column("body_temperature", sa.Float(), nullable=True),
        sa.Column("respiratory_rate", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_biometric_latest_provider", "biometric_latest", ["provider"], unique=False)
    op.create_index("ix_biometric_latest_updated_at", "biometric_latest", ["updated_at"], unique=False)

    op.create_table(
        "biometric_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("source_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aggregation", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_biometric_observations_observation_id",
        "biometric_observations",
        ["observation_id"],
        unique=True,
    )
    op.create_index("ix_biometric_observations_provider", "biometric_observations", ["provider"], unique=False)
    op.create_index("ix_biometric_observations_device_id", "biometric_observations", ["device_id"], unique=False)
    op.create_index("ix_biometric_observations_source_ts", "biometric_observations", ["source_ts"], unique=False)
    op.create_index("ix_biometric_observations_aggregation", "biometric_observations", ["aggregation"], unique=False)
    op.create_index("ix_biometric_observations_received_at", "biometric_observations", ["received_at"], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO biometric_latest (
                id, provider, heart_rate, resting_heart_rate, spo2, steps, calories,
                active_minutes, stress_level, fatigue_score, sleep_duration_minutes,
                sleep_quality_score, hrv_ms, body_temperature, respiratory_rate, updated_at
            )
            SELECT
                1, provider, heart_rate, resting_heart_rate, spo2, steps, calories,
                active_minutes, stress_level, fatigue_score, sleep_duration_minutes,
                sleep_quality_score, hrv_ms, body_temperature, respiratory_rate, recorded_at
            FROM biometric_readings
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """
        )
    )


def downgrade() -> None:
    raise RuntimeError("Canonical biometric store downgrade would destroy observation data")
