"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a text completion."""
        pass

    @abstractmethod
    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Analyze an image and generate a response."""
        pass

    def summarize_session(
        self,
        events: list[Any],
        screenshots: list[Any],
    ) -> str:
        """Generate a summary of a session."""
        from peer.privacy import redact_for_llm

        # Prepare event data
        event_dicts = [e.to_dict() if hasattr(e, "to_dict") else e for e in events]
        redacted_events = redact_for_llm(event_dicts)

        # Build context
        event_summary = self._summarize_events(redacted_events)

        prompt = f"""Summarize the following user activity session. Focus on:
1. What applications/websites were used
2. Key tasks or activities performed
3. Any patterns in behavior

Activity Log:
{event_summary}

Screenshots captured: {len(screenshots)}

Provide a concise summary (2-4 paragraphs) of what the user was doing during this session."""

        response = self.complete(
            prompt=prompt,
            system="You are an activity analyst helping users understand their computer usage patterns. Be concise and objective.",
            max_tokens=500,
        )

        return response.content

    def _summarize_events(self, events: list[dict[str, Any]]) -> str:
        """Create a text summary of events for the LLM."""
        if not events:
            return "No events recorded."

        # Group events by type
        keystrokes = [e for e in events if e.get("event_type") == "keystroke"]
        clicks = [e for e in events if e.get("event_type") == "click"]
        windows = [e for e in events if e.get("event_type") == "window_change"]

        lines = []
        lines.append(f"Total events: {len(events)}")
        lines.append(f"- Keystrokes: {len(keystrokes)}")
        lines.append(f"- Mouse clicks: {len(clicks)}")
        lines.append(f"- Window changes: {len(windows)}")

        # List unique applications used
        apps = set()
        for w in windows:
            data = w.get("data", {})
            app = data.get("app_name", "")
            if app:
                apps.add(app)

        if apps:
            lines.append(f"\nApplications used: {', '.join(sorted(apps))}")

        # Sample of window changes (for context)
        if windows:
            lines.append("\nWindow activity (sample):")
            for w in windows[:20]:
                data = w.get("data", {})
                app = data.get("app_name", "Unknown")
                title = data.get("window_title", "")[:50]
                lines.append(f"  - {app}: {title}")

        return "\n".join(lines)
