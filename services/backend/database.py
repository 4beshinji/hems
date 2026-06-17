import os
from datetime import UTC

from sqlalchemy import DateTime as _SADateTime
from sqlalchemy import TypeDecorator, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker


class TZDateTime(TypeDecorator):
    """DateTime that ensures UTC tzinfo on naive results from SQLite."""

    impl = _SADateTime
    cache_ok = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://hems:hems@postgres:5432/hems")

_engine_kwargs: dict = {"echo": False}
if "postgresql" in DATABASE_URL:
    # PostgreSQL: bounded pool + pre-ping for container restart resilience.
    _engine_kwargs.update({"pool_size": 5, "max_overflow": 5, "pool_pre_ping": True})
elif ":memory:" in DATABASE_URL:
    # In-memory SQLite: force a StaticPool so every AsyncSession shares one
    # underlying connection — otherwise each checkout gets a fresh empty DB.
    from sqlalchemy.pool import StaticPool

    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and a busy timeout for SQLite backends."""
    if "sqlite" not in DATABASE_URL:
        return
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
