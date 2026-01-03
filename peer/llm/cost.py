"""LLM cost tracking for Peer."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CostEntry:
    """A single cost entry."""

    timestamp: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    operation: str  # 'summary', 'analysis', 'realtime'


@dataclass
class CostTracker:
    """Tracks LLM usage costs for a session."""

    session_id: str
    entries: list[CostEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def total_cost(self) -> float:
        """Get total cost for all entries."""
        with self._lock:
            return sum(e.cost for e in self.entries)

    @property
    def total_input_tokens(self) -> int:
        """Get total input tokens."""
        with self._lock:
            return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        """Get total output tokens."""
        with self._lock:
            return sum(e.output_tokens for e in self.entries)

    def add_entry(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        operation: str,
    ) -> None:
        """Add a cost entry."""
        entry = CostEntry(
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            operation=operation,
        )

        with self._lock:
            self.entries.append(entry)

    def get_summary(self) -> dict:
        """Get a summary of costs by provider and operation."""
        with self._lock:
            by_provider: dict[str, float] = {}
            by_operation: dict[str, float] = {}

            for entry in self.entries:
                by_provider[entry.provider] = (
                    by_provider.get(entry.provider, 0) + entry.cost
                )
                by_operation[entry.operation] = (
                    by_operation.get(entry.operation, 0) + entry.cost
                )

            return {
                "total_cost": self.total_cost,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "by_provider": by_provider,
                "by_operation": by_operation,
                "entry_count": len(self.entries),
            }


# Global cost tracker for current session
_current_tracker: Optional[CostTracker] = None


def get_tracker(session_id: Optional[str] = None) -> CostTracker:
    """Get or create the cost tracker for a session."""
    global _current_tracker

    if _current_tracker is None or (
        session_id and _current_tracker.session_id != session_id
    ):
        _current_tracker = CostTracker(session_id=session_id or "unknown")

    return _current_tracker


def reset_tracker() -> None:
    """Reset the global cost tracker."""
    global _current_tracker
    _current_tracker = None
