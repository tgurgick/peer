"""Mouse event logger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pynput import mouse


@dataclass
class MouseEvent:
    """A mouse click event."""

    timestamp: str
    x: int
    y: int
    button: str
    event_type: str  # 'click' or 'scroll'
    pressed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "button": self.button,
            "event_type": self.event_type,
            "pressed": self.pressed,
        }


class MouseLogger:
    """Captures mouse click events."""

    def __init__(self, on_event: Callable[[MouseEvent], None]):
        self.on_event = on_event
        self._listener: Optional[mouse.Listener] = None
        self._running = False

    def start(self) -> None:
        """Start listening for mouse events."""
        if self._running:
            return

        self._running = True
        # Only track clicks, not scrolls (scrolls are too noisy and rarely meaningful)
        self._listener = mouse.Listener(
            on_click=self._on_click,
        )
        self._listener.start()

    def stop(self) -> None:
        """Stop listening for mouse events."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        if not self._running:
            return

        # Only log press events, not releases (to reduce noise)
        if not pressed:
            return

        event = MouseEvent(
            timestamp=datetime.now().isoformat(),
            x=int(x),
            y=int(y),
            button=button.name,
            event_type="click",
            pressed=pressed,
        )

        self.on_event(event)

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._running:
            return

        # Determine scroll direction
        direction = "up" if dy > 0 else "down" if dy < 0 else "horizontal"

        event = MouseEvent(
            timestamp=datetime.now().isoformat(),
            x=int(x),
            y=int(y),
            button=direction,
            event_type="scroll",
            pressed=True,
        )

        self.on_event(event)

    @property
    def is_running(self) -> bool:
        return self._running
