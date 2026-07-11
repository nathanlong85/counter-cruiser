"""SQLite-backed persistent recorder for deterrent trigger attempts.

One row per attempted trigger (timestamp + succeeded flag), surviving
client restarts. Mirrors ZoneStore's access pattern from the web-ui
change: a fresh connection per read/write, WAL mode, no shared long-lived
connection and no threading.Lock — SQLite's single-writer/multiple-reader
WAL semantics already make this safe across the asyncio detection thread
(writer) and the Flask request threads (readers).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class DeterrentStatsStore:
    """SQLite-backed recorder for deterrent trigger attempts."""

    def __init__(self, db_path: Path) -> None:
        """Store the target database path and ensure the schema exists."""
        self._db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh connection with WAL mode enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _init_schema(self) -> None:
        """Create the deterrent_events table if it does not already exist."""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    'CREATE TABLE IF NOT EXISTS deterrent_events ('
                    'id INTEGER PRIMARY KEY AUTOINCREMENT, '
                    'timestamp_utc TEXT NOT NULL, '
                    'succeeded INTEGER NOT NULL)'
                )
        finally:
            conn.close()

    def record(self, succeeded: bool) -> None:
        """Insert one event row for the current UTC time."""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    'INSERT INTO deterrent_events (timestamp_utc, succeeded) '
                    'VALUES (?, ?)',
                    (datetime.now(UTC).isoformat(), int(succeeded)),
                )
        finally:
            conn.close()

    def recent_events(self, since_days: int) -> list[tuple[str, bool]]:
        """Return (timestamp_utc, succeeded) for events within the last *since_days*."""
        cutoff = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
        conn = self._connect()
        try:
            with conn:
                rows = conn.execute(
                    'SELECT timestamp_utc, succeeded FROM deterrent_events '
                    'WHERE timestamp_utc >= ? ORDER BY timestamp_utc ASC',
                    (cutoff,),
                ).fetchall()
        finally:
            conn.close()
        return [(ts, bool(s)) for ts, s in rows]

    def recent_failures(self, limit: int) -> list[str]:
        """Return up to *limit* most recent failed-event timestamps, newest first."""
        conn = self._connect()
        try:
            with conn:
                rows = conn.execute(
                    'SELECT timestamp_utc FROM deterrent_events '
                    'WHERE succeeded = 0 ORDER BY timestamp_utc DESC LIMIT ?',
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
        return [ts for (ts,) in rows]
