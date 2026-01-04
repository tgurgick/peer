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

    # --- Data Management Methods ---
    # Inspired by ActivityWatch's data deletion capabilities

    def get_all_sessions(self, limit: int = 100) -> list[Session]:
        """Get all sessions, most recent first."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [Session(**dict(row)) for row in rows]

    def delete_events_before(self, before_date: str) -> int:
        """Delete all events before a given date. Returns count deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (before_date,),
            )
            return cursor.rowcount

    def delete_events_by_app(self, app_name: str) -> int:
        """Delete all events from a specific app. Returns count deleted."""
        with self._get_connection() as conn:
            # Events store app_name in the JSON data field
            cursor = conn.execute(
                "DELETE FROM events WHERE data LIKE ?",
                (f'%"app_name": "{app_name}"%',),
            )
            return cursor.rowcount

    def delete_events_by_type(self, event_type: str) -> int:
        """Delete all events of a specific type. Returns count deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE event_type = ?",
                (event_type,),
            )
            return cursor.rowcount

    def delete_session(self, session_id: str, delete_events: bool = True) -> bool:
        """Delete a session and optionally its events. Returns True if deleted."""
        with self._get_connection() as conn:
            if delete_events:
                conn.execute(
                    "DELETE FROM events WHERE session_id = ?",
                    (session_id,),
                )
                conn.execute(
                    "DELETE FROM screenshots WHERE session_id = ?",
                    (session_id,),
                )
            cursor = conn.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def redact_text_matching(self, pattern: str, replacement: str = "[REDACTED]") -> int:
        """Redact text events matching a pattern. Returns count modified."""
        import re
        count = 0
        with self._get_connection() as conn:
            # Get all text events
            rows = conn.execute(
                "SELECT id, data FROM events WHERE event_type = 'text'"
            ).fetchall()

            for row in rows:
                try:
                    data = json.loads(row["data"])
                    text = data.get("text", "")
                    if re.search(pattern, text, re.IGNORECASE):
                        data["text"] = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                        data["redacted"] = True
                        conn.execute(
                            "UPDATE events SET data = ? WHERE id = ?",
                            (json.dumps(data), row["id"]),
                        )
                        count += 1
                except Exception:
                    continue

            return count

    def delete_events_matching_url(self, url_pattern: str) -> int:
        """Delete window events matching a URL pattern. Returns count deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE event_type = 'window_change' AND data LIKE ?",
                (f'%{url_pattern}%',),
            )
            return cursor.rowcount

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        with self._get_connection() as conn:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            screenshots = conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]

            # Event breakdown
            event_types = conn.execute(
                "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type"
            ).fetchall()

            return {
                "sessions": sessions,
                "events": events,
                "screenshots": screenshots,
                "event_breakdown": {row["event_type"]: row["count"] for row in event_types},
            }

    def merge_events(self, pulsetime: float = 30.0) -> int:
        """Merge consecutive similar events within a time window.

        Inspired by ActivityWatch's heartbeat merging pattern.
        Merges clicks in the same app, reducing storage while preserving meaning.

        Args:
            pulsetime: Maximum seconds between events to consider them mergeable.

        Returns:
            Number of events removed through merging.
        """
        merged_count = 0

        with self._get_connection() as conn:
            # Get all click events ordered by session and timestamp
            rows = conn.execute(
                """SELECT id, timestamp, event_type, data, session_id
                   FROM events
                   WHERE event_type = 'click'
                   ORDER BY session_id, timestamp"""
            ).fetchall()

            if not rows:
                return 0

            # Group consecutive clicks that can be merged
            to_delete = []
            to_update = []
            i = 0

            while i < len(rows):
                base_row = rows[i]
                base_data = json.loads(base_row["data"])
                base_time = datetime.fromisoformat(base_row["timestamp"])
                count = 1
                last_time = base_time

                # Look for consecutive mergeable events
                j = i + 1
                while j < len(rows):
                    next_row = rows[j]

                    # Must be same session
                    if next_row["session_id"] != base_row["session_id"]:
                        break

                    next_time = datetime.fromisoformat(next_row["timestamp"])
                    time_diff = (next_time - last_time).total_seconds()

                    # Must be within pulsetime
                    if time_diff > pulsetime:
                        break

                    # For clicks, we just count them (don't need same position)
                    to_delete.append(next_row["id"])
                    count += 1
                    last_time = next_time
                    j += 1

                # If we merged any events, update the base event
                if count > 1:
                    base_data["merged_count"] = count
                    base_data["duration"] = (last_time - base_time).total_seconds()
                    to_update.append((json.dumps(base_data), base_row["id"]))

                i = j

            # Apply updates
            for data, event_id in to_update:
                conn.execute("UPDATE events SET data = ? WHERE id = ?", (data, event_id))

            # Delete merged events
            for event_id in to_delete:
                conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
                merged_count += 1

            return merged_count

    def compact(self, pulsetime: float = 30.0) -> dict[str, int]:
        """Compact the database by merging events and cleaning up.

        Returns dict with counts of actions taken.
        """
        results = {
            "events_merged": self.merge_events(pulsetime),
        }

        # Vacuum the database to reclaim space
        with self._get_connection() as conn:
            conn.execute("VACUUM")

        return results
