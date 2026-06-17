"""Tests for backend DB operational improvements (WAL mode, retention cleanup)."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String, event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker


@pytest.fixture
def sqlite_engine(tmp_path):
    """Create a fresh file-backed SQLite async engine with WAL pragmas applied."""
    db_file = tmp_path / "hems_db_improvements.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    yield engine

    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass


class TestSqliteWalMode:
    def test_wal_mode_enabled_for_sqlite(self, sqlite_engine):
        async def _check():
            async with sqlite_engine.connect() as conn:
                result = await conn.execute(text("PRAGMA journal_mode"))
                row = result.fetchone()
                return row[0] if row else None

        assert asyncio.run(_check()) == "wal"

    def test_busy_timeout_set_for_sqlite(self, sqlite_engine):
        async def _check():
            async with sqlite_engine.connect() as conn:
                result = await conn.execute(text("PRAGMA busy_timeout"))
                row = result.fetchone()
                return row[0] if row else None

        assert asyncio.run(_check()) == 5000


class TestRetentionCleanup:
    @pytest.fixture
    async def cleanup_session(self, sqlite_engine):
        """Create minimal tables and yield a session for retention cleanup tests."""
        Base = declarative_base()

        class TimeSeriesPoint(Base):
            __tablename__ = "timeseries"
            id = Column(Integer, primary_key=True)
            metric = Column(String, nullable=False)
            value = Column(Float, nullable=False)
            recorded_at = Column(DateTime(timezone=True), nullable=False)

        class Task(Base):
            __tablename__ = "tasks"
            id = Column(Integer, primary_key=True)
            title = Column(String)
            is_completed = Column(Integer, default=0)
            completed_at = Column(DateTime(timezone=True), nullable=True)

        class VoiceEvent(Base):
            __tablename__ = "voice_events"
            id = Column(Integer, primary_key=True)
            created_at = Column(DateTime(timezone=True), nullable=False)

        class BiometricReading(Base):
            __tablename__ = "biometric_readings"
            id = Column(Integer, primary_key=True)
            recorded_at = Column(DateTime(timezone=True), nullable=False)

        class PurchaseHistory(Base):
            __tablename__ = "purchase_history"
            id = Column(Integer, primary_key=True)
            purchased_at = Column(DateTime(timezone=True), nullable=False)

        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        Session = sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            yield session, TimeSeriesPoint, Task, VoiceEvent, BiometricReading, PurchaseHistory

    @pytest.mark.asyncio
    async def test_deletes_old_time_series_points(self, cleanup_session):
        from main import _run_retention_cleanup

        session, TimeSeriesPoint, *_ = cleanup_session
        now = datetime.now(UTC)

        session.add_all(
            [
                TimeSeriesPoint(metric="temperature", value=25.0, recorded_at=now - timedelta(days=60)),
                TimeSeriesPoint(metric="temperature", value=26.0, recorded_at=now - timedelta(days=1)),
            ]
        )
        await session.commit()

        deleted = await _run_retention_cleanup(session)
        await session.commit()

        result = await session.execute(text("SELECT value FROM timeseries"))
        remaining = result.scalars().all()
        assert deleted.get("timeseries") == 1
        assert remaining == [26.0]

    @pytest.mark.asyncio
    async def test_deletes_old_completed_tasks_only(self, cleanup_session):
        from main import _run_retention_cleanup

        session, _, Task, *_ = cleanup_session
        now = datetime.now(UTC)

        session.add_all(
            [
                Task(title="old done", is_completed=1, completed_at=now - timedelta(days=400)),
                Task(title="recent done", is_completed=1, completed_at=now - timedelta(days=1)),
                Task(title="active", is_completed=0),
            ]
        )
        await session.commit()

        deleted = await _run_retention_cleanup(session)
        await session.commit()

        result = await session.execute(text("SELECT title FROM tasks ORDER BY title"))
        remaining = result.scalars().all()
        assert deleted.get("tasks") == 1
        assert remaining == ["active", "recent done"]
