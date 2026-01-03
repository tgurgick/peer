"""Smart screenshot capture with strategic triggers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set
from urllib.parse import urlparse

from peer.capture.screen import capture_screen


@dataclass
class CaptureReason:
    """Reason for taking a screenshot."""
    trigger: str  # "new_domain", "idle", "content_page", "app_switch"
    context: str  # Additional context


class SmartScreenshotManager:
    """Manages strategic screenshot capture based on user activity."""

    # Idle threshold - capture after this many seconds of no activity
    IDLE_THRESHOLD = 5.0

    # Minimum time between screenshots (avoid rapid captures)
    MIN_CAPTURE_INTERVAL = 3.0

    # Content page indicators in URL paths
    CONTENT_INDICATORS = {
        "/article", "/post", "/blog", "/news", "/story",
        "/doc", "/docs", "/wiki", "/page", "/content",
        "/search", "/results", "/watch", "/video",
    }

    # Domains that are always content-heavy
    CONTENT_DOMAINS = {
        "medium.com", "substack.com", "notion.so", "wikipedia.org",
        "github.com", "stackoverflow.com", "reddit.com",
        "youtube.com", "twitter.com", "x.com",
    }

    def __init__(
        self,
        screenshots_dir: Path,
        session_id: str,
        on_capture: Optional[Callable[[Path, CaptureReason], None]] = None,
    ):
        self.screenshots_dir = screenshots_dir
        self.session_id = session_id
        self.on_capture = on_capture

        # State tracking
        self._seen_domains: Set[str] = set()
        self._last_activity_time: float = time.time()
        self._last_capture_time: float = 0
        self._last_url: Optional[str] = None
        self._last_app: Optional[str] = None

        # Idle timer
        self._idle_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._running = False

        # Pending capture info (for when we detect something worth capturing)
        self._pending_capture_reason: Optional[CaptureReason] = None

    def start(self) -> None:
        """Start the smart capture manager."""
        self._running = True
        self._last_activity_time = time.time()

    def stop(self) -> None:
        """Stop the smart capture manager."""
        self._running = False
        self._cancel_idle_timer()

    def on_activity(self) -> None:
        """Called when user activity is detected (keyboard/mouse)."""
        with self._lock:
            self._last_activity_time = time.time()
            self._reset_idle_timer()

    def on_window_change(self, window_info: dict[str, Any]) -> None:
        """Called when window/URL changes."""
        if not self._running:
            return

        app = window_info.get("app", "")
        url = window_info.get("url")

        with self._lock:
            self._last_activity_time = time.time()

            # Check for app switch
            if app and app != self._last_app:
                self._last_app = app
                # Capture on significant app switch (not just to finder/system)
                if app not in ("Finder", "SystemUIServer", "Dock"):
                    self._maybe_capture(CaptureReason(
                        trigger="app_switch",
                        context=f"Switched to {app}"
                    ))

            # Check for URL-based triggers
            if url:
                self._check_url_triggers(url)
                self._last_url = url

            self._reset_idle_timer()

    def _check_url_triggers(self, url: str) -> None:
        """Check if URL warrants a screenshot."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix for comparison
            if domain.startswith("www."):
                domain = domain[4:]

            # New domain trigger
            if domain and domain not in self._seen_domains:
                self._seen_domains.add(domain)
                self._maybe_capture(CaptureReason(
                    trigger="new_domain",
                    context=f"First visit to {domain}"
                ))
                return

            # Content page trigger
            if self._is_content_page(parsed, domain):
                # Only capture if URL path changed significantly
                if self._last_url:
                    last_parsed = urlparse(self._last_url)
                    if parsed.path != last_parsed.path:
                        self._maybe_capture(CaptureReason(
                            trigger="content_page",
                            context=f"Content page: {domain}{parsed.path[:30]}"
                        ))

        except Exception:
            pass

    def _is_content_page(self, parsed, domain: str) -> bool:
        """Determine if URL is likely a content page."""
        # Check if domain is content-heavy
        for content_domain in self.CONTENT_DOMAINS:
            if domain.endswith(content_domain):
                return True

        # Check path for content indicators
        path_lower = parsed.path.lower()
        for indicator in self.CONTENT_INDICATORS:
            if indicator in path_lower:
                return True

        # Long paths often indicate content (not homepage)
        if parsed.path.count("/") >= 2 and len(parsed.path) > 20:
            return True

        return False

    def _maybe_capture(self, reason: CaptureReason) -> None:
        """Capture if enough time has passed since last capture."""
        now = time.time()

        if now - self._last_capture_time < self.MIN_CAPTURE_INTERVAL:
            # Too soon, save reason for potential later capture
            self._pending_capture_reason = reason
            return

        self._do_capture(reason)

    def _do_capture(self, reason: CaptureReason) -> None:
        """Actually perform the capture."""
        self._last_capture_time = time.time()
        self._pending_capture_reason = None

        filepath = capture_screen(self.screenshots_dir, self.session_id)
        if filepath and self.on_capture:
            self.on_capture(filepath, reason)

    def _on_idle_timeout(self) -> None:
        """Called when user has been idle for IDLE_THRESHOLD seconds."""
        with self._lock:
            if not self._running:
                return

            # Capture if we have a pending reason or just because of idle
            reason = self._pending_capture_reason or CaptureReason(
                trigger="idle",
                context="User idle - likely reading content"
            )
            self._do_capture(reason)

    def _reset_idle_timer(self) -> None:
        """Reset the idle timer."""
        self._cancel_idle_timer()
        if self._running:
            self._idle_timer = threading.Timer(
                self.IDLE_THRESHOLD, self._on_idle_timeout
            )
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        """Cancel the idle timer."""
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None
