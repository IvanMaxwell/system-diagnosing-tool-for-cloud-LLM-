import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import CONFIG

logger = logging.getLogger(__name__)
DB_PATH = Path(CONFIG.db_path)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    try:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS diagnostic_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    intent      TEXT,
                    category    TEXT,
                    narrative   TEXT,
                    top_process TEXT,
                    dqe_used    INTEGER DEFAULT 0,
                    resolved    INTEGER DEFAULT 0
                )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"DB init failed: {e}")


def write_event(
    intent: str,
    category: str,
    narrative: str,
    top_process: str = "",
    dqe_used: bool = False,
) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO diagnostic_events
                   (timestamp, intent, category, narrative, top_process, dqe_used)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    intent,
                    category,
                    narrative,
                    top_process,
                    int(dqe_used),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"DB write failed: {e}")


def get_recent_events(limit: int = 10) -> list[dict[str, Any]]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM diagnostic_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"DB read failed: {e}")
        return []


def count_prior_occurrences(category: str) -> int:
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM diagnostic_events WHERE category = ?",
                (category,),
            ).fetchone()
            return row["cnt"] if row else 0
    except Exception as e:
        logger.error(f"DB count failed: {e}")
        return 0
