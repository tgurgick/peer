"""System tray integration for Peer."""

import sys
import threading
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from peer.config import Config
    from peer.main import EventCoordinator
    from peer.storage import Session


def create_icon_image(color: str = "green") -> Image.Image:
    """Create a simple tray icon."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw a circle
    colors = {
        "green": (76, 175, 80, 255),  # Active/running
        "yellow": (255, 193, 7, 255),  # Paused
        "red": (244, 67, 54, 255),  # Stopped
        "blue": (33, 150, 243, 255),  # Recording with AI
    }

    fill_color = colors.get(color, colors["green"])
    draw.ellipse([8, 8, size - 8, size - 8], fill=fill_color)

    # Draw "P" for Peer
    draw.text((20, 16), "P", fill=(255, 255, 255, 255))

    return image


def run_tray(
    session: "Session",
    config: "Config",
    coordinator: "EventCoordinator",
) -> None:
    """Run the system tray application."""
    try:
        import pystray
    except ImportError:
        print("pystray not available, running without system tray")
        # Fall back to simple wait
        try:
            while True:
                threading.Event().wait(1)
        except KeyboardInterrupt:
            return

    from pystray import MenuItem as Item

    icon = None
    running = True

    def get_status_text() -> str:
        stats = coordinator.get_stats()
        return f"Events: {sum(stats.values())} | Cost: ${session.total_cost:.4f}"

    def on_quit(icon, item):
        nonlocal running
        running = False
        icon.stop()

    def on_status(icon, item):
        stats = coordinator.get_stats()
        print(f"\nSession: {session.id[:8]}...")
        print(f"Mode: {session.mode}")
        print(f"Keystrokes: {stats['keystroke']}")
        print(f"Clicks: {stats['click']}")
        print(f"Window Changes: {stats['window_change']}")
        print(f"Screenshots: {stats['screenshot']}")
        print(f"Cost: ${session.total_cost:.4f}")

    def on_screenshot(icon, item):
        from datetime import datetime

        from peer.capture import capture_screen
        from peer.storage import Database, Screenshot

        db = Database(config.db_path)
        filepath = capture_screen(config.screenshots_dir, session.id)

        if filepath:
            screenshot = Screenshot(
                timestamp=datetime.now().isoformat(),
                filepath=str(filepath),
                session_id=session.id,
            )
            db.add_screenshot(screenshot)
            print(f"Screenshot saved: {filepath}")

    # Create menu
    menu = pystray.Menu(
        Item("Peer - Running", lambda: None, enabled=False),
        Item(lambda text: get_status_text(), lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("Take Screenshot", on_screenshot),
        Item("Show Status", on_status),
        pystray.Menu.SEPARATOR,
        Item("Quit", on_quit),
    )

    # Create and run icon
    icon = pystray.Icon(
        "peer",
        create_icon_image("green"),
        "Peer - Activity Logger",
        menu,
    )

    icon.run()
