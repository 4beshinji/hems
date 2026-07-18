"""Create the fixed Backend baseline schema without legacy additive columns.

Revision ID: 0001_backend_baseline
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_backend_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_feedback_feedback_type"), "agent_feedback", ["feedback_type"], unique=False)
    op.create_index(op.f("ix_agent_feedback_id"), "agent_feedback", ["id"], unique=False)
    op.create_index(op.f("ix_agent_feedback_recorded_at"), "agent_feedback", ["recorded_at"], unique=False)
    op.create_index(op.f("ix_agent_feedback_target_id"), "agent_feedback", ["target_id"], unique=False)
    op.create_index(op.f("ix_agent_feedback_target_type"), "agent_feedback", ["target_type"], unique=False)
    op.create_index(op.f("ix_agent_feedback_user_id"), "agent_feedback", ["user_id"], unique=False)
    op.create_table(
        "agent_trajectories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cycle_id", sa.String(), nullable=True),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("trigger_events", sa.JSON(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("world_state_snapshot", sa.JSON(), nullable=False),
        sa.Column("outcome_summary", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_trajectories_cycle_id"), "agent_trajectories", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_agent_trajectories_decision_id"), "agent_trajectories", ["decision_id"], unique=False)
    op.create_index(op.f("ix_agent_trajectories_id"), "agent_trajectories", ["id"], unique=False)
    op.create_index(op.f("ix_agent_trajectories_timestamp"), "agent_trajectories", ["timestamp"], unique=False)
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("trigger_config", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("cooldown_s", sa.Integer(), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("require_confirm", sa.Boolean(), nullable=True),
        sa.Column("fire_count", sa.Integer(), nullable=True),
        sa.Column("last_evaluation_ts", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_automation_rules_id"), "automation_rules", ["id"], unique=False)
    op.create_index(op.f("ix_automation_rules_trigger_type"), "automation_rules", ["trigger_type"], unique=False)
    op.create_table(
        "biometric_readings",
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
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_biometric_readings_id"), "biometric_readings", ["id"], unique=False)
    op.create_index(op.f("ix_biometric_readings_provider"), "biometric_readings", ["provider"], unique=False)
    op.create_index(op.f("ix_biometric_readings_recorded_at"), "biometric_readings", ["recorded_at"], unique=False)
    op.create_table(
        "bridge_status_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("detail", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bridge_status_log_id"), "bridge_status_log", ["id"], unique=False)
    op.create_index(op.f("ix_bridge_status_log_service"), "bridge_status_log", ["service"], unique=False)
    op.create_index(op.f("ix_bridge_status_log_timestamp"), "bridge_status_log", ["timestamp"], unique=False)
    op.create_table(
        "classifier_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("value_json", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=True),
        sa.Column(
            "learned_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "key_hash", name="uq_classifier_kind_key"),
    )
    op.create_index(op.f("ix_classifier_cache_id"), "classifier_cache", ["id"], unique=False)
    op.create_index(op.f("ix_classifier_cache_key_hash"), "classifier_cache", ["key_hash"], unique=False)
    op.create_index(op.f("ix_classifier_cache_kind"), "classifier_cache", ["kind"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_id"), "conversations", ["id"], unique=False)
    op.create_table(
        "device_action_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_device_action_log_device_id"), "device_action_log", ["device_id"], unique=False)
    op.create_index(op.f("ix_device_action_log_id"), "device_action_log", ["id"], unique=False)
    op.create_index(op.f("ix_device_action_log_timestamp"), "device_action_log", ["timestamp"], unique=False)
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("vendor", sa.String(), nullable=False),
        sa.Column("vendor_ref", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("device_class", sa.String(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("channels", sa.JSON(), nullable=True),
        sa.Column("units", sa.JSON(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("zone", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("last_state", sa.JSON(), nullable=True),
        sa.Column("last_value", sa.JSON(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("battery_pct", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_device_id"), "devices", ["device_id"], unique=True)
    op.create_index(op.f("ix_devices_id"), "devices", ["id"], unique=False)
    op.create_index(op.f("ix_devices_vendor"), "devices", ["vendor"], unique=False)
    op.create_index(op.f("ix_devices_zone"), "devices", ["zone"], unique=False)
    op.create_table(
        "frequent_places",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("cooldown_min", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_frequent_places_category"), "frequent_places", ["category"], unique=False)
    op.create_index(op.f("ix_frequent_places_id"), "frequent_places", ["id"], unique=False)
    op.create_table(
        "mobile_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=False),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("hmac_secret", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column(
            "registered_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mobile_devices_api_key_hash"), "mobile_devices", ["api_key_hash"], unique=True)
    op.create_index(op.f("ix_mobile_devices_id"), "mobile_devices", ["id"], unique=False)
    op.create_table(
        "purchase_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column(
            "purchased_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_purchase_history_id"), "purchase_history", ["id"], unique=False)
    op.create_index(op.f("ix_purchase_history_item_name"), "purchase_history", ["item_name"], unique=False)
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=True),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scenes_id"), "scenes", ["id"], unique=False)
    op.create_index(op.f("ix_scenes_name"), "scenes", ["name"], unique=True)
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("is_purchased", sa.Boolean(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=True),
        sa.Column("recurrence_days", sa.Integer(), nullable=True),
        sa.Column("last_purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_purchase_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("share_token", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_token"),
    )
    op.create_index(op.f("ix_shopping_items_category"), "shopping_items", ["category"], unique=False)
    op.create_index(op.f("ix_shopping_items_id"), "shopping_items", ["id"], unique=False)
    op.create_index(op.f("ix_shopping_items_name"), "shopping_items", ["name"], unique=False)
    op.create_table(
        "system_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=True),
        sa.Column("tasks_created", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column(
            "last_seen", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_preferences_id"), "task_preferences", ["id"], unique=False)
    op.create_index(op.f("ix_task_preferences_key"), "task_preferences", ["key"], unique=True)
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=True),
        sa.Column("urgency", sa.Integer(), nullable=True),
        sa.Column("zone", sa.String(), nullable=True),
        sa.Column("estimated_duration", sa.Integer(), nullable=True),
        sa.Column("is_queued", sa.Boolean(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("announcement_audio_url", sa.String(), nullable=True),
        sa.Column("announcement_text", sa.String(), nullable=True),
        sa.Column("completion_audio_url", sa.String(), nullable=True),
        sa.Column("completion_text", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_type", sa.String(), nullable=True),
        sa.Column("report_status", sa.String(), nullable=True),
        sa.Column("completion_note", sa.String(), nullable=True),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_id"), "tasks", ["id"], unique=False)
    op.create_index(op.f("ix_tasks_title"), "tasks", ["title"], unique=False)
    op.create_table(
        "threshold_drift_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("detector", sa.String(), nullable=False),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("old_value", sa.Float(), nullable=True),
        sa.Column("proposed_value", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_threshold_drift_log_detected_at"), "threshold_drift_log", ["detected_at"], unique=False)
    op.create_index(op.f("ix_threshold_drift_log_id"), "threshold_drift_log", ["id"], unique=False)
    op.create_index(op.f("ix_threshold_drift_log_metric_key"), "threshold_drift_log", ["metric_key"], unique=False)
    op.create_index(op.f("ix_threshold_drift_log_status"), "threshold_drift_log", ["status"], unique=False)
    op.create_table(
        "timeseries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("zone", sa.String(), nullable=True),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_timeseries_id"), "timeseries", ["id"], unique=False)
    op.create_index(op.f("ix_timeseries_metric"), "timeseries", ["metric"], unique=False)
    op.create_index(op.f("ix_timeseries_recorded_at"), "timeseries", ["recorded_at"], unique=False)
    op.create_index(op.f("ix_timeseries_zone"), "timeseries", ["zone"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_table(
        "voice_capsules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capsule_date", sa.String(), nullable=False),
        sa.Column("character_version", sa.String(), nullable=True),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_voice_capsules_capsule_date"), "voice_capsules", ["capsule_date"], unique=False)
    op.create_index(op.f("ix_voice_capsules_id"), "voice_capsules", ["id"], unique=False)
    op.create_table(
        "voice_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("zone", sa.String(), nullable=True),
        sa.Column("tone", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_voice_events_id"), "voice_events", ["id"], unique=False)
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("risk_tier", sa.String(), nullable=False),
        sa.Column("reversibility", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("proposed_payload", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reviewer_id", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("decision_reason", sa.String(), nullable=True),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_plan", sa.JSON(), nullable=True),
        sa.Column("rollback_status", sa.String(), nullable=True),
        sa.Column("audit_log", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["automation_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approvals_rule_id"), "approvals", ["rule_id"], unique=False)
    op.create_index(op.f("ix_approvals_status"), "approvals", ["status"], unique=False)
    op.create_index(op.f("ix_approvals_thread_id"), "approvals", ["thread_id"], unique=False)
    op.create_table(
        "dismiss_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("task_title", sa.String(), nullable=True),
        sa.Column("task_type_json", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("context_json", sa.String(), nullable=True),
        sa.Column(
            "dismissed_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dismiss_log_id"), "dismiss_log", ["id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("tool_calls_json", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_messages_id"), "messages", ["id"], unique=False)
    op.create_table(
        "scheduled_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("ref_task_id", sa.Integer(), nullable=True),
        sa.Column("ref_calendar_event_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=True),
        sa.Column("travel_buffer_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["ref_task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_blocks_date"), "scheduled_blocks", ["date"], unique=False)
    op.create_index(op.f("ix_scheduled_blocks_id"), "scheduled_blocks", ["id"], unique=False)
    op.create_table(
        "threshold_adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(), nullable=False),
        sa.Column("base_value", sa.Float(), nullable=False),
        sa.Column("offset", sa.Float(), nullable=False),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("drift_log_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["drift_log_id"],
            ["threshold_drift_log.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_threshold_adjustments_applied_at"), "threshold_adjustments", ["applied_at"], unique=False)
    op.create_index(
        op.f("ix_threshold_adjustments_drift_log_id"), "threshold_adjustments", ["drift_log_id"], unique=False
    )
    op.create_index(op.f("ix_threshold_adjustments_id"), "threshold_adjustments", ["id"], unique=False)
    op.create_index(op.f("ix_threshold_adjustments_metric_key"), "threshold_adjustments", ["metric_key"], unique=False)
    op.create_table(
        "voice_capsule_play_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capsule_id", sa.Integer(), nullable=True),
        sa.Column("clip_id", sa.String(), nullable=False),
        sa.Column(
            "played_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("trigger_drift_sec", sa.Integer(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["capsule_id"],
            ["voice_capsules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_voice_capsule_play_log_capsule_id"), "voice_capsule_play_log", ["capsule_id"], unique=False
    )
    op.create_index(op.f("ix_voice_capsule_play_log_id"), "voice_capsule_play_log", ["id"], unique=False)
    op.create_table(
        "action_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_action_snapshots_approval_id"), "action_snapshots", ["approval_id"], unique=False)
    op.create_table(
        "rollback_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("compensation_plan", sa.JSON(), nullable=True),
        sa.Column("execution_status", sa.String(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rollback_log_approval_id"), "rollback_log", ["approval_id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    raise RuntimeError("Backend baseline downgrade is intentionally unsupported")
