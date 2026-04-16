import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/hems.db")

_engine_kwargs: dict = {"echo": False}
if ":memory:" in DATABASE_URL:
    # In-memory SQLite: force a StaticPool so every AsyncSession shares one
    # underlying connection — otherwise each checkout gets a fresh empty DB.
    from sqlalchemy.pool import StaticPool
    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
