"""Active window tracker for macOS."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

try:
    from AppKit import NSRunningApplication
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListOptionOnScreenOnly,
    )

    MACOS_AVAILABLE = True
except ImportError:
    MACOS_AVAILABLE = False
    NSRunningApplication = None  # type: ignore


@dataclass
class WindowEvent:
    """A window focus change event."""

    timestamp: str
    app_name: str
    window_title: str
    bundle_id: Optional[str] = None
    url: Optional[str] = None  # For browsers
    document_path: Optional[str] = None  # For document-based apps
    is_private: bool = False  # Incognito/private browsing mode

    def to_dict(self) -> dict[str, Any]:
        result = {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "bundle_id": self.bundle_id,
        }
        if self.url:
            result["url"] = self.url
        if self.document_path:
            result["document_path"] = self.document_path
        if self.is_private:
            result["is_private"] = self.is_private
        return result


class WindowLogger:
    """Tracks active window changes on macOS."""

    def __init__(
        self,
        on_event: Callable[[WindowEvent], None],
        poll_interval: float = 0.5,
        blocked_apps: Optional[set] = None,
        blocked_bundles: Optional[set] = None,
    ):
        self.on_event = on_event
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_window: Optional[dict[str, str]] = None
        self._blocked_apps = blocked_apps or set()
        self._blocked_bundles = blocked_bundles or set()

    def is_blocked(self, app_name: str, bundle_id: Optional[str]) -> bool:
        """Check if an app is blocked from logging."""
        if app_name in self._blocked_apps:
            return True
        if bundle_id and bundle_id in self._blocked_bundles:
            return True
        return False

    def start(self) -> None:
        """Start tracking window changes."""
        if not MACOS_AVAILABLE:
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop tracking window changes."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def get_active_window(self) -> dict[str, Any]:
        """Get the currently active window info.

        Uses AppleScript to get the frontmost app (most reliable method),
        then CGWindowListCopyWindowInfo for the window title.
        """
        if not MACOS_AVAILABLE:
            return {"app": "", "title": "", "bundle_id": "", "url": None, "document_path": None, "is_private": False}

        try:
            # Use AppleScript to get frontmost app - most reliable method
            script = '''
            tell application "System Events"
                set frontApp to first application process whose frontmost is true
                set appName to name of frontApp
                set bundleId to bundle identifier of frontApp
                return appName & "|" & bundleId
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=1.0,
            )

            if result.returncode != 0:
                return self._get_active_window_fallback()

            parts = result.stdout.strip().split("|")
            if len(parts) != 2:
                return self._get_active_window_fallback()

            app_name, bundle_id = parts

            # Get window title using Quartz
            window_title = self._get_window_title_for_app(app_name)

            # Check for private browsing mode
            is_private = self._is_private_browsing(app_name, bundle_id, window_title)

            # Skip URL capture for private browsing (privacy protection)
            if is_private:
                url = None
                document_path = None
            else:
                # Get URL or document path based on app type
                url = self._get_browser_url(app_name, bundle_id)
                document_path = self._get_document_path(app_name, bundle_id) if not url else None

            return {
                "app": app_name,
                "title": window_title,
                "bundle_id": bundle_id,
                "url": url,
                "document_path": document_path,
                "is_private": is_private,
            }
        except Exception:
            return self._get_active_window_fallback()

    def _get_active_window_fallback(self) -> dict[str, Any]:
        """Fallback method using CGWindowListCopyWindowInfo."""
        try:
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )

            if not window_list:
                return {"app": "", "title": "", "bundle_id": "", "url": None, "document_path": None, "is_private": False}

            system_owners = {
                "Window Server", "Dock", "SystemUIServer",
                "Control Center", "Notification Center", "Spotlight",
            }

            for window in window_list:
                layer = window.get("kCGWindowLayer", -1)
                owner_name = window.get("kCGWindowOwnerName", "")

                if layer != 0 or not owner_name or owner_name in system_owners:
                    continue

                pid = window.get("kCGWindowOwnerPID", 0)
                window_title = window.get("kCGWindowName", "") or ""

                bundle_id = ""
                if pid:
                    try:
                        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                        if app:
                            bundle_id = app.bundleIdentifier() or ""
                    except Exception:
                        pass

                # Check for private browsing
                is_private = self._is_private_browsing(owner_name, bundle_id, window_title)

                # Skip URL capture for private browsing
                if is_private:
                    url = None
                    document_path = None
                else:
                    url = self._get_browser_url(owner_name, bundle_id)
                    document_path = self._get_document_path(owner_name, bundle_id) if not url else None

                return {
                    "app": owner_name,
                    "title": window_title,
                    "bundle_id": bundle_id,
                    "url": url,
                    "document_path": document_path,
                    "is_private": is_private,
                }

            return {"app": "", "title": "", "bundle_id": "", "url": None, "document_path": None, "is_private": False}
        except Exception:
            return {"app": "", "title": "", "bundle_id": "", "url": None, "document_path": None, "is_private": False}

    def _get_window_title_for_app(self, app_name: str) -> str:
        """Get the window title for an app by name."""
        try:
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )
            if not window_list:
                return ""

            for window in window_list:
                if window.get("kCGWindowOwnerName") == app_name:
                    layer = window.get("kCGWindowLayer", -1)
                    if layer == 0:
                        title = window.get("kCGWindowName", "")
                        if title:
                            return title
            return ""
        except Exception:
            return ""

    def _get_window_title(self, pid: int) -> str:
        """Get the window title for a given process ID."""
        try:
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )
            if window_list is None:
                return ""

            for window in window_list:
                if window.get("kCGWindowOwnerPID") == pid:
                    title = window.get("kCGWindowName", "")
                    if title:
                        return title
            return ""
        except Exception:
            return ""

    def _get_browser_url(self, app_name: str, bundle_id: str) -> Optional[str]:
        """Get the current URL from a browser."""
        # Map of browser bundle IDs to their AppleScript commands
        browser_scripts = {
            "com.google.Chrome": 'tell application "Google Chrome" to return URL of active tab of front window',
            "com.apple.Safari": 'tell application "Safari" to return URL of front document',
            "company.thebrowser.Browser": 'tell application "Arc" to return URL of active tab of front window',
            "org.mozilla.firefox": 'tell application "Firefox" to return URL of active tab of front window',
            "com.brave.Browser": 'tell application "Brave Browser" to return URL of active tab of front window',
            "com.microsoft.edgemac": 'tell application "Microsoft Edge" to return URL of active tab of front window',
        }

        script = browser_scripts.get(bundle_id)
        if not script:
            return None

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                return url if url else None
        except Exception:
            pass
        return None

    def _get_document_path(self, app_name: str, bundle_id: str) -> Optional[str]:
        """Get the current document path from document-based apps."""
        # Apps that support getting document path
        doc_app_scripts = {
            "com.apple.TextEdit": 'tell application "TextEdit" to return path of front document',
            "com.apple.Preview": 'tell application "Preview" to return path of front document',
            "com.microsoft.Word": 'tell application "Microsoft Word" to return path of active document',
            "com.microsoft.Excel": 'tell application "Microsoft Excel" to return path of active workbook',
            "com.apple.finder": 'tell application "Finder" to return POSIX path of (target of front window as alias)',
        }

        # VS Code and similar editors - get from window title (usually shows path)
        if bundle_id in ("com.microsoft.VSCode", "com.todesktop.230313mzl4w4u92"):
            # These apps show file path in title, already captured
            return None

        script = doc_app_scripts.get(bundle_id)
        if not script:
            return None

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=0.5,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                return path if path else None
        except Exception:
            pass
        return None

    def _is_private_browsing(self, app_name: str, bundle_id: str, window_title: str) -> bool:
        """Detect if browser is in private/incognito mode.

        Inspired by ActivityWatch's aw-watcher-web incognito detection.
        """
        # Common private window title indicators
        private_indicators = [
            "incognito",
            "private",
            "inprivate",  # Edge
            "private browsing",  # Firefox/Safari
        ]

        title_lower = window_title.lower()
        for indicator in private_indicators:
            if indicator in title_lower:
                return True

        # Browser-specific AppleScript detection
        browser_private_scripts = {
            "com.google.Chrome": '''
                tell application "Google Chrome"
                    if (count of windows) > 0 then
                        return mode of front window is "incognito"
                    end if
                    return false
                end tell
            ''',
            "com.apple.Safari": '''
                tell application "Safari"
                    if (count of windows) > 0 then
                        return private browsing of front window
                    end if
                    return false
                end tell
            ''',
            "com.brave.Browser": '''
                tell application "Brave Browser"
                    if (count of windows) > 0 then
                        return mode of front window is "incognito"
                    end if
                    return false
                end tell
            ''',
        }

        script = browser_private_scripts.get(bundle_id)
        if script:
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                )
                if result.returncode == 0:
                    return result.stdout.strip().lower() == "true"
            except Exception:
                pass

        return False

    def _is_meaningful_change(self, current: dict[str, Any], last: Optional[dict[str, Any]]) -> bool:
        """Determine if window change is meaningful (not just title flicker)."""
        if last is None:
            return True

        # App change is always meaningful
        if current.get("app") != last.get("app"):
            return True

        # For browsers: check if URL domain/path changed significantly
        curr_url = current.get("url") or ""
        last_url = last.get("url") or ""

        if curr_url or last_url:
            try:
                from urllib.parse import urlparse
                curr_parsed = urlparse(curr_url) if curr_url else None
                last_parsed = urlparse(last_url) if last_url else None

                # Domain change is meaningful
                if (curr_parsed and last_parsed and
                    curr_parsed.netloc != last_parsed.netloc):
                    return True

                # Significant path change is meaningful (not just query params)
                if (curr_parsed and last_parsed and
                    curr_parsed.netloc == last_parsed.netloc):
                    # Same domain - check if path changed
                    if curr_parsed.path != last_parsed.path:
                        return True
                    # Same path - not meaningful (just query/fragment change)
                    return False

                # URL appeared or disappeared
                if bool(curr_url) != bool(last_url):
                    return True

            except Exception:
                pass

        # For document-based apps: check if document changed
        curr_doc = current.get("document_path") or ""
        last_doc = last.get("document_path") or ""
        if curr_doc != last_doc:
            return True

        # Title-only changes within same URL/doc are not meaningful
        return False

    def _poll_loop(self) -> None:
        """Poll for window changes."""
        while self._running:
            try:
                current = self.get_active_window()
                app_name = current.get("app", "")
                bundle_id = current.get("bundle_id")

                # Skip blocked apps entirely
                if self.is_blocked(app_name, bundle_id):
                    # Still update last_window to avoid re-logging when leaving blocked app
                    self._last_window = current
                    time.sleep(self.poll_interval)
                    continue

                # Check if this is a meaningful change
                if app_name and self._is_meaningful_change(current, self._last_window):
                    self._last_window = current

                    event = WindowEvent(
                        timestamp=datetime.now().isoformat(),
                        app_name=app_name,
                        window_title=current["title"],
                        bundle_id=bundle_id,
                        url=current.get("url"),
                        document_path=current.get("document_path"),
                        is_private=current.get("is_private", False),
                    )
                    self.on_event(event)

            except Exception:
                pass

            time.sleep(self.poll_interval)

    @property
    def is_running(self) -> bool:
        return self._running
