"""
HEMS Lite Sentinel — SQLite persistent storage for alerts and history.
"""
import aiosqlite
from loguru import logger

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    level TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT NOT NULL,
    zone TEXT DEFAULT '',
    data_json TEXT DEFAULT '{}',
    notified INTEGER DEFAULT 0,
    escalated INTEGER DEFAULT 0,
    llm_verdict TEXT DEFAULT '',
    llm_reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    summary_json TEXT NOT NULL,
    sent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metrics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    zone TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(level);
CREATE INDEX IF NOT EXISTS idx_metrics_ts_metric ON metrics_history(timestamp, metric);
"""


class SentinelDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info(f"Database initialized: {self.db_path}")

    async def log_alert(self, timestamp: float, level: str, rule_id: str,
                        title: str, body: str, source: str, zone: str = "",
                        data_json: str = "{}", notified: bool = False,
                        escalated: bool = False, llm_verdict: str = "",
                        llm_reason: str = ""):
        await self._db.execute(
            "INSERT INTO alerts (timestamp, level, rule_id, title, body, source, "
            "zone, data_json, notified, escalated, llm_verdict, llm_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, level, rule_id, title, body, source, zone, data_json,
             int(notified), int(escalated), llm_verdict, llm_reason),
        )
        await self._db.commit()

    async def log_metric(self, timestamp: float, metric: str, value: float,
                         zone: str = ""):
        await self._db.execute(
            "INSERT INTO metrics_history (timestamp, metric, value, zone) "
            "VALUES (?, ?, ?, ?)",
            (timestamp, metric, value, zone),
        )
        await self._db.commit()

    async def get_alerts_since(self, since_ts: float, level: str | None = None) -> list[dict]:
        query = "SELECT * FROM alerts WHERE timestamp >= ?"
        params: list = [since_ts]
        if level:
            query += " AND level = ?"
            params.append(level)
        query += " ORDER BY timestamp DESC"

        rows = await self._db.execute_fetchall(query, params)
        columns = ["id", "timestamp", "level", "rule_id", "title", "body",
                    "source", "zone", "data_json", "notified", "escalated",
                    "llm_verdict", "llm_reason"]
        return [dict(zip(columns, row)) for row in rows]

    async def get_daily_stats(self, date_str: str) -> dict | None:
        row = await self._db.execute_fetchall(
            "SELECT summary_json FROM daily_summary WHERE date = ?",
            (date_str,),
        )
        if row:
            import json
            return json.loads(row[0][0])
        return None

    async def save_daily_summary(self, date_str: str, summary_json: str, sent: bool = False):
        await self._db.execute(
            "INSERT OR REPLACE INTO daily_summary (date, summary_json, sent) "
            "VALUES (?, ?, ?)",
            (date_str, summary_json, int(sent)),
        )
        await self._db.commit()

    async def get_metric_history(self, metric: str, since_ts: float) -> list[tuple[float, float]]:
        rows = await self._db.execute_fetchall(
            "SELECT timestamp, value FROM metrics_history "
            "WHERE metric = ? AND timestamp >= ? ORDER BY timestamp",
            (metric, since_ts),
        )
        return [(r[0], r[1]) for r in rows]

    async def prune_old_data(self, retention_days: int = 90):
        import time
        cutoff = time.time() - retention_days * 86400
        await self._db.execute("DELETE FROM alerts WHERE timestamp < ?", (cutoff,))
        await self._db.execute("DELETE FROM metrics_history WHERE timestamp < ?", (cutoff,))
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
