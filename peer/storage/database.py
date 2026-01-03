"""SQLite database layer for Peer."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class Event:
    """An activity event (keystroke, click, window change)."""

    timestamp: str
    event_type: str
    data: dict[str, Any]
    session_id: str
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Screenshot:
    """A captured screenshot."""

    timestamp: str
    filepath: str
    session_id: str
    ai_interpretation: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    """A logging session."""

    id: str
    start_time: str
    mode: int = 1
    end_time: Optional[str] = None
    summary: Optional[str] = None
    total_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Database:
    """SQLite database for storing activity logs."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    mode INTEGER DEFAULT 1,
                    summary TEXT,
                    total_cost REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    ai_interpretation TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_screenshots_session ON screenshots(session_id);
            """)

    def create_session(self, mode: int = 1) -> Session:
        """Create a new logging session."""
        session = Session(
            id=str(uuid.uuid4()),
            start_time=datetime.now().isoformat(),
            mode=mode,
        )
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, start_time, mode) VALUES (?, ?, ?)",
                (session.id, session.start_time, session.mode),
            )
        return session

    def end_session(
        self, session_id: str, summary: Optional[str] = None, total_cost: float = 0.0
    ) -> None:
        """End a logging session."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET end_time = ?, summary = ?, total_cost = ? WHERE id = ?",
                (datetime.now().isoformat(), summary, total_cost, session_id),
            )

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row:
                return Session(**dict(row))
        return None

    def get_active_session(self) -> Optional[Session]:
        """Get the most recent active (not ended) session."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
            ).fetchone()
            if row:
                return Session(**dict(row))
        return None

    def add_event(self, event: Event) -> int:
        """Add an activity event."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO events (timestamp, event_type, data, session_id) VALUES (?, ?, ?, ?)",
                (event.timestamp, event.event_type, json.dumps(event.data), event.session_id),
            )
            return cursor.lastrowid or 0

    def add_screenshot(self, screenshot: Screenshot) -> int:
        """Add a screenshot record."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO screenshots (timestamp, filepath, session_id, ai_interpretation)
                   VALUES (?, ?, ?, ?)""",
                (
                    screenshot.timestamp,
                    screenshot.filepath,
                    screenshot.session_id,
                    screenshot.ai_interpretation,
                ),
            )
            return cursor.lastrowid or 0

    def get_session_events(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[Event]:
        """Get all events for a session."""
        with self._get_connection() as conn:
            if limit:
                rows = conn.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
                    (session_id,),
                ).fetchall()
            return [
                Event(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    event_type=row["event_type"],
                    data=json.loads(row["data"]),
                    session_id=row["session_id"],
                )
                for row in rows
            ]

    def get_session_screenshots(self, session_id: str) -> list[Screenshot]:
        """Get all screenshots for a session."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM screenshots WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [Screenshot(**dict(row)) for row in rows]

    def get_recent_events(self, session_id: str, count: int = 100) -> list[Event]:
        """Get the most recent events for a session."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM events WHERE session_id = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (session_id, count),
            ).fetchall()
            return [
                Event(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    event_type=row["event_type"],
                    data=json.loads(row["data"]),
                    session_id=row["session_id"],
                )
                for row in reversed(rows)
            ]

    def export_session_json(self, session_id: str) -> dict[str, Any]:
        """Export a session and all its data as JSON-friendly dict."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        events = self.get_session_events(session_id)
        screenshots = self.get_session_screenshots(session_id)

        return {
            "session": session.to_dict(),
            "events": [e.to_dict() for e in events],
            "screenshots": [s.to_dict() for s in screenshots],
        }

    def update_session_cost(self, session_id: str, cost: float) -> None:
        """Add to the total cost of a session."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET total_cost = total_cost + ? WHERE id = ?",
                (cost, session_id),
            )
