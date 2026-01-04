"""AFK (Away From Keyboard) detection.

Inspired by ActivityWatch's aw-watcher-afk.
Tracks user idle state based on input activity.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional


@dataclass
class AFKEvent:
    """AFK status change event."""

    timestamp: str
    status: str  # "afk" or "active"
    idle_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "idle_seconds": self.idle_seconds,
            "event_type": "afk_status",
        }


class AFKDetector:
    """Detects when user is away from keyboard.

    Uses macOS HIDIdleTime to get system-wide idle time,
    which tracks time since last keyboard/mouse input.
    """

    # Seconds of inactivity before considered AFK
    AFK_THRESHOLD = 180.0  # 3 minutes

    # How often to check idle state
    CHECK_INTERVAL = 10.0  # seconds

    def __init__(
        self,
        on_status_change: Optional[Callable[[AFKEvent], None]] = None,
        afk_threshold: float = AFK_THRESHOLD,
    ):
        self.on_status_change = on_status_change
        self.afk_threshold = afk_threshold
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_afk = False
        self._afk_since: Optional[datetime] = None

    def start(self) -> None:
        """Start AFK detection."""
        if self._running:
            return

        self._running = True
        self._is_afk = False
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop AFK detection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                idle_seconds = self._get_idle_time()
                was_afk = self._is_afk

                if idle_seconds >= self.afk_threshold:
                    if not self._is_afk:
                        # Transition to AFK
                        self._is_afk = True
                        self._afk_since = datetime.now()
                        self._emit_status_change("afk", idle_seconds)
                else:
                    if self._is_afk:
                        # Transition to active
                        self._is_afk = False
                        self._emit_status_change("active", idle_seconds)

            except Exception:
                pass  # Silently continue on errors

            time.sleep(self.CHECK_INTERVAL)

    def _get_idle_time(self) -> float:
        """Get system idle time in seconds using macOS ioreg."""
        try:
            # Use ioreg to get HIDIdleTime (nanoseconds since last input)
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )

            # Parse HIDIdleTime from output
            for line in result.stdout.split("\n"):
                if "HIDIdleTime" in line:
                    # Format: "HIDIdleTime" = 1234567890
                    parts = line.split("=")
                    if len(parts) >= 2:
                        nanoseconds = int(parts[1].strip())
                        return nanoseconds / 1_000_000_000.0

            return 0.0
        except Exception:
            return 0.0

    def _emit_status_change(self, status: str, idle_seconds: float) -> None:
        """Emit AFK status change event."""
        if self.on_status_change:
            event = AFKEvent(
                timestamp=datetime.now().isoformat(),
                status=status,
                idle_seconds=idle_seconds,
            )
            self.on_status_change(event)

    @property
    def is_afk(self) -> bool:
        """Check if user is currently AFK."""
        return self._is_afk

    @property
    def is_running(self) -> bool:
        return self._running
