"""
Position Tracker - Manages position context lifecycle.

This module provides utilities for:
1. Tracking position contexts across trading cycles
2. Generating summaries for display
3. Handling position lifecycle (entry, update, exit)

The PositionTracker is mode-agnostic and works identically
in both backtest and live trading modes.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from src.data.position_context import (
    PositionContext,
    EventThesis,
    EventState,
    EventType,
    ThesisType,
    ProbabilitySnapshot,
)


class PositionTracker:
    """
    Tracks and manages position contexts throughout their lifecycle.

    This class provides:
    - Position context storage and retrieval
    - Summary generation for display
    - Lifecycle management (entry, update, exit)
    
    The tracker maintains an internal dictionary of position contexts
    keyed by ticker symbol. It handles both the new PositionContext
    format (with multiple events) and legacy single-event formats.
    
    Example:
        >>> tracker = PositionTracker()
        >>> tracker.add_position("AAPL", context_data, entry_price=150.0)
        >>> tracker.update_position("AAPL", probability=0.75)
        >>> summary = tracker.get_active_events_summary()
    """

    def __init__(self):
        """Initialize an empty position tracker."""
        self._contexts: Dict[str, PositionContext] = {}

    def add_position(
        self,
        ticker: str,
        context_data: Dict[str, Any],
        entry_price: Optional[float] = None,
    ) -> None:
        """
        Add a new position with context.
        
        Handles both the new multi-event PositionContext format and
        legacy single-event formats for backward compatibility.
        
        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            context_data: Position context data (dict or PositionContext)
            entry_price: Optional entry price for the position
        """
        if isinstance(context_data, PositionContext):
            # Already a PositionContext object
            context = context_data
            if entry_price is not None:
                context.entry_price = entry_price
        elif isinstance(context_data, dict):
            # Handle dict format
            if "events" in context_data:
                # New multi-event format
                context = PositionContext(
                    ticker=ticker,
                    events=[
                        EventThesis(**e) if isinstance(e, dict) else e
                        for e in context_data.get("events", [])
                    ],
                    entry_price=entry_price or context_data.get("entry_price"),
                    last_updated=context_data.get("last_updated", datetime.now().isoformat()),
                )
            elif "event_id" in context_data:
                # Legacy single-event format - convert to new format
                event = EventThesis(
                    event_id=context_data.get("event_id", ""),
                    event_title=context_data.get("event_title", "Unknown Event"),
                    event_type=EventType(context_data.get("event_type", "binary")),
                    event_state=EventState(context_data.get("event_state", "active")),
                    thesis=context_data.get("thesis", ""),
                    thesis_type=ThesisType(context_data.get("thesis_type", "short_term")),
                    impact_direction=context_data.get("impact_direction", "bullish"),
                    confidence=context_data.get("confidence", 50),
                    probability=ProbabilitySnapshot(
                        current=context_data.get("probability", {}).get("current", 0.5),
                        change_24h=context_data.get("probability", {}).get("change_24h"),
                        change_7d=context_data.get("probability", {}).get("change_7d"),
                        since_entry=context_data.get("probability", {}).get("since_entry"),
                        at_entry=context_data.get("probability", {}).get("at_entry"),
                    ),
                    entry_date=context_data.get("entry_date", datetime.now().strftime("%Y-%m-%d")),
                    resolved_date=context_data.get("resolved_date"),
                )
                context = PositionContext(
                    ticker=ticker,
                    events=[event],
                    entry_price=entry_price or context_data.get("entry_price"),
                )
            else:
                # Empty or unknown format - create empty context
                context = PositionContext(
                    ticker=ticker,
                    events=[],
                    entry_price=entry_price,
                )
        else:
            # Unknown type - create empty context
            context = PositionContext(
                ticker=ticker,
                events=[],
                entry_price=entry_price,
            )

        self._contexts[ticker] = context

    def update_position(
        self,
        ticker: str,
        probability: Optional[float] = None,
        event_state: Optional[EventState] = None,
        event_id: Optional[str] = None,
    ) -> bool:
        """
        Update an existing position's context.
        
        Updates probability and/or event state for a position.
        If event_id is provided, only that specific event is updated.
        Otherwise, all events for the ticker are updated.
        
        Args:
            ticker: Stock ticker symbol
            probability: New probability value (0-1)
            event_state: New event state
            event_id: Optional specific event ID to update
            
        Returns:
            True if position was found and updated, False otherwise
        """
        if ticker not in self._contexts:
            return False

        context = self._contexts[ticker]

        for event in context.events:
            # Skip if event_id specified and doesn't match
            if event_id is not None and event.event_id != event_id:
                continue
                
            if probability is not None:
                old_prob = event.probability.current
                event.probability.current = probability
                event.probability.change_24h = probability - old_prob
                if event.probability.at_entry is not None:
                    event.probability.since_entry = probability - event.probability.at_entry

            if event_state is not None:
                event.event_state = event_state
                if event_state != EventState.ACTIVE:
                    event.resolved_date = datetime.now().strftime("%Y-%m-%d")

        context.last_updated = datetime.now().isoformat()
        return True

    def mark_resolved(
        self,
        ticker: str,
        event_id: str,
        state: EventState,
    ) -> bool:
        """
        Mark a specific event as resolved.
        
        Args:
            ticker: Stock ticker symbol
            event_id: The Polymarket event ID to mark as resolved
            state: The resolution state (RESOLVED_YES, RESOLVED_NO, or EXPIRED)
            
        Returns:
            True if event was found and updated, False otherwise
        """
        if ticker not in self._contexts:
            return False
            
        return self._contexts[ticker].mark_event_resolved(event_id, state)

    def remove_position(self, ticker: str) -> Optional[PositionContext]:
        """
        Remove a position and return its context.
        
        Args:
            ticker: Stock ticker symbol to remove
            
        Returns:
            The removed PositionContext, or None if not found
        """
        return self._contexts.pop(ticker, None)

    def get_context(self, ticker: str) -> Optional[PositionContext]:
        """
        Get context for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            PositionContext for the ticker, or None if not found
        """
        return self._contexts.get(ticker)

    def get_all_contexts(self) -> Dict[str, PositionContext]:
        """
        Get all position contexts.
        
        Returns:
            Copy of the internal contexts dictionary
        """
        return self._contexts.copy()
    
    def get_contexts_as_dict(self) -> Dict[str, Dict]:
        """
        Get all position contexts as plain dictionaries.
        
        This is useful for passing to functions that expect
        the legacy dict format.
        
        Returns:
            Dictionary of ticker -> context dict
        """
        result = {}
        for ticker, context in self._contexts.items():
            result[ticker] = context.model_dump()
        return result

    def get_active_tickers(self) -> List[str]:
        """
        Get tickers with active (unresolved) events.
        
        Returns:
            List of ticker symbols with at least one active event
        """
        return [
            ticker for ticker, context in self._contexts.items()
            if context.has_active_events()
        ]

    def get_all_tickers(self) -> List[str]:
        """
        Get all tracked tickers.
        
        Returns:
            List of all ticker symbols being tracked
        """
        return list(self._contexts.keys())

    def get_active_events_summary(self) -> str:
        """
        Generate summary of active events for display.
        
        Returns:
            Formatted string showing all active Polymarket events
        """
        lines = ["=== ACTIVE POLYMARKET EVENTS ==="]

        active_count = 0
        for ticker, context in self._contexts.items():
            active_events = context.get_active_events()
            if active_events:
                for event in active_events:
                    active_count += 1
                    prob_str = f"{event.probability.current:.1%}" if event.probability else "?"
                    direction = "+" if event.impact_direction == "bullish" else "-"
                    title_preview = event.event_title[:40] + "..." if len(event.event_title) > 40 else event.event_title
                    lines.append(
                        f"  {ticker} [{direction}] {title_preview} "
                        f"(P={prob_str}, C={event.confidence}%)"
                    )

        if active_count == 0:
            lines.append("  No active Polymarket events")

        return "\n".join(lines)

    def get_resolved_events_summary(self) -> str:
        """
        Generate summary of resolved events for display.
        
        Returns:
            Formatted string showing all resolved Polymarket events
        """
        lines = ["=== RESOLVED EVENTS (Historical Context) ==="]

        resolved_count = 0
        for ticker, context in self._contexts.items():
            resolved_events = context.get_resolved_events()
            if resolved_events:
                for event in resolved_events:
                    resolved_count += 1
                    status = event.event_state.replace("resolved_", "").upper() if isinstance(event.event_state, str) else event.event_state.value.replace("resolved_", "").upper()
                    title_preview = event.event_title[:40] + "..." if len(event.event_title) > 40 else event.event_title
                    lines.append(
                        f"  {ticker}: {title_preview} → {status}"
                    )

        if resolved_count == 0:
            lines.append("  No resolved events")

        return "\n".join(lines)

    def get_context_summary(self, ticker: Optional[str] = None) -> str:
        """
        Get summary of position context(s) for display.
        
        Args:
            ticker: Optional specific ticker to summarize.
                   If None, summarizes all positions.
                   
        Returns:
            Formatted summary string
        """
        if ticker is not None:
            context = self._contexts.get(ticker)
            if context:
                return context.get_context_summary()
            return f"No context found for {ticker}"
        
        # Summarize all positions
        lines = ["=== POSITION CONTEXT SUMMARY ==="]
        lines.append(f"Total positions tracked: {len(self._contexts)}")
        lines.append(f"Positions with active events: {len(self.get_active_tickers())}")
        lines.append("")
        lines.append(self.get_active_events_summary())
        lines.append("")
        lines.append(self.get_resolved_events_summary())
        
        return "\n".join(lines)

    def get_decision_context_for_ticker(self, ticker: str) -> str:
        """
        Get formatted context string for agent decision display.
        
        This provides a compact view of the Polymarket context
        suitable for including in agent decision output.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Formatted context string, or empty string if no context
        """
        context = self._contexts.get(ticker)
        if not context:
            return ""

        lines = []
        for event in context.events:
            status = "ACTIVE" if event.is_active() else event.event_state
            if isinstance(status, EventState):
                status = status.value
            prob_str = f"{event.probability.current:.1%}" if event.probability else "?"

            lines.append(f"[{status.upper()}] {event.event_title}")
            thesis_preview = event.thesis[:60] + "..." if len(event.thesis) > 60 else event.thesis
            lines.append(f"  Thesis: {thesis_preview}")
            lines.append(f"  Direction: {event.impact_direction} | Prob: {prob_str}")

            # Add exit guidance if resolved
            guidance = event.get_exit_guidance()
            if guidance:
                guidance_preview = guidance[:60] + "..." if len(guidance) > 60 else guidance
                lines.append(f"  Guidance: {guidance_preview}")

        return "\n".join(lines)

    def load_from_dict(self, contexts: Dict[str, Dict]) -> None:
        """
        Load position contexts from a dictionary.
        
        This is useful for restoring state from persistence
        or initializing from existing context data.
        
        Args:
            contexts: Dictionary of ticker -> context dict
        """
        self._contexts.clear()
        for ticker, context_data in contexts.items():
            self.add_position(ticker, context_data)

    def clear(self) -> None:
        """Clear all tracked positions."""
        self._contexts.clear()

    def __len__(self) -> int:
        """Return the number of tracked positions."""
        return len(self._contexts)

    def __contains__(self, ticker: str) -> bool:
        """Check if a ticker is being tracked."""
        return ticker in self._contexts

    def __iter__(self):
        """Iterate over tracked tickers."""
        return iter(self._contexts)
