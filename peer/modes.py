"""Operating modes for Peer."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Mode(IntEnum):
    """Peer operating modes."""

    LOGS_ONLY = 1  # Silent background logging
    LOGS_SCREENSHOTS = 2  # Logging + periodic screenshots
    LOGS_SCREENSHOTS_SUMMARIES = 3  # + periodic AI summaries
    LOGS_SCREENSHOTS_REALTIME = 4  # + real-time AI feedback


@dataclass
class ModeConfig:
    """Configuration for a specific mode."""

    mode: Mode
    capture_screenshots: bool
    ai_summaries: bool
    realtime_ai: bool
    summary_interval: Optional[int] = None  # seconds

    @classmethod
    def from_mode(cls, mode: int, summary_interval: int = 300) -> "ModeConfig":
        """Create mode configuration from mode number."""
        mode_enum = Mode(mode)

        return cls(
            mode=mode_enum,
            capture_screenshots=mode >= Mode.LOGS_SCREENSHOTS,
            ai_summaries=mode >= Mode.LOGS_SCREENSHOTS_SUMMARIES,
            realtime_ai=mode >= Mode.LOGS_SCREENSHOTS_REALTIME,
            summary_interval=summary_interval if mode >= Mode.LOGS_SCREENSHOTS_SUMMARIES else None,
        )


MODE_DESCRIPTIONS = {
    Mode.LOGS_ONLY: "Logs only (silent background logging)",
    Mode.LOGS_SCREENSHOTS: "Logs + screenshots",
    Mode.LOGS_SCREENSHOTS_SUMMARIES: "Logs + screenshots + periodic AI summaries",
    Mode.LOGS_SCREENSHOTS_REALTIME: "Logs + screenshots + real-time AI feedback",
}


def get_mode_description(mode: int) -> str:
    """Get human-readable description for a mode."""
    try:
        return MODE_DESCRIPTIONS[Mode(mode)]
    except ValueError:
        return f"Unknown mode {mode}"


def validate_mode(mode: int) -> bool:
    """Check if a mode number is valid."""
    return mode in (1, 2, 3, 4)
