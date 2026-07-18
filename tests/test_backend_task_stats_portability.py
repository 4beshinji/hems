"""Dialect-compatibility tests for the task statistics query."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import models
from routers.tasks import _completed_last_hour_query


def test_completed_last_hour_query_is_postgresql_compatible():
    cutoff = datetime.now(UTC) - timedelta(hours=1)

    compiled = _completed_last_hour_query(cutoff).compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()

    assert "datetime(" not in sql
    assert "tasks.completed_at >=" in sql
    assert cutoff in compiled.params.values()


def test_completed_last_hour_query_counts_recent_tasks_on_sqlite():
    engine = create_engine("sqlite:///:memory:")
    now = datetime.now(UTC)

    try:
        models.Task.__table__.create(engine)
        with Session(engine) as session:
            session.add_all(
                [
                    models.Task(title="recent", is_completed=True, completed_at=now - timedelta(minutes=30)),
                    models.Task(title="old", is_completed=True, completed_at=now - timedelta(hours=2)),
                    models.Task(title="active", is_completed=False),
                ]
            )
            session.commit()

            result = session.execute(_completed_last_hour_query(now - timedelta(hours=1)))

            assert result.scalar_one() == 1
    finally:
        engine.dispose()
