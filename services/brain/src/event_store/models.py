"""
SQLAlchemy ORM models for the events schema.

Used for typed queries in the aggregator. Tables are created via raw DDL
in database.py (not via ORM metadata).
"""
from datetime import datetime
from sqlalchemy import Integer, BigInteger, Text, Float, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = {"schema": "events"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zone: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_device: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class LLMDecision(Base):
    __tablename__ = "llm_decisions"
    __table_args__ = {"schema": "events"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cycle_duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_events: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    tool_calls: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    world_state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class HourlyAggregate(Base):
    __tablename__ = "hourly_aggregates"
    __table_args__ = {"schema": "events"}

    hub_id: Mapped[str] = mapped_column(Text, primary_key=True, default="soms-brain")
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    zones: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tasks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_health: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AggregationState(Base):
    __tablename__ = "aggregation_state"
    __table_args__ = {"schema": "events"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_aggregated_hour: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
