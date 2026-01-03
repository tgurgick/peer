"""Tests for the database module."""

import tempfile
from pathlib import Path

import pytest

from peer.storage.database import Database, Event, Screenshot, Session


class TestDatabase:
    """Test database operations."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield Database(db_path)

    def test_create_session(self, db):
        """Test session creation."""
        session = db.create_session(mode=1)
        assert session.id is not None
        assert session.mode == 1
        assert session.start_time is not None
        assert session.end_time is None

    def test_get_session(self, db):
        """Test retrieving a session by ID."""
        session = db.create_session(mode=2)
        retrieved = db.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.mode == 2

    def test_get_active_session(self, db):
        """Test getting active session."""
        session = db.create_session(mode=1)
        active = db.get_active_session()
        assert active is not None
        assert active.id == session.id

    def test_end_session(self, db):
        """Test ending a session."""
        session = db.create_session(mode=1)
        db.end_session(session.id, summary="Test summary", total_cost=0.05)

        ended = db.get_session(session.id)
        assert ended.end_time is not None
        assert ended.summary == "Test summary"
        assert ended.total_cost == 0.05

    def test_add_event(self, db):
        """Test adding events."""
        session = db.create_session(mode=1)
        event = Event(
            timestamp="2024-01-01T12:00:00",
            event_type="click",
            data={"x": 100, "y": 200, "button": "left"},
            session_id=session.id,
        )
        event_id = db.add_event(event)
        assert event_id > 0

    def test_get_session_events(self, db):
        """Test retrieving session events."""
        session = db.create_session(mode=1)

        for i in range(5):
            event = Event(
                timestamp=f"2024-01-01T12:00:0{i}",
                event_type="click",
                data={"x": i * 10, "y": i * 20},
                session_id=session.id,
            )
            db.add_event(event)

        events = db.get_session_events(session.id)
        assert len(events) == 5

    def test_get_session_events_with_limit(self, db):
        """Test retrieving session events with limit."""
        session = db.create_session(mode=1)

        for i in range(10):
            event = Event(
                timestamp=f"2024-01-01T12:00:0{i}",
                event_type="click",
                data={"x": i},
                session_id=session.id,
            )
            db.add_event(event)

        events = db.get_session_events(session.id, limit=3)
        assert len(events) == 3

    def test_add_screenshot(self, db):
        """Test adding screenshots."""
        session = db.create_session(mode=2)
        screenshot = Screenshot(
            timestamp="2024-01-01T12:00:00",
            filepath="/tmp/screenshot.png",
            session_id=session.id,
        )
        screenshot_id = db.add_screenshot(screenshot)
        assert screenshot_id > 0

    def test_get_session_screenshots(self, db):
        """Test retrieving session screenshots."""
        session = db.create_session(mode=2)

        for i in range(3):
            screenshot = Screenshot(
                timestamp=f"2024-01-01T12:00:0{i}",
                filepath=f"/tmp/screenshot_{i}.png",
                session_id=session.id,
            )
            db.add_screenshot(screenshot)

        screenshots = db.get_session_screenshots(session.id)
        assert len(screenshots) == 3

    def test_export_session_json(self, db):
        """Test exporting session to JSON."""
        session = db.create_session(mode=1)

        event = Event(
            timestamp="2024-01-01T12:00:00",
            event_type="text",
            data={"text": "hello", "masked": False},
            session_id=session.id,
        )
        db.add_event(event)

        export = db.export_session_json(session.id)
        assert "session" in export
        assert "events" in export
        assert "screenshots" in export
        assert len(export["events"]) == 1

    def test_update_session_cost(self, db):
        """Test updating session cost."""
        session = db.create_session(mode=3)

        db.update_session_cost(session.id, 0.01)
        db.update_session_cost(session.id, 0.02)

        updated = db.get_session(session.id)
        assert updated.total_cost == pytest.approx(0.03)
