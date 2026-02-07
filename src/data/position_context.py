"""Position context for Polymarket-driven positions.

This module defines the context that gets shared with ALL agents
when analyzing a position that was discovered via Polymarket.

Key principle: Polymarket is HOW we found the stock, not WHY we keep it.
AI always manages positions until sold - event expiry is just historical context.
Multiple event theses per ticker are allowed - agents see all and decide.

Also includes EventHistory for tracking analyzed events to prevent duplicate analysis.
"""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Type of Polymarket event - detected programmatically from API structure."""
    BINARY = "binary"           # Single market, Yes/No outcomes
    MULTI_OPTION = "multi_option"  # Multiple mutually exclusive outcomes
    SEQUENTIAL = "sequential"   # Time-based series (e.g., "BTC ATH by [month]")
    RANGE = "range"            # Numeric outcome ranges


class ThesisType(str, Enum):
    """Classification of investment thesis duration."""
    SHORT_TERM = "short_term"  # Event-dependent, thesis ends when event resolves
    LONG_TERM = "long_term"    # Structural change, thesis persists after event


class EventState(str, Enum):
    """Current state of the Polymarket event."""
    ACTIVE = "active"          # Event ongoing, probability updating
    RESOLVED_YES = "resolved_yes"  # Event resolved to YES
    RESOLVED_NO = "resolved_no"    # Event resolved to NO
    EXPIRED = "expired"        # Event ended without clear resolution


class ProbabilitySnapshot(BaseModel):
    """Point-in-time probability data for context."""
    current: float = Field(..., description="Current probability (0-1)")
    change_24h: Optional[float] = Field(None, description="Change in last 24 hours")
    change_7d: Optional[float] = Field(None, description="Change in last 7 days")
    since_entry: Optional[float] = Field(None, description="Change since position entry")
    at_entry: Optional[float] = Field(None, description="Probability when position was opened")


class SequentialEventData(BaseModel):
    """Data for sequential/time-based events."""
    current_market_index: int = Field(..., description="Index of current active market")
    total_markets: int = Field(..., description="Total number of markets in sequence")
    cumulative_probability: float = Field(..., description="P(happens by last date)")
    market_deadlines: List[str] = Field(default_factory=list, description="Deadline for each market")


class EventThesis(BaseModel):
    """Individual event thesis for a ticker.
    
    Represents a single Polymarket event and its investment thesis
    for a particular stock. A ticker can have multiple EventThesis
    objects if multiple events affect it.
    """
    # Event identification
    event_id: str = Field(..., description="Polymarket event ID")
    event_title: str = Field(..., description="Human-readable event title")
    event_type: EventType = Field(..., description="Type of event (binary, multi_option, etc.)")
    event_state: EventState = Field(default=EventState.ACTIVE, description="Current event state")
    
    # The thesis - WHY this stock was selected for this event
    thesis: str = Field(..., description="Investment thesis explaining stock selection")
    thesis_type: ThesisType = Field(..., description="Short-term (event-dependent) or long-term (structural)")
    
    # Impact assessment
    impact_direction: str = Field(..., description="'bullish' or 'bearish' if event happens")
    confidence: int = Field(..., ge=0, le=100, description="Confidence in stock mapping (0-100)")

    # Multi-outcome landscape context
    target_outcome: Optional[str] = Field(
        None,
        description="For multi-outcome events: which outcome the thesis is based on (e.g., '4 cuts', 'Trump')"
    )
    landscape_at_entry: Optional[str] = Field(
        None,
        description="Formatted landscape snapshot when position was opened"
    )

    # Probability data (snapshot, not history)
    probability: ProbabilitySnapshot = Field(..., description="Current probability snapshot")
    
    # Timing
    entry_date: str = Field(..., description="Date this thesis was added (YYYY-MM-DD)")
    resolved_date: Optional[str] = Field(None, description="Date event resolved (YYYY-MM-DD)")
    
    # Sequential event data (only populated for sequential events)
    sequential_data: Optional[SequentialEventData] = Field(
        None, 
        description="Additional data for sequential events"
    )
    
    class Config:
        use_enum_values = True
    
    def is_active(self) -> bool:
        """Check if this event thesis is still active (not resolved/expired)."""
        return self.event_state == EventState.ACTIVE
    
    def get_exit_guidance(self) -> Optional[str]:
        """Get thesis-type-aware exit guidance based on event resolution.
        
        Returns actionable guidance for agents based on:
        - Event state (resolved yes/no, expired)
        - Thesis type (short-term catalyst vs long-term structural)
        - Impact direction (bullish/bearish)
        
        Returns:
            Exit guidance string if event is resolved, None if still active
        """
        if self.event_state == EventState.ACTIVE:
            return None
        
        # Determine if the resolution was favorable to the thesis
        # For bullish thesis: RESOLVED_YES is favorable (event happened as expected)
        # For bearish thesis: RESOLVED_NO is favorable (event didn't happen, bearish thesis validated)
        is_bullish_thesis = self.impact_direction == "bullish"
        
        if self.event_state == EventState.RESOLVED_YES:
            thesis_validated = is_bullish_thesis  # YES outcome validates bullish thesis
        elif self.event_state == EventState.RESOLVED_NO:
            thesis_validated = not is_bullish_thesis  # NO outcome validates bearish thesis
        else:  # EXPIRED
            thesis_validated = None  # Unclear outcome
        
        # Generate guidance based on thesis type and validation
        if self.thesis_type == ThesisType.SHORT_TERM:
            if thesis_validated is True:
                return (
                    f"⚠️ SHORT-TERM CATALYST REALIZED - Event '{self.event_title}' resolved in favor of thesis. "
                    f"Consider taking profits as the catalyst has played out."
                )
            elif thesis_validated is False:
                return (
                    f"🚨 SHORT-TERM CATALYST FAILED - Event '{self.event_title}' resolved against thesis. "
                    f"Consider exiting position as the original catalyst is invalidated."
                )
            else:  # EXPIRED
                return (
                    f"⚠️ EVENT EXPIRED - Event '{self.event_title}' ended without clear resolution. "
                    f"Reassess position as the short-term catalyst is no longer valid."
                )
        
        else:  # LONG_TERM thesis
            if thesis_validated is True:
                return (
                    f"✓ STRUCTURAL THESIS VALIDATED - Event '{self.event_title}' resolved in favor of thesis. "
                    f"Long-term structural benefits expected. Consider holding for continued upside."
                )
            elif thesis_validated is False:
                return (
                    f"⚠️ STRUCTURAL THESIS CHALLENGED - Event '{self.event_title}' resolved against thesis. "
                    f"Reassess position as the structural change may not materialize as expected."
                )
            else:  # EXPIRED
                return (
                    f"⚠️ EVENT EXPIRED - Event '{self.event_title}' ended without clear resolution. "
                    f"Long-term thesis may still be valid. Reassess based on current fundamentals."
                )
    
    def get_thesis_with_guidance(self) -> str:
        """Get the thesis string with exit guidance appended if applicable.
        
        This is the primary method agents should use to get the full thesis
        context including any actionable exit guidance.
        
        Returns:
            Thesis string, optionally with exit guidance appended
        """
        guidance = self.get_exit_guidance()
        if guidance:
            return f"{self.thesis}\n\n{guidance}"
        return self.thesis


class PositionContext(BaseModel):
    """Context for a ticker - can have multiple event theses.
    
    This is the container that holds all Polymarket-related context
    for a single ticker. A ticker can be affected by multiple events,
    each with its own thesis.
    
    Key principles:
    - Polymarket is HOW we found the stock, not WHY we keep it
    - AI manages positions until sold (no automatic exits on event expiry)
    - Event expiry = historical context, AI keeps managing
    - Multiple event theses allowed - agents see all and decide
    """
    
    # Ticker identification
    ticker: str = Field(..., description="Stock ticker this context applies to")
    
    # Multiple event theses
    events: List[EventThesis] = Field(
        default_factory=list,
        description="List of event theses affecting this ticker"
    )
    
    # Position tracking (shared across all events)
    entry_price: Optional[float] = Field(None, description="Stock price at initial entry")
    
    # Metadata
    last_updated: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When this context was last updated"
    )
    
    class Config:
        use_enum_values = True
    
    def add_event(self, event: EventThesis) -> None:
        """Add a new event thesis to this ticker's context.
        
        If an event with the same event_id already exists, it will be updated.
        """
        # Check if event already exists
        for i, existing in enumerate(self.events):
            if existing.event_id == event.event_id:
                self.events[i] = event
                self.last_updated = datetime.now().isoformat()
                return
        
        # Add new event
        self.events.append(event)
        self.last_updated = datetime.now().isoformat()
    
    def get_active_events(self) -> List[EventThesis]:
        """Get all active (non-resolved) event theses."""
        return [e for e in self.events if e.is_active()]
    
    def get_resolved_events(self) -> List[EventThesis]:
        """Get all resolved/expired event theses (historical context)."""
        return [e for e in self.events if not e.is_active()]
    
    def get_all_theses(self) -> List[str]:
        """Get all thesis strings for agent context with exit guidance.
        
        Returns both active and resolved theses - agents should see
        the full history to make informed decisions. For resolved events,
        includes thesis-type-aware exit guidance.
        """
        theses = []
        for event in self.events:
            status = "ACTIVE" if event.is_active() else f"RESOLVED ({event.event_state})"
            # Use get_thesis_with_guidance() to include exit recommendations
            thesis_text = event.get_thesis_with_guidance()
            theses.append(f"[{status}] {thesis_text}")
        return theses
    
    def mark_event_resolved(self, event_id: str, state: EventState) -> bool:
        """Mark an event as resolved with the given state.
        
        Args:
            event_id: The Polymarket event ID to mark as resolved
            state: The resolution state (RESOLVED_YES, RESOLVED_NO, or EXPIRED)
            
        Returns:
            True if event was found and updated, False otherwise
        """
        for event in self.events:
            if event.event_id == event_id:
                event.event_state = state
                event.resolved_date = datetime.now().strftime("%Y-%m-%d")
                self.last_updated = datetime.now().isoformat()
                return True
        return False
    
    def has_active_events(self) -> bool:
        """Check if this ticker has any active event theses."""
        return len(self.get_active_events()) > 0
    
    def get_primary_direction(self) -> Optional[str]:
        """Get the dominant impact direction from active events.
        
        Returns 'bullish', 'bearish', or None if no active events or mixed signals.
        Weighted by confidence.
        """
        active = self.get_active_events()
        if not active:
            return None
        
        bullish_weight = sum(e.confidence for e in active if e.impact_direction == "bullish")
        bearish_weight = sum(e.confidence for e in active if e.impact_direction == "bearish")
        
        if bullish_weight > bearish_weight:
            return "bullish"
        elif bearish_weight > bullish_weight:
            return "bearish"
        return None
    
    def get_context_summary(self) -> str:
        """Generate a human-readable summary for agent context."""
        active = self.get_active_events()
        resolved = self.get_resolved_events()
        
        lines = [f"Position Context for {self.ticker}:"]
        
        if active:
            lines.append(f"\nActive Events ({len(active)}):")
            for e in active:
                prob_str = f"{e.probability.current*100:.1f}%" if e.probability else "N/A"
                lines.append(f"  - {e.event_title} ({prob_str})")
                lines.append(f"    Thesis: {e.thesis}")
                lines.append(f"    Direction: {e.impact_direction} (confidence: {e.confidence}%)")
                if e.target_outcome:
                    lines.append(f"    Target outcome: {e.target_outcome}")
                if e.landscape_at_entry:
                    lines.append(f"    Landscape at entry:\n{e.landscape_at_entry}")
        
        if resolved:
            lines.append(f"\nResolved Events ({len(resolved)}) - Historical Context:")
            for e in resolved:
                lines.append(f"  - {e.event_title} → {e.event_state}")
                lines.append(f"    Original thesis: {e.thesis}")
        
        if not active and not resolved:
            lines.append("  No event context available")
        
        return "\n".join(lines)


# Backward compatibility: Create a single-event PositionContext easily
def create_position_context(
    ticker: str,
    event_id: str,
    event_title: str,
    event_type: EventType,
    thesis: str,
    thesis_type: ThesisType,
    impact_direction: str,
    confidence: int,
    probability: ProbabilitySnapshot,
    entry_date: str,
    entry_price: Optional[float] = None,
    event_state: EventState = EventState.ACTIVE,
    sequential_data: Optional[SequentialEventData] = None,
    target_outcome: Optional[str] = None,
    landscape_at_entry: Optional[str] = None,
) -> PositionContext:
    """Create a PositionContext with a single event thesis.

    This is a convenience function for backward compatibility and
    simple use cases where a ticker has only one event thesis.
    """
    event = EventThesis(
        event_id=event_id,
        event_title=event_title,
        event_type=event_type,
        event_state=event_state,
        thesis=thesis,
        thesis_type=thesis_type,
        impact_direction=impact_direction,
        confidence=confidence,
        probability=probability,
        entry_date=entry_date,
        sequential_data=sequential_data,
        target_outcome=target_outcome,
        landscape_at_entry=landscape_at_entry,
    )
    
    return PositionContext(
        ticker=ticker,
        events=[event],
        entry_price=entry_price,
    )


# ==================== Event History Tracking ====================

class AnalyzedEvent(BaseModel):
    """Record of an analyzed event for deduplication.
    
    Tracks events that have been analyzed by the discovery agent
    to prevent re-processing the same events.
    """
    event_id: str = Field(..., description="Polymarket event ID")
    event_title: str = Field(..., description="Event title for fuzzy matching")
    analyzed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when event was analyzed"
    )
    score: float = Field(default=0.0, description="Event score from EventScorer")
    mapped_tickers: List[str] = Field(
        default_factory=list,
        description="Tickers discovered from this event"
    )
    outcome: Optional[Literal["profitable", "loss", "pending"]] = Field(
        None,
        description="Trading outcome if position was taken"
    )
    
    class Config:
        use_enum_values = True


class EventHistory(BaseModel):
    """History of analyzed events for deduplication.
    
    Tracks all events that have been analyzed to prevent:
    1. Re-analyzing the same event_id
    2. Analyzing events with very similar titles (fuzzy match)
    3. Over-exposing portfolio to same event type
    
    Example:
        >>> history = EventHistory()
        >>> history.add_event(AnalyzedEvent(
        ...     event_id="abc123",
        ...     event_title="Will Trump win 2024?",
        ...     score=85.0,
        ...     mapped_tickers=["DJT", "GEO"]
        ... ))
        >>> history.has_event("abc123")
        True
        >>> history.get_events_for_ticker("DJT")
        [AnalyzedEvent(...)]
    """
    events: Dict[str, AnalyzedEvent] = Field(
        default_factory=dict,
        description="event_id -> AnalyzedEvent mapping"
    )
    ticker_event_map: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="ticker -> [event_ids] mapping"
    )
    
    # Configuration for fuzzy matching
    fuzzy_match_threshold: float = Field(
        default=0.85,
        description="Similarity threshold for fuzzy title matching (0-1)"
    )
    
    class Config:
        use_enum_values = True
    
    def add_event(self, event: AnalyzedEvent) -> None:
        """Add an analyzed event to history.
        
        Also updates the ticker_event_map for reverse lookups.
        
        Args:
            event: The AnalyzedEvent to add
        """
        self.events[event.event_id] = event
        
        # Update ticker -> event mapping
        for ticker in event.mapped_tickers:
            if ticker not in self.ticker_event_map:
                self.ticker_event_map[ticker] = []
            if event.event_id not in self.ticker_event_map[ticker]:
                self.ticker_event_map[ticker].append(event.event_id)
    
    def has_event(self, event_id: str) -> bool:
        """Check if an event has already been analyzed.
        
        Args:
            event_id: The Polymarket event ID to check
            
        Returns:
            True if event was previously analyzed
        """
        return event_id in self.events
    
    def has_similar_event(self, event_title: str) -> Optional[AnalyzedEvent]:
        """Check if a similar event title has been analyzed (fuzzy match).
        
        Uses SequenceMatcher for fuzzy string matching to detect
        events that are essentially the same but with slight title variations.
        
        Args:
            event_title: The event title to check
            
        Returns:
            The similar AnalyzedEvent if found, None otherwise
        """
        for analyzed in self.events.values():
            similarity = SequenceMatcher(
                None,
                event_title.lower(),
                analyzed.event_title.lower()
            ).ratio()
            
            if similarity >= self.fuzzy_match_threshold:
                return analyzed
        
        return None
    
    def get_events_for_ticker(self, ticker: str) -> List[AnalyzedEvent]:
        """Get all analyzed events that mapped to a specific ticker.
        
        Useful for understanding what events have already created
        exposure to a particular stock.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of AnalyzedEvent objects for this ticker
        """
        event_ids = self.ticker_event_map.get(ticker, [])
        return [self.events[eid] for eid in event_ids if eid in self.events]
    
    def get_recent_events(self, hours: int = 24) -> List[AnalyzedEvent]:
        """Get events analyzed within the specified time window.
        
        Args:
            hours: Number of hours to look back (default 24)
            
        Returns:
            List of recently analyzed events
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = []
        
        for event in self.events.values():
            try:
                analyzed_time = datetime.fromisoformat(event.analyzed_at)
                if analyzed_time >= cutoff:
                    recent.append(event)
            except (ValueError, TypeError):
                # Skip events with invalid timestamps
                continue
        
        return recent
    
    def get_ticker_exposure_count(self, ticker: str) -> int:
        """Get the number of events that have exposure to a ticker.
        
        Useful for avoiding over-concentration in a single stock.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Number of events with exposure to this ticker
        """
        return len(self.ticker_event_map.get(ticker, []))
    
    def should_skip_event(
        self,
        event_id: str,
        event_title: str,
        check_fuzzy: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """Determine if an event should be skipped (deduplication check).
        
        Checks both exact event_id match and fuzzy title match.
        
        Args:
            event_id: The Polymarket event ID
            event_title: The event title
            check_fuzzy: Whether to perform fuzzy title matching
            
        Returns:
            Tuple of (should_skip, reason)
            - should_skip: True if event should be skipped
            - reason: Explanation if skipped, None otherwise
        """
        # Check exact event_id match
        if self.has_event(event_id):
            return True, f"Event {event_id} already analyzed"
        
        # Check fuzzy title match
        if check_fuzzy:
            similar = self.has_similar_event(event_title)
            if similar:
                return True, f"Similar event already analyzed: {similar.event_title}"
        
        return False, None
    
    def clear_old_events(self, days: int = 30) -> int:
        """Remove events older than specified days.
        
        Useful for keeping history manageable over time.
        
        Args:
            days: Remove events older than this many days
            
        Returns:
            Number of events removed
        """
        cutoff = datetime.now() - timedelta(days=days)
        to_remove = []
        
        for event_id, event in self.events.items():
            try:
                analyzed_time = datetime.fromisoformat(event.analyzed_at)
                if analyzed_time < cutoff:
                    to_remove.append(event_id)
            except (ValueError, TypeError):
                continue
        
        # Remove old events
        for event_id in to_remove:
            event = self.events.pop(event_id, None)
            if event:
                # Clean up ticker_event_map
                for ticker in event.mapped_tickers:
                    if ticker in self.ticker_event_map:
                        self.ticker_event_map[ticker] = [
                            eid for eid in self.ticker_event_map[ticker]
                            if eid != event_id
                        ]
        
        return len(to_remove)
    
    def get_summary(self) -> Dict[str, any]:
        """Get a summary of the event history.
        
        Returns:
            Dict with history statistics
        """
        return {
            "total_events": len(self.events),
            "total_tickers": len(self.ticker_event_map),
            "recent_24h": len(self.get_recent_events(hours=24)),
            "recent_7d": len(self.get_recent_events(hours=168)),
        }


def build_portfolio_context(portfolio: Dict[str, PositionContext]) -> str:
    """Build context string for LLM about current portfolio.
    
    This provides the LLM with information about existing positions
    to help it avoid recommending duplicate exposure.
    
    Args:
        portfolio: Dict of ticker -> PositionContext
        
    Returns:
        Formatted string for LLM prompt injection
    """
    if not portfolio:
        return "Current Portfolio: Empty (no existing positions)"

    lines = ["Current Portfolio Positions:"]

    for ticker, context in portfolio.items():
        # Handle both PositionContext objects and dicts
        if isinstance(context, dict):
            # Convert dict to PositionContext if needed
            try:
                context = PositionContext(**context)
            except Exception:
                # If conversion fails, skip this entry
                continue

        active_events = context.get_active_events()
        direction = context.get_primary_direction()
        
        lines.append(f"\n{ticker}:")
        lines.append(f"  Direction: {direction or 'neutral'}")
        lines.append(f"  Active Theses: {len(active_events)}")
        
        # Show top 3 active event theses
        for event in active_events[:3]:
            thesis_preview = event.thesis[:50] + "..." if len(event.thesis) > 50 else event.thesis
            lines.append(f"    - {event.event_title}: {thesis_preview}")
    
    lines.append("\n\nInstructions:")
    lines.append("- For stocks already in portfolio, only add NEW event theses if highly relevant")
    lines.append("- Prioritize finding NEW stocks not in portfolio for diversification")
    lines.append("- Consider sector balance when recommending stocks")
    
    return "\n".join(lines)
