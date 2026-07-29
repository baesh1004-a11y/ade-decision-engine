from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_sqlite(
    db_path: str | Path,
    *,
    row_factory: bool = True,
    timeout_seconds: float = 30.0,
) -> sqlite3.Connection:
    """Create a consistently configured SQLite connection.

    Connections remain scoped to the caller. This avoids sharing one SQLite
    connection across Streamlit sessions or background worker threads while
    applying the same lock timeout and foreign-key settings everywhere.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout_seconds)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
