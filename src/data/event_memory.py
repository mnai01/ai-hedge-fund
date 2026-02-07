"""
Event memory system for tracking analyzed Polymarket events.

This module provides a persistent cache of events that have been analyzed,
including their relevance scores and discovered tickers. Prevents re-analyzing
the same events across multiple discovery cycles, saving LLM costs.

Expected to reduce costs by 30-40% by avoiding duplicate analysis of recurring events.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Literal
from pydantic import BaseModel, Field


class EventMemoryEntry(BaseModel):
    """Single entry in event memory cache."""

    event_id: str = Field(description="Polymarket event ID")
    event_title: str = Field(description="Event title for reference")
    category: Optional[str] = Field(default=None, description="Event category")

    # Relevance check results
    relevance: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="Cached relevance level"
    )
    relevance_confidence: Optional[float] = Field(
        default=None,
        description="Confidence in relevance assessment"
    )
    relevance_reasoning: Optional[str] = Field(
        default=None,
        description="Reasoning for relevance determination"
    )

    # Discovered tickers (if relevance check passed)
    discovered_tickers: Optional[list[str]] = Field(
        default=None,
        description="List of tickers discovered for this event"
    )
    discovery_reasoning: Optional[str] = Field(
        default=None,
        description="AI reasoning for ticker discovery"
    )

    # Metadata
    first_seen: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When this event was first analyzed"
    )
    last_updated: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When this entry was last updated"
    )
    analysis_count: int = Field(
        default=1,
        description="Number of times this event has been seen"
    )

    def is_expired(self, ttl_days: int = 30) -> bool:
        """
        Check if this memory entry has expired.

        Args:
            ttl_days: Time-to-live in days

        Returns:
            True if entry is older than ttl_days
        """
        last_updated_dt = datetime.fromisoformat(self.last_updated)
        age = datetime.now() - last_updated_dt
        return age > timedelta(days=ttl_days)

    def should_recheck_relevance(self, recheck_days: int = 7) -> bool:
        """
        Determine if relevance should be rechecked.

        Events with low/medium relevance should be rechecked periodically
        in case circumstances change. High relevance events are more stable.

        Args:
            recheck_days: Days before rechecking relevance

        Returns:
            True if relevance should be rechecked
        """
        if self.relevance is None:
            return True

        if self.relevance == "high":
            # High relevance is stable, don't recheck
            return False

        last_updated_dt = datetime.fromisoformat(self.last_updated)
        age = datetime.now() - last_updated_dt
        return age > timedelta(days=recheck_days)


class EventMemory:
    """
    Persistent memory system for tracking analyzed Polymarket events.

    Stores:
    - Relevance check results (to avoid re-running AI relevance checks)
    - Discovered tickers (to avoid re-running stock discovery)
    - Analysis metadata (first seen, last updated, count)

    Usage:
        memory = EventMemory()

        # Check if event was already analyzed
        if memory.has_event("event-123"):
            entry = memory.get_event("event-123")
            if entry.relevance == "low":
                # Skip this event - we already know it's not relevant
                pass

        # Store relevance result
        memory.store_relevance(
            event_id="event-123",
            event_title="Apple announces new iPhone",
            category="Technology",
            relevance="high",
            confidence=0.95,
            reasoning="Direct impact on AAPL stock"
        )

        # Store discovered tickers
        memory.store_discovery(
            event_id="event-123",
            tickers=["AAPL", "QCOM", "TSM"],
            reasoning="Apple and its key suppliers"
        )

        # Persist to disk
        memory.save()
    """

    def __init__(self, cache_file: Optional[Path] = None, ttl_days: int = 30):
        """
        Initialize event memory.

        Args:
            cache_file: Path to JSON cache file. Defaults to data/event_memory.json
            ttl_days: Time-to-live for memory entries in days
        """
        if cache_file is None:
            cache_file = Path(__file__).parent.parent.parent / "data" / "event_memory.json"

        self.cache_file = Path(cache_file)
        self.ttl_days = ttl_days
        self._memory: dict[str, EventMemoryEntry] = {}

        # Ensure directory exists
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing memory
        self._load()

    def _load(self):
        """Load memory from disk."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)

            for event_id, entry_data in data.items():
                try:
                    entry = EventMemoryEntry(**entry_data)
                    # Only load non-expired entries
                    if not entry.is_expired(self.ttl_days):
                        self._memory[event_id] = entry
                except Exception as e:
                    print(f"Warning: Could not load memory entry for {event_id}: {e}")

        except Exception as e:
            print(f"Warning: Could not load event memory from {self.cache_file}: {e}")

    def save(self):
        """Persist memory to disk."""
        try:
            # Clean expired entries before saving
            self._clean_expired()

            # Convert to dict
            data = {
                event_id: entry.model_dump()
                for event_id, entry in self._memory.items()
            }

            with open(self.cache_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"Warning: Could not save event memory to {self.cache_file}: {e}")

    def _clean_expired(self):
        """Remove expired entries from memory."""
        expired_ids = [
            event_id
            for event_id, entry in self._memory.items()
            if entry.is_expired(self.ttl_days)
        ]

        for event_id in expired_ids:
            del self._memory[event_id]

    def has_event(self, event_id: str) -> bool:
        """
        Check if an event is in memory.

        Args:
            event_id: Polymarket event ID

        Returns:
            True if event has been analyzed before
        """
        return event_id in self._memory

    def get_event(self, event_id: str) -> Optional[EventMemoryEntry]:
        """
        Get memory entry for an event.

        Args:
            event_id: Polymarket event ID

        Returns:
            EventMemoryEntry if found, None otherwise
        """
        return self._memory.get(event_id)

    def store_relevance(
        self,
        event_id: str,
        event_title: str,
        category: Optional[str],
        relevance: Literal["high", "medium", "low"],
        confidence: float,
        reasoning: str
    ):
        """
        Store relevance check result for an event.

        Args:
            event_id: Polymarket event ID
            event_title: Event title
            category: Event category
            relevance: Relevance level (high/medium/low)
            confidence: Confidence score (0-1)
            reasoning: Reasoning for relevance determination
        """
        if event_id in self._memory:
            # Update existing entry
            entry = self._memory[event_id]
            entry.relevance = relevance
            entry.relevance_confidence = confidence
            entry.relevance_reasoning = reasoning
            entry.last_updated = datetime.now().isoformat()
            entry.analysis_count += 1
        else:
            # Create new entry
            entry = EventMemoryEntry(
                event_id=event_id,
                event_title=event_title,
                category=category,
                relevance=relevance,
                relevance_confidence=confidence,
                relevance_reasoning=reasoning
            )
            self._memory[event_id] = entry

    def store_discovery(
        self,
        event_id: str,
        tickers: list[str],
        reasoning: Optional[str] = None
    ):
        """
        Store discovered tickers for an event.

        Args:
            event_id: Polymarket event ID
            tickers: List of discovered ticker symbols
            reasoning: Optional reasoning for ticker discovery
        """
        if event_id not in self._memory:
            raise ValueError(f"Event {event_id} not found in memory. Store relevance first.")

        entry = self._memory[event_id]
        entry.discovered_tickers = tickers
        entry.discovery_reasoning = reasoning
        entry.last_updated = datetime.now().isoformat()

    def get_cached_relevance(
        self,
        event_id: str,
        recheck_days: int = 7
    ) -> Optional[tuple[Literal["high", "medium", "low"], float, str]]:
        """
        Get cached relevance result if available and not expired.

        Args:
            event_id: Polymarket event ID
            recheck_days: Days before rechecking relevance

        Returns:
            Tuple of (relevance, confidence, reasoning) if cached and valid, None otherwise
        """
        entry = self.get_event(event_id)

        if entry is None or entry.relevance is None:
            return None

        if entry.should_recheck_relevance(recheck_days):
            return None

        return (entry.relevance, entry.relevance_confidence or 0.0, entry.relevance_reasoning or "")

    def get_cached_tickers(self, event_id: str) -> Optional[list[str]]:
        """
        Get cached discovered tickers if available.

        Args:
            event_id: Polymarket event ID

        Returns:
            List of ticker symbols if cached, None otherwise
        """
        entry = self.get_event(event_id)

        if entry is None or entry.discovered_tickers is None:
            return None

        return entry.discovered_tickers

    def get_stats(self) -> dict:
        """
        Get statistics about event memory.

        Returns:
            Dictionary with memory statistics
        """
        total_events = len(self._memory)

        relevance_counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        events_with_tickers = 0

        for entry in self._memory.values():
            if entry.relevance:
                relevance_counts[entry.relevance] += 1
            else:
                relevance_counts["unknown"] += 1

            if entry.discovered_tickers:
                events_with_tickers += 1

        return {
            "total_events": total_events,
            "relevance_distribution": relevance_counts,
            "events_with_tickers": events_with_tickers,
            "cache_file": str(self.cache_file),
            "ttl_days": self.ttl_days
        }

    def clear(self):
        """Clear all memory entries."""
        self._memory.clear()

    def clear_event(self, event_id: str):
        """
        Remove a specific event from memory.

        Args:
            event_id: Polymarket event ID to remove
        """
        if event_id in self._memory:
            del self._memory[event_id]
