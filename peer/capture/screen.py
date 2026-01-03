"""Screen capture functionality for macOS."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from Quartz import (
        CGDisplayBounds,
        CGMainDisplayID,
        CGWindowListCreateImage,
        kCGWindowImageDefault,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )
    from Quartz.CoreGraphics import CGRectInfinite

    QUARTZ_AVAILABLE = True
except ImportError:
    QUARTZ_AVAILABLE = False

try:
    from PIL import Image
    import Quartz.CoreGraphics as CG

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def capture_screen(
    screenshots_dir: Path,
    session_id: str,
    display_id: Optional[int] = None,
) -> Optional[Path]:
    """Capture the current screen and save to file.

    Args:
        screenshots_dir: Base directory for screenshots
        session_id: Current session ID for organization
        display_id: Optional display ID (defaults to main display)

    Returns:
        Path to saved screenshot, or None if capture failed
    """
    if not QUARTZ_AVAILABLE:
        return None

    try:
        # Get display bounds
        if display_id is None:
            display_id = CGMainDisplayID()

        # Capture the screen
        image = CGWindowListCreateImage(
            CGRectInfinite,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
            kCGWindowImageDefault,
        )

        if image is None:
            return None

        # Create directory structure: screenshots/YYYY-MM-DD/session_id[:8]/
        today = datetime.now().strftime("%Y-%m-%d")
        save_dir = screenshots_dir / today / session_id[:8]
        save_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = f"screen_{timestamp}.png"
        filepath = save_dir / filename

        # Save the image
        if PIL_AVAILABLE:
            _save_with_pil(image, filepath)
        else:
            _save_with_quartz(image, filepath)

        return filepath

    except Exception:
        return None


def _save_with_pil(cg_image, filepath: Path) -> None:
    """Save CGImage using PIL."""
    width = CG.CGImageGetWidth(cg_image)
    height = CG.CGImageGetHeight(cg_image)
    bytes_per_row = CG.CGImageGetBytesPerRow(cg_image)

    # Get image data
    data_provider = CG.CGImageGetDataProvider(cg_image)
    data = CG.CGDataProviderCopyData(data_provider)

    # Create PIL image
    image = Image.frombytes(
        "RGBA",
        (width, height),
        data,
        "raw",
        "BGRA",
        bytes_per_row,
    )

    # Convert to RGB and save
    image = image.convert("RGB")
    image.save(str(filepath), "PNG", optimize=True)


def _save_with_quartz(cg_image, filepath: Path) -> None:
    """Save CGImage using Quartz directly."""
    from Quartz import (
        CGImageDestinationCreateWithURL,
        CGImageDestinationAddImage,
        CGImageDestinationFinalize,
        kUTTypePNG,
    )
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(filepath))
    destination = CGImageDestinationCreateWithURL(url, kUTTypePNG, 1, None)

    if destination:
        CGImageDestinationAddImage(destination, cg_image, None)
        CGImageDestinationFinalize(destination)


def get_screen_resolution() -> tuple[int, int]:
    """Get the main screen resolution."""
    if not QUARTZ_AVAILABLE:
        return (0, 0)

    display_id = CGMainDisplayID()
    bounds = CGDisplayBounds(display_id)
    return (int(bounds.size.width), int(bounds.size.height))
