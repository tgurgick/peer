"""Global hotkey listener for toggling peer monitoring."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import Optional, Set

from pynput import keyboard

from rich.console import Console

console = Console()


class HotkeyListener:
    """Listens for global hotkey to toggle peer monitoring."""

    # Default hotkey: Ctrl + Shift + Left Arrow
    HOTKEY_KEYS = {keyboard.Key.ctrl, keyboard.Key.shift, keyboard.Key.left}

    def __init__(self):
        self._listener: Optional[keyboard.Listener] = None
        self._pressed_keys: Set[keyboard.Key] = set()
        self._running = False
        self._monitoring_active = False
        self._lock = threading.Lock()
        self._last_toggle_time = 0.0
        # Debounce time to prevent rapid toggling
        self._debounce_seconds = 1.0

    def start(self) -> None:
        """Start listening for hotkey."""
        if self._running:
            return

        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

        # Check if peer is already running
        self._monitoring_active = self._is_peer_running()

        status = "[green]active[/green]" if self._monitoring_active else "[dim]inactive[/dim]"
        console.print(f"[cyan]Peer hotkey daemon started[/cyan]")
        console.print(f"  Hotkey: [bold]Ctrl + Shift + Left Arrow[/bold]")
        console.print(f"  Current status: {status}")
        console.print(f"  Press hotkey to toggle monitoring")
        console.print(f"  Press Ctrl+C to exit daemon")

    def stop(self) -> None:
        """Stop listening for hotkey."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """Handle key press."""
        if not self._running:
            return

        # Normalize key (handle left/right variants)
        normalized = self._normalize_key(key)
        if normalized:
            self._pressed_keys.add(normalized)

        # Check if hotkey combination is pressed
        if self._is_hotkey_pressed():
            self._toggle_monitoring()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """Handle key release."""
        normalized = self._normalize_key(key)
        if normalized:
            self._pressed_keys.discard(normalized)

    def _normalize_key(self, key) -> Optional[keyboard.Key]:
        """Normalize key variants (e.g., shift_l -> shift)."""
        if key is None:
            return None

        # Map variants to base keys
        key_map = {
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
        }

        if key in key_map:
            return key_map[key]

        if isinstance(key, keyboard.Key):
            return key

        return None

    def _is_hotkey_pressed(self) -> bool:
        """Check if the hotkey combination is currently pressed."""
        return self.HOTKEY_KEYS.issubset(self._pressed_keys)

    def _toggle_monitoring(self) -> None:
        """Toggle peer monitoring on/off."""
        with self._lock:
            # Debounce
            now = time.time()
            if now - self._last_toggle_time < self._debounce_seconds:
                return
            self._last_toggle_time = now

            if self._monitoring_active:
                self._stop_monitoring()
            else:
                self._start_monitoring()

    def _start_monitoring(self) -> None:
        """Start peer monitoring in a new Terminal window with streaming output."""
        console.print("\n[cyan]Starting peer monitoring...[/cyan]")
        try:
            # Use AppleScript to open a new Terminal window with peer start -v
            # This gives the user a visible window with streaming output
            script = f'''
            tell application "Terminal"
                activate
                do script "peer start -v"
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                self._monitoring_active = True
                console.print("[green]✓ Peer monitoring started in new Terminal window[/green]")
            else:
                console.print(f"[red]Failed to start: {result.stderr}[/red]")
        except Exception as e:
            console.print(f"[red]Error starting peer: {e}[/red]")

    def _stop_monitoring(self) -> None:
        """Stop peer monitoring."""
        console.print("\n[yellow]Stopping peer monitoring...[/yellow]")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "peer.cli", "stop"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                self._monitoring_active = False
                console.print("[green]✓ Peer monitoring stopped[/green]")
            else:
                # May already be stopped
                self._monitoring_active = False
                console.print("[dim]Peer monitoring stopped[/dim]")
        except Exception as e:
            console.print(f"[red]Error stopping peer: {e}[/red]")

    def _is_peer_running(self) -> bool:
        """Check if peer monitoring is currently running."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "peer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            # If status returns success and mentions "active", monitoring is running
            return "active" in result.stdout.lower() or result.returncode == 0 and "session" in result.stdout.lower()
        except Exception:
            return False

    def run(self) -> None:
        """Run the hotkey listener (blocking)."""
        self.start()
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            console.print("\n[dim]Hotkey daemon stopped[/dim]")


def run_hotkey_daemon() -> None:
    """Run the hotkey daemon."""
    listener = HotkeyListener()
    listener.run()
