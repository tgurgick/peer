"""Keyboard event logger with text aggregation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union

from pynput import keyboard

from peer.privacy.filter import is_sensitive_context, mask_if_sensitive


@dataclass
class TextEvent:
    """Aggregated text input event."""

    timestamp: str
    text: str
    masked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "masked": self.masked,
            "event_type": "text",
        }


@dataclass
class CommandEvent:
    """A keyboard command event (modifier + key)."""

    timestamp: str
    key: str
    modifiers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "modifiers": self.modifiers,
            "event_type": "command",
        }


# Union type for keyboard events
KeyboardEvent = Union[TextEvent, CommandEvent]


class KeyboardLogger:
    """Captures keyboard events with text aggregation and command detection."""

    # Time in seconds to wait before flushing text buffer
    # Longer timeout = captures full queries like "I want to test an MCP service"
    FLUSH_TIMEOUT = 2.0

    def __init__(
        self,
        on_event: Callable[[KeyboardEvent], None],
        get_active_window: Optional[Callable[[], dict[str, Any]]] = None,
        on_window_change: Optional[Callable[[], None]] = None,
    ):
        self.on_event = on_event
        self.get_active_window = get_active_window
        self._listener: Optional[keyboard.Listener] = None
        self._current_modifiers: set[str] = set()
        self._running = False

        # Text buffer for aggregation
        self._text_buffer: list[str] = []
        self._buffer_lock = threading.Lock()
        self._buffer_start_time: Optional[str] = None
        self._buffer_masked = False

        # Flush timer
        self._flush_timer: Optional[threading.Timer] = None

    def start(self) -> None:
        """Start listening for keyboard events."""
        if self._running:
            return

        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        self._running = False
        self._cancel_flush_timer()
        self._flush_buffer()  # Flush any remaining text

        if self._listener:
            self._listener.stop()
            self._listener = None

    def flush_on_window_change(self) -> None:
        """Called when window changes - flush any pending text."""
        self._flush_buffer()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if not self._running:
            return

        key_str = self._key_to_string(key)
        if key_str is None:
            return

        # Track modifiers
        if key_str in ("ctrl", "alt", "cmd", "shift"):
            self._current_modifiers.add(key_str)
            return

        # Check if this is a command (has non-shift modifier)
        has_command_modifier = bool(
            self._current_modifiers - {"shift"}
        )

        if has_command_modifier:
            # This is a command - flush any pending text first
            self._flush_buffer()
            self._emit_command(key_str)
        else:
            # This is regular text input
            self._buffer_keystroke(key_str)

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if not self._running:
            return

        key_str = self._key_to_string(key)
        if key_str is None:
            return

        # Track modifiers
        if key_str in ("ctrl", "alt", "cmd", "shift"):
            self._current_modifiers.discard(key_str)

    def _buffer_keystroke(self, key_str: str) -> None:
        """Add a keystroke to the buffer."""
        # Check if we're in a sensitive context
        window_info = {}
        if self.get_active_window:
            window_info = self.get_active_window()

        is_sensitive = is_sensitive_context(
            window_title=window_info.get("title", ""),
            app_name=window_info.get("app", ""),
        )

        with self._buffer_lock:
            # If sensitivity changed, flush first
            if self._text_buffer and is_sensitive != self._buffer_masked:
                self._flush_buffer_locked()

            # Set buffer start time if this is the first character
            if not self._text_buffer:
                self._buffer_start_time = datetime.now().isoformat()
                self._buffer_masked = is_sensitive

            # Handle special keys that should flush
            if key_str == "\n":
                # Add the newline, then flush
                self._text_buffer.append(key_str)
                self._flush_buffer_locked()
                return
            elif key_str == "[backspace]":
                # Remove last character if buffer not empty
                if self._text_buffer:
                    self._text_buffer.pop()
                self._reset_flush_timer()
                return
            elif key_str.startswith("[") and key_str.endswith("]"):
                # Special key - flush buffer, don't add to text
                self._flush_buffer_locked()
                return

            # Mask if sensitive
            display_key = mask_if_sensitive(key_str, is_sensitive)
            self._text_buffer.append(display_key)

        # Reset the flush timer
        self._reset_flush_timer()

    def _emit_command(self, key_str: str) -> None:
        """Emit a command event."""
        event = CommandEvent(
            timestamp=datetime.now().isoformat(),
            key=key_str,
            modifiers=list(self._current_modifiers),
        )
        self.on_event(event)

    def _flush_buffer(self) -> None:
        """Flush the text buffer and emit event."""
        with self._buffer_lock:
            self._flush_buffer_locked()

    def _flush_buffer_locked(self) -> None:
        """Flush the text buffer (must hold lock)."""
        if not self._text_buffer:
            return

        text = "".join(self._text_buffer)
        timestamp = self._buffer_start_time or datetime.now().isoformat()

        event = TextEvent(
            timestamp=timestamp,
            text=text,
            masked=self._buffer_masked,
        )
        self.on_event(event)

        # Clear buffer
        self._text_buffer = []
        self._buffer_start_time = None
        self._buffer_masked = False

    def _reset_flush_timer(self) -> None:
        """Reset the flush timer."""
        self._cancel_flush_timer()
        self._flush_timer = threading.Timer(self.FLUSH_TIMEOUT, self._flush_buffer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _cancel_flush_timer(self) -> None:
        """Cancel the flush timer."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None

    def _key_to_string(self, key: keyboard.Key | keyboard.KeyCode | None) -> Optional[str]:
        """Convert a pynput key to a string representation."""
        if key is None:
            return None

        if isinstance(key, keyboard.KeyCode):
            if key.char:
                return key.char
            return None

        # Handle special keys
        key_map = {
            keyboard.Key.space: " ",
            keyboard.Key.enter: "\n",
            keyboard.Key.tab: "\t",
            keyboard.Key.backspace: "[backspace]",
            keyboard.Key.delete: "[delete]",
            keyboard.Key.esc: "[esc]",
            keyboard.Key.ctrl: "ctrl",
            keyboard.Key.ctrl_l: "ctrl",
            keyboard.Key.ctrl_r: "ctrl",
            keyboard.Key.alt: "alt",
            keyboard.Key.alt_l: "alt",
            keyboard.Key.alt_r: "alt",
            keyboard.Key.cmd: "cmd",
            keyboard.Key.cmd_l: "cmd",
            keyboard.Key.cmd_r: "cmd",
            keyboard.Key.shift: "shift",
            keyboard.Key.shift_l: "shift",
            keyboard.Key.shift_r: "shift",
            keyboard.Key.caps_lock: "[capslock]",
            keyboard.Key.up: "[up]",
            keyboard.Key.down: "[down]",
            keyboard.Key.left: "[left]",
            keyboard.Key.right: "[right]",
        }

        return key_map.get(key)

    @property
    def is_running(self) -> bool:
        return self._running
