"""Main event coordinator for Peer."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, Union

from rich.console import Console
from rich.live import Live
from rich.table import Table

from peer.capture import CaptureReason, SmartScreenshotManager
from peer.config import Config, get_config
from peer.logger import KeyboardLogger, MouseLogger, WindowLogger
from peer.logger.keyboard import CommandEvent, KeyboardEvent, TextEvent
from peer.storage import Database, Event, Screenshot, Session

console = Console()


class EventCoordinator:
    """Coordinates all activity loggers and manages the event stream."""

    def __init__(
        self,
        session: Session,
        config: Config,
        verbose_callback: Optional[
            Callable[[str, str, dict[str, Any], dict[str, Any]], None]
        ] = None,
    ):
        self.session = session
        self.config = config
        self.db = Database(config.db_path)
        self._verbose_callback = verbose_callback

        # Initialize window logger first (needed by keyboard logger)
        self.window_logger = WindowLogger(on_event=self._on_window_event)

        # Initialize other loggers
        self.keyboard_logger = KeyboardLogger(
            on_event=self._on_keyboard_event,
            get_active_window=self.window_logger.get_active_window,
        )
        self.mouse_logger = MouseLogger(on_event=self._on_mouse_event)

        # Event counters for display
        self._event_counts = {
            "text": 0,
            "command": 0,
            "click": 0,
            "window_change": 0,
            "screenshot": 0,
            "session_start": 0,
            "session_stop": 0,
        }
        self._lock = threading.Lock()
        self._running = False

        # Smart screenshot manager
        self._screenshot_manager: Optional[SmartScreenshotManager] = None

        # Track last app for keyboard flush decisions
        self._last_app: str = ""

    def start(self) -> None:
        """Start all loggers."""
        self._running = True

        # Log session start event
        self._log_session_event("session_start")

        self.window_logger.start()
        self.keyboard_logger.start()
        self.mouse_logger.start()

        # Start smart screenshot capture if mode >= 2
        if self.session.mode >= 2:
            self._screenshot_manager = SmartScreenshotManager(
                screenshots_dir=self.config.screenshots_dir,
                session_id=self.session.id,
                on_capture=self._on_screenshot_capture,
            )
            self._screenshot_manager.start()

    def stop(self) -> None:
        """Stop all loggers."""
        self._running = False

        self.keyboard_logger.stop()
        self.mouse_logger.stop()
        self.window_logger.stop()

        if self._screenshot_manager:
            self._screenshot_manager.stop()

        # Log session stop event
        self._log_session_event("session_stop")

    def _log_session_event(self, event_type: str) -> None:
        """Log a session lifecycle event (start/stop)."""
        timestamp = datetime.now().isoformat()
        stats = self.get_stats() if event_type == "session_stop" else {}

        event_data = {
            "event_type": event_type,
            "session_id": self.session.id,
            "mode": self.session.mode,
        }

        # Include stats in stop event
        if event_type == "session_stop":
            event_data["stats"] = stats

        with self._lock:
            self._event_counts[event_type] += 1

        db_event = Event(
            timestamp=timestamp,
            event_type=event_type,
            data=event_data,
            session_id=self.session.id,
        )
        self.db.add_event(db_event)

        if self._verbose_callback:
            window_info = {"app": "peer", "title": "Session Lifecycle"}
            self._verbose_callback(event_type, timestamp, event_data, window_info)

    def _on_keyboard_event(self, event: KeyboardEvent) -> None:
        """Handle keyboard events (text or command)."""
        # Notify screenshot manager of activity
        if self._screenshot_manager:
            self._screenshot_manager.on_activity()

        event_data = event.to_dict()
        event_type = event_data.get("event_type", "text")

        with self._lock:
            self._event_counts[event_type] += 1

        db_event = Event(
            timestamp=event.timestamp,
            event_type=event_type,
            data=event_data,
            session_id=self.session.id,
        )
        self.db.add_event(db_event)

        if self._verbose_callback:
            # Get current window in real-time for accurate context
            window_info = self.window_logger.get_active_window()
            self._verbose_callback(event_type, event.timestamp, event_data, window_info)

    def _on_mouse_event(self, event) -> None:
        """Handle mouse events."""
        # Notify screenshot manager of activity
        if self._screenshot_manager:
            self._screenshot_manager.on_activity()

        with self._lock:
            self._event_counts["click"] += 1

        db_event = Event(
            timestamp=event.timestamp,
            event_type="click",
            data=event.to_dict(),
            session_id=self.session.id,
        )
        self.db.add_event(db_event)

        if self._verbose_callback:
            # Get current window in real-time for accurate context
            window_info = self.window_logger.get_active_window()
            self._verbose_callback("click", event.timestamp, event.to_dict(), window_info)

    def _on_window_event(self, event) -> None:
        """Handle window change events."""
        event_data = event.to_dict()

        # Only flush keyboard buffer on actual app change (not URL changes within same app)
        new_app = event_data.get("app_name", "")
        if new_app and new_app != self._last_app:
            self.keyboard_logger.flush_on_window_change()
            self._last_app = new_app

        # Notify screenshot manager of window change
        if self._screenshot_manager:
            window_info = {
                "app": event_data.get("app_name", ""),
                "title": event_data.get("window_title", ""),
                "url": event_data.get("url"),
                "document_path": event_data.get("document_path"),
            }
            self._screenshot_manager.on_window_change(window_info)

        with self._lock:
            self._event_counts["window_change"] += 1

        db_event = Event(
            timestamp=event.timestamp,
            event_type="window_change",
            data=event_data,
            session_id=self.session.id,
        )
        self.db.add_event(db_event)

        if self._verbose_callback:
            # For window changes, use the new window as context
            window_info = {
                "app": event_data.get("app_name", ""),
                "title": event_data.get("window_title", ""),
                "url": event_data.get("url"),
                "document_path": event_data.get("document_path"),
            }
            self._verbose_callback("window_change", event.timestamp, event_data, window_info)

    def _on_screenshot_capture(self, filepath: Path, reason: CaptureReason) -> None:
        """Handle smart screenshot capture."""
        timestamp = datetime.now().isoformat()

        screenshot = Screenshot(
            timestamp=timestamp,
            filepath=str(filepath),
            session_id=self.session.id,
        )
        self.db.add_screenshot(screenshot)

        with self._lock:
            self._event_counts["screenshot"] += 1

        if self._verbose_callback:
            window_info = self.window_logger.get_active_window()
            self._verbose_callback(
                "screenshot",
                timestamp,
                {"filepath": str(filepath), "reason": reason.trigger, "context": reason.context},
                window_info,
            )

    def get_stats(self) -> dict[str, int]:
        """Get current event counts."""
        with self._lock:
            return self._event_counts.copy()


def _format_location(window: dict[str, Any]) -> str:
    """Format location (URL or document path) for display."""
    url = window.get("url")
    doc_path = window.get("document_path")

    if url:
        # Extract domain from URL for cleaner display
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path
            if len(path) > 30:
                path = path[:27] + "..."
            return f"{domain}{path}"
        except Exception:
            if len(url) > 40:
                return url[:37] + "..."
            return url
    elif doc_path:
        # Show just filename for document paths
        if "/" in doc_path:
            return "~/" + doc_path.split("/")[-1]
        return doc_path

    return ""


def _format_event(
    event_type: str, timestamp: str, data: dict, window: dict[str, Any]
) -> str:
    """Format an event for verbose output.

    Format: TIME APP LOCATION TYPE DATA
    """
    # Extract just the time portion from ISO timestamp
    time_str = timestamp.split("T")[1].split(".")[0] if "T" in timestamp else timestamp

    # Format app with fixed width
    app = window.get("app", "")[:15].ljust(15)

    # Format location (URL or document path) or fall back to title
    location = _format_location(window)
    if not location:
        location = window.get("title", "")
    if len(location) > 35:
        location = location[:32] + "..."
    location = location.ljust(35)

    if event_type == "text":
        text = data.get("text", "")
        masked = data.get("masked", False)
        if masked:
            detail = "[masked]"
        else:
            # Escape newlines and show text in quotes
            display_text = text.replace("\n", "↵").replace("\t", "→")
            if len(display_text) > 50:
                display_text = display_text[:47] + "..."
            detail = f'"{display_text}"'
        return f"[dim]{time_str}[/dim] {app} {location} [yellow]TEXT[/yellow]   {detail}"

    elif event_type == "command":
        key = data.get("key", "")
        mods = data.get("modifiers", [])
        # Format as Cmd+S style
        mod_str = "+".join(m.capitalize() for m in sorted(mods))
        if mod_str:
            detail = f"{mod_str}+{key.upper()}"
        else:
            detail = key.upper()
        return f"[dim]{time_str}[/dim] {app} {location} [cyan]CMD[/cyan]    {detail}"

    elif event_type == "click":
        x, y = data.get("x", 0), data.get("y", 0)
        button = data.get("button", "unknown")
        detail = f"{button} ({x},{y})"
        return f"[dim]{time_str}[/dim] {app} {location} [blue]CLICK[/blue]  {detail}"

    elif event_type == "window_change":
        # For window change, show the new window info with URL if available
        new_app = data.get("app_name", "")
        url = data.get("url")
        doc_path = data.get("document_path")

        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                detail = f"→ {new_app}: {parsed.netloc}{parsed.path[:30]}"
            except Exception:
                detail = f"→ {new_app}: {url[:40]}"
        elif doc_path:
            detail = f"→ {new_app}: {doc_path.split('/')[-1]}"
        else:
            new_title = data.get("window_title", "")
            if len(new_title) > 35:
                new_title = new_title[:32] + "..."
            detail = f"→ {new_app}: {new_title}"

        return f"[dim]{time_str}[/dim] {app} {location} [green]WINDOW[/green] {detail}"

    elif event_type == "screenshot":
        filepath = data.get("filepath", "")
        filename = filepath.split("/")[-1] if "/" in filepath else filepath
        reason = data.get("reason", "periodic")
        reason_map = {
            "new_domain": "🆕",
            "idle": "📖",
            "content_page": "📄",
            "app_switch": "🔄",
            "periodic": "⏱️",
        }
        icon = reason_map.get(reason, "📸")
        return f"[dim]{time_str}[/dim] {app} {location} [magenta]SCREEN[/magenta] {icon} {reason}: {filename}"

    elif event_type == "session_start":
        session_id = data.get("session_id", "")[:8]
        mode = data.get("mode", 1)
        return f"[dim]{time_str}[/dim] [bold green]▶ SESSION START[/bold green] id={session_id}... mode={mode}"

    elif event_type == "session_stop":
        session_id = data.get("session_id", "")[:8]
        stats = data.get("stats", {})
        stats_str = f"text={stats.get('text', 0)} cmd={stats.get('command', 0)} clicks={stats.get('click', 0)} windows={stats.get('window_change', 0)}"
        return f"[dim]{time_str}[/dim] [bold red]■ SESSION STOP[/bold red]  id={session_id}... {stats_str}"

    return f"[dim]{time_str}[/dim] {app} {location} [{event_type}] {data}"


def run_foreground(session: Session, config: Config, verbose: bool = False) -> None:
    """Run the logging session in the foreground with live status display."""

    def verbose_callback(
        event_type: str, timestamp: str, data: dict, window: dict[str, str]
    ) -> None:
        """Print events in real-time."""
        formatted = _format_event(event_type, timestamp, data, window)
        console.print(formatted)

    callback = verbose_callback if verbose else None
    coordinator = EventCoordinator(session, config, verbose_callback=callback)
    coordinator.start()

    mode_descriptions = {
        1: "Logs only",
        2: "Logs + screenshots",
        3: "Logs + screenshots + AI summaries",
        4: "Logs + screenshots + real-time AI",
    }

    if verbose:
        # In verbose mode, just stream events without the live table
        console.print(
            f"[cyan]Session:[/cyan] {session.id[:8]}... | "
            f"[cyan]Mode:[/cyan] {session.mode} ({mode_descriptions[session.mode]})"
        )
        # Print column headers
        console.print(
            f"[bold]{'TIME':<8} {'APP':<15} {'LOCATION':<35} {'TYPE':<6} DATA[/bold]"
        )
        console.print("[dim]─" * 90 + "[/dim]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            coordinator.stop()
            stats = coordinator.get_stats()
            console.print("[dim]─" * 90 + "[/dim]")
            console.print(
                f"[cyan]Total:[/cyan] {stats['text']} text inputs, "
                f"{stats['command']} commands, "
                f"{stats['click']} clicks, {stats['window_change']} window changes"
            )
            if session.mode >= 2:
                console.print(f"[cyan]Screenshots:[/cyan] {stats['screenshot']}")
            console.print("[yellow]Session paused. Use 'peer stop' to end.[/yellow]")
    else:
        # Normal mode with live table
        def make_table() -> Table:
            stats = coordinator.get_stats()
            table = Table(title="Peer - Live Activity")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Session", session.id[:8] + "...")
            table.add_row("Mode", f"{session.mode} ({mode_descriptions[session.mode]})")
            table.add_row("Duration", _format_duration(session.start_time))
            table.add_row("Text Inputs", str(stats["text"]))
            table.add_row("Commands", str(stats["command"]))
            table.add_row("Clicks", str(stats["click"]))
            table.add_row("Window Changes", str(stats["window_change"]))
            if session.mode >= 2:
                table.add_row("Screenshots", str(stats["screenshot"]))

            return table

        try:
            with Live(make_table(), refresh_per_second=2, console=console) as live:
                while True:
                    live.update(make_table())
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            coordinator.stop()
            console.print("[yellow]Session paused. Use 'peer stop' to end.[/yellow]")


def run_background(session: Session, config: Config) -> None:
    """Run the logging session in the background with system tray."""
    from peer.tray import run_tray

    coordinator = EventCoordinator(session, config)
    coordinator.start()

    try:
        run_tray(session, config, coordinator)
    finally:
        coordinator.stop()


def _format_duration(start_time: str) -> str:
    """Format duration from start time to now."""
    start = datetime.fromisoformat(start_time)
    delta = datetime.now() - start
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
