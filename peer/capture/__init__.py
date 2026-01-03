"""Screen capture for Peer."""

from peer.capture.screen import capture_screen
from peer.capture.smart import CaptureReason, SmartScreenshotManager

__all__ = ["capture_screen", "SmartScreenshotManager", "CaptureReason"]
