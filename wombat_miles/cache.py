"""SQLite cache for award search results (4-hour TTL)."""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".wombat-miles"
CACHE_FILE = CACHE_DIR / "cache.db"
DEFAULT_TTL = 4 * 60 * 60  # 4 hours in seconds


def _get_conn() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def get(key: str) -> Optional[Any]:
    """Get a cached value, returning None if missing or expired."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        conn.close()

        if row is None:
            return None

        value_str, expires_at = row
        if time.time() > expires_at:
            return None

        return json.loads(value_str)
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Store a value in cache with TTL."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Cache set error: {e}")


def clear_expired() -> int:
    """Remove expired cache entries. Returns number of removed entries."""
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM cache WHERE expires_at < ?", (time.time(),)
        )
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Cache clear error: {e}")
        return 0


def clear_all() -> None:
    """Clear all cache entries."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Cache clear_all error: {e}")


def make_key(program: str, origin: str, destination: str, date: str) -> str:
    return f"{program}_{origin.upper()}_{destination.upper()}_{date}"
