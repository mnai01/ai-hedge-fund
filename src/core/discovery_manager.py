"""
Discovery Manager - Unified discovery and update logic.

This module provides a single interface for:
1. Discovering new Polymarket events and mapping to stocks
2. Updating existing position contexts with latest probabilities
3. Detecting event resolution and generating exit guidance

The DiscoveryManager wraps existing functions from polymarket_discovery.py
to provide a clean, mode-agnostic interface for both backtest and live modes.
"""

from typing import Dict, List, Tuple, Optional, Any, Literal
from datetime import datetime
import logging

from src.agents.polymarket_discovery import (
    discover_tickers_from_events,
    update_position_contexts,
)
from src.tools.polymarket_api import (
    get_active_events,
    get_event_by_id,
    get_event_outcome,
)
from src.data.polymarket_cache import get_polymarket_cache, PolymarketCache
from src.data.position_context import EventHistory, EventState

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """
    Manages Polymarket event discovery and position context updates.

    This class provides a unified interface used by both backtest
    and live modes for:
    - Finding new trading opportunities from Polymarket
    - Keeping position contexts up-to-date
    - Detecting and handling event resolution
    
    The manager is mode-agnostic - it accepts a current_date parameter
    that can be either a simulated date (backtest) or today's date (live).
    
    Example:
        >>> manager = DiscoveryManager(
        ...     model_name="gemini-2.0-flash",
        ...     autonomous_mode=True,
        ... )
        >>> discoveries = manager.discover_new(
        ...     existing_tickers=["AAPL"],
        ...     portfolio_positions={},
        ...     current_date="2025-01-20",
        ... )
        >>> updated, resolutions = manager.update_contexts(
        ...     existing_contexts=position_contexts,
        ...     current_date="2025-01-20",
        ... )
    """

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        model_provider: str = "Google",
        autonomous_mode: bool = True,
        max_positions: int = 10,
        min_probability: float = 0.25,
        max_probability: float = 0.75,
        min_confidence: int = 70,
        min_score: float = 40.0,
        validate_with_news: bool = True,
        news_lookback_days: int = 7,
        min_news_articles: int = 3,
    ):
        """
        Initialize the DiscoveryManager.
        
        Args:
            model_name: LLM model name for stock mapping
            model_provider: LLM provider (e.g., "Google", "OpenAI")
            autonomous_mode: Whether to enable autonomous discovery
            max_positions: Maximum concurrent positions to discover
            min_probability: Minimum event probability (0-1)
            max_probability: Maximum event probability (0-1)
            min_confidence: Minimum confidence for stock mappings (0-100)
            min_score: Minimum EventScorer score to analyze
            validate_with_news: Enable news validation for stock picks
            news_lookback_days: How far back to fetch news for validation
            min_news_articles: Minimum articles required for validation
        """
        self.model_name = model_name
        self.model_provider = model_provider
        self.autonomous_mode = autonomous_mode
        self.max_positions = max_positions
        self.min_probability = min_probability
        self.max_probability = max_probability
        self.min_confidence = min_confidence
        self.min_score = min_score
        self.validate_with_news = validate_with_news
        self.news_lookback_days = news_lookback_days
        self.min_news_articles = min_news_articles

        self._cache: Optional[PolymarketCache] = None
        self._event_history: EventHistory = EventHistory()

    @property
    def cache(self) -> PolymarketCache:
        """Get or create the Polymarket cache instance."""
        if self._cache is None:
            self._cache = get_polymarket_cache()
        return self._cache

    def discover_new_events(
        self,
        existing_tickers: List[str],
        portfolio_positions: Dict[str, Dict],
        current_date: str,
        limit: Optional[int] = None,
        mode: Literal["backtest", "live"] = "backtest",
    ) -> List[Dict[str, Any]]:
        """
        Discover new trading opportunities from Polymarket events.
        
        This method wraps the existing discover_tickers_from_events function
        to provide a clean interface for the TradingCycle.

        Args:
            existing_tickers: Tickers already being tracked
            portfolio_positions: Current position contexts (ticker -> context dict)
            current_date: Date for discovery (YYYY-MM-DD)
            limit: Maximum new tickers to discover (defaults to max_positions)
            mode: "backtest" uses simulation_date, "live" uses current date

        Returns:
            List of discovered opportunities, each containing:
            - ticker: Stock symbol
            - context: Position context dict for the ticker
            - event_id: Polymarket event ID
            - event_title: Human-readable event title
        """
        if not self.autonomous_mode:
            logger.debug("Autonomous mode disabled, skipping discovery")
            return []

        effective_limit = limit if limit is not None else self.max_positions

        # Use simulation_date for backtest to prevent future knowledge
        simulation_date = current_date if mode == "backtest" else None

        try:
            # Call the existing discovery function
            discovered, self._event_history = discover_tickers_from_events(
                events=None,  # Will fetch events internally
                portfolio_positions=portfolio_positions,
                event_history=self._event_history,
                min_score=self.min_score,
                min_probability=self.min_probability,
                max_probability=self.max_probability,
                min_confidence=self.min_confidence,
                limit=effective_limit,
                cache=self.cache,
                model_name=self.model_name,
                model_provider=self.model_provider,
                skip_duplicates=True,
                validate_with_news=self.validate_with_news,
                news_lookback_days=self.news_lookback_days,
                min_news_articles=self.min_news_articles,
                simulation_date=simulation_date,
            )

            # Filter out already-tracked tickers
            new_discoveries = [
                d for d in discovered
                if d.get("ticker") not in existing_tickers
            ]

            logger.info(
                f"Discovery found {len(discovered)} opportunities, "
                f"{len(new_discoveries)} are new (not in existing tickers)"
            )

            return new_discoveries

        except Exception as e:
            logger.error(f"Error during discovery: {e}", exc_info=True)
            return []

    # Alias for backward compatibility
    discover_new = discover_new_events

    def update_existing_contexts(
        self,
        existing_contexts: Dict[str, Dict],
        current_date: str,
        mode: Literal["backtest", "live"] = "backtest",
    ) -> Tuple[Dict[str, Dict], Dict[str, str]]:
        """
        Update existing position contexts with latest data.

        This method:
        1. Fetches current event state from Polymarket
        2. Updates probability snapshots
        3. Detects event resolution
        4. Generates exit guidance for resolved events

        Args:
            existing_contexts: Current position contexts (ticker -> context dict)
            current_date: Date for update (YYYY-MM-DD)
            mode: "backtest" or "live" (affects logging only)

        Returns:
            Tuple of (updated_contexts, resolution_changes)
            - updated_contexts: Updated position contexts
            - resolution_changes: Dict of ticker -> new status if changed
        """
        if not existing_contexts:
            return {}, {}

        try:
            updated, status_changes = update_position_contexts(
                existing_context=existing_contexts,
                current_date=current_date,
                cache=self.cache,
            )

            if status_changes:
                logger.info(
                    f"Context update: {len(status_changes)} events changed status: "
                    f"{status_changes}"
                )

            return updated, status_changes

        except Exception as e:
            logger.error(f"Error updating contexts: {e}", exc_info=True)
            # Return original contexts unchanged on error
            return existing_contexts, {}

    # Alias for backward compatibility
    update_contexts = update_existing_contexts

    def check_event_resolution(
        self,
        event_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a specific event has resolved.
        
        Args:
            event_id: The Polymarket event ID to check
            
        Returns:
            Tuple of (is_resolved, outcome)
            - is_resolved: True if event has resolved
            - outcome: "Yes", "No", or None if not resolved
        """
        try:
            event = get_event_by_id(event_id, cache=self.cache)
            if not event:
                logger.warning(f"Event {event_id} not found")
                return True, None  # Treat as expired
            
            # Check if event is closed
            if not event.closed:
                return False, None
            
            # Get the outcome using the existing function
            outcome = get_event_outcome(event)
            return True, outcome
            
        except Exception as e:
            logger.error(f"Error checking event resolution: {e}", exc_info=True)
            return False, None

    def get_event_history(self) -> EventHistory:
        """
        Get the current event history for persistence.
        
        The event history tracks which events have been analyzed
        to prevent duplicate analysis.
        
        Returns:
            Current EventHistory instance
        """
        return self._event_history

    def set_event_history(self, history: EventHistory) -> None:
        """
        Restore event history from persistence.
        
        Use this to restore state when resuming a backtest
        or continuing a live trading session.
        
        Args:
            history: EventHistory instance to restore
        """
        self._event_history = history

    def clear_event_history(self) -> None:
        """Clear the event history (start fresh)."""
        self._event_history = EventHistory()

    def get_discovery_stats(self) -> Dict[str, Any]:
        """
        Get statistics about discovery operations.
        
        Returns:
            Dictionary with discovery statistics
        """
        history_summary = self._event_history.get_summary()
        return {
            "autonomous_mode": self.autonomous_mode,
            "model": f"{self.model_provider}/{self.model_name}",
            "probability_range": f"{self.min_probability:.0%}-{self.max_probability:.0%}",
            "min_confidence": self.min_confidence,
            "min_score": self.min_score,
            "events_analyzed": history_summary.get("total_events", 0),
            "tickers_discovered": history_summary.get("total_tickers", 0),
            "recent_24h": history_summary.get("recent_24h", 0),
        }
