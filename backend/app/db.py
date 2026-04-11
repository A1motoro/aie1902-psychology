import sqlite3
from pathlib import Path

from app.config import get_settings


def _connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    settings = get_settings()
    conn = _connect(settings.database_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    return _connect(get_settings().database_path)
