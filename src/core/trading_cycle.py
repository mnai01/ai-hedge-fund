"""
Unified Trading Cycle - Shared between backtest and live modes.

This module implements the daily trading cycle that runs identically
in both backtest and live modes. The only difference is:
- Backtest: current_date is simulated, prices are historical
- Live: current_date is today, prices are real-time

This is the HEART of the unified architecture - ensuring that
backtest and live trading modes share the exact same core logic.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime, timedelta
import logging

from src.main import run_hedge_fund
from src.core.discovery_manager import DiscoveryManager
from src.core.position_tracker import PositionTracker

logger = logging.getLogger(__name__)


@dataclass
class TradingConfig:
    """
    Configuration for the unified trading cycle.
    
    This dataclass holds all configuration needed for trading operations,
    including LLM settings, analyst selection, and discovery parameters.
    
    Attributes:
        model_name: LLM model name (e.g., "gemini-2.0-flash", "gpt-4.1")
        model_provider: LLM provider (e.g., "Google", "OpenAI")
        selected_analysts: List of analyst keys to use
        autonomous_mode: Enable Polymarket-driven discovery
        max_positions: Maximum concurrent positions
        min_probability: Minimum event probability for discovery
        max_probability: Maximum event probability for discovery
        min_confidence: Minimum confidence for stock mappings
        min_score: Minimum EventScorer score for events
        validate_with_news: Enable news validation for stock picks
        news_lookback_days: Days of news to fetch for validation
        min_news_articles: Minimum articles for validation
        data_provider: Data provider for financial data
        long_only: Disable short selling (--no-short flag)
    """
    model_name: str = "gpt-4.1"
    model_provider: str = "OpenAI"
    selected_analysts: List[str] = field(default_factory=list)
    autonomous_mode: bool = False
    max_positions: int = 10
    min_probability: float = 0.60
    max_probability: float = 0.85
    min_confidence: int = 70
    min_score: float = 40.0
    validate_with_news: bool = True
    news_lookback_days: int = 7
    min_news_articles: int = 3
    data_provider: str = "yfinance"
    long_only: bool = False


@dataclass
class DailyCycleResult:
    """
    Result of a single daily trading cycle.
    
    This dataclass captures all outputs from a daily cycle,
    including trading decisions, discovery results, and state updates.
    
    Attributes:
        decisions: Trading decisions (ticker -> {action, quantity, reasoning})
        analyst_signals: Raw signals from each analyst
        discovered_tickers: Newly discovered tickers this cycle
        updated_tickers: Full list of tickers after discovery (for caller to update)
        resolved_events: Events that resolved (ticker -> status)
        updated_contexts: Position contexts after update
        cycle_summary: Human-readable summary
        skip_day: True if no valid tickers (skip to next day)
        error: Error message if cycle failed
    """
    decisions: Dict[str, Dict] = field(default_factory=dict)
    analyst_signals: Dict[str, Any] = field(default_factory=dict)
    discovered_tickers: List[str] = field(default_factory=list)
    updated_tickers: List[str] = field(default_factory=list)
    resolved_events: Dict[str, str] = field(default_factory=dict)
    updated_contexts: Dict[str, Dict] = field(default_factory=dict)
    cycle_summary: str = ""
    skip_day: bool = False
    error: Optional[str] = None

    def has_actions(self) -> bool:
        """Check if any non-hold actions were decided."""
        return any(
            d.get("action", "hold") != "hold"
            for d in self.decisions.values()
        )

    def get_action_summary(self) -> Dict[str, int]:
        """Get count of each action type."""
        counts = {"buy": 0, "sell": 0, "short": 0, "cover": 0, "hold": 0}
        for decision in self.decisions.values():
            action = decision.get("action", "hold")
            counts[action] = counts.get(action, 0) + 1
        return counts


class TradingCycle:
    """
    Unified daily trading cycle for both backtest and live modes.

    This class encapsulates the complete daily workflow:
    1. Discovery/Update Phase - Find new events, update existing contexts
    2. Analysis Phase - Run hedge fund agents
    3. Result Phase - Return decisions and updated state

    The caller (BacktestEngine or Trader) is responsible for:
    - Iterating through dates (backtest) or scheduling (live)
    - Executing trades based on decisions
    - Providing price data
    
    Example:
        >>> config = TradingConfig(
        ...     model_name="gemini-2.0-flash",
        ...     model_provider="Google",
        ...     selected_analysts=["warren_buffett", "technicals"],
        ...     autonomous_mode=True,
        ... )
        >>> cycle = TradingCycle(config)
        >>> result = cycle.execute_daily_cycle(
        ...     current_date="2025-01-20",
        ...     tickers=["AAPL", "MSFT"],
        ...     portfolio={"cash": 100000, "positions": {}},
        ...     position_contexts={},
        ...     mode="backtest",
        ... )
    """

    def __init__(self, config: TradingConfig):
        """
        Initialize the TradingCycle with configuration.
        
        Args:
            config: TradingConfig with all trading parameters
        """
        self.config = config
        self.discovery_manager = DiscoveryManager(
            model_name=config.model_name,
            model_provider=config.model_provider,
            autonomous_mode=config.autonomous_mode,
            max_positions=config.max_positions,
            min_probability=config.min_probability,
            max_probability=config.max_probability,
            min_confidence=config.min_confidence,
            min_score=config.min_score,
            validate_with_news=config.validate_with_news,
            news_lookback_days=config.news_lookback_days,
            min_news_articles=config.min_news_articles,
        )
        self.position_tracker = PositionTracker()

    def execute_daily_cycle(
        self,
        current_date: str,
        tickers: List[str],
        portfolio: Dict,
        position_contexts: Dict[str, Dict],
        mode: Literal["backtest", "live"] = "backtest",
        lookback_days: int = 30,
    ) -> DailyCycleResult:
        """
        Execute a single daily trading cycle.

        This method runs identically for backtest and live modes.
        The mode parameter only affects:
        - Whether to use simulation_date for LLM knowledge restriction (backtest)
        - Logging/display formatting

        Args:
            current_date: The date for this cycle (YYYY-MM-DD)
            tickers: Current list of tickers to analyze
            portfolio: Portfolio snapshot (cash, positions, etc.)
            position_contexts: Mutable dict of position contexts (updated in-place)
            mode: "backtest" or "live"
            lookback_days: Days of historical data to fetch (default 30)

        Returns:
            DailyCycleResult with decisions and updated state
        """
        discovered_tickers: List[str] = []
        resolved_events: Dict[str, str] = {}
        
        # Make a working copy of tickers to avoid mutating the input
        working_tickers = list(tickers)

        try:
            # ==================== PHASE 1: DISCOVERY/UPDATE ====================
            # This phase runs EVERY cycle, not just at the start

            if self.config.autonomous_mode:
                # 1a. Update existing position contexts
                if position_contexts:
                    logger.info(f"[{current_date}] Updating {len(position_contexts)} position contexts")
                    updated, resolutions = self.discovery_manager.update_contexts(
                        existing_contexts=position_contexts,
                        current_date=current_date,
                        mode=mode,
                    )
                    position_contexts.update(updated)
                    resolved_events = resolutions
                    
                    if resolutions:
                        logger.info(f"[{current_date}] Events resolved: {resolutions}")

                # 1b. Discover new events (if under max_positions)
                current_position_count = self._count_active_positions(portfolio)

                if current_position_count < self.config.max_positions:
                    slots_available = self.config.max_positions - current_position_count
                    logger.info(
                        f"[{current_date}] Discovering new events "
                        f"({slots_available} slots available)"
                    )
                    
                    new_discoveries = self.discovery_manager.discover_new(
                        existing_tickers=working_tickers,
                        portfolio_positions=position_contexts,
                        current_date=current_date,
                        limit=slots_available,
                        mode=mode,
                    )

                    for discovery in new_discoveries:
                        ticker = discovery.get("ticker")
                        if ticker and ticker not in working_tickers:
                            working_tickers.append(ticker)
                            discovered_tickers.append(ticker)
                            position_contexts[ticker] = discovery.get("context", {})
                            logger.info(f"[{current_date}] Discovered new ticker: {ticker}")

            # Check if we have any tickers to analyze
            if not working_tickers:
                logger.warning(f"[{current_date}] No tickers to analyze - skipping day")
                return DailyCycleResult(
                    decisions={},
                    analyst_signals={},
                    discovered_tickers=discovered_tickers,
                    updated_tickers=working_tickers,
                    resolved_events=resolved_events,
                    updated_contexts=position_contexts,
                    cycle_summary=f"[{current_date}] No tickers to analyze - skipping day",
                    skip_day=True,
                )

            # ==================== PHASE 2: ANALYSIS ====================
            # Run the hedge fund agent workflow

            # Calculate lookback period
            current_dt = datetime.strptime(current_date, "%Y-%m-%d")
            lookback_start = (current_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            logger.info(
                f"[{current_date}] Running hedge fund analysis for {len(working_tickers)} tickers"
            )

            result = run_hedge_fund(
                tickers=working_tickers,
                start_date=lookback_start,
                end_date=current_date,
                portfolio=portfolio,
                show_reasoning=False,
                selected_analysts=self.config.selected_analysts,
                model_name=self.config.model_name,
                model_provider=self.config.model_provider,
                data_provider=self.config.data_provider,
                position_context=position_contexts,  # Updated contexts
                long_only=self.config.long_only,  # Pass --no-short flag
            )

            decisions = result.get("decisions", {}) or {}
            analyst_signals = result.get("analyst_signals", {}) or {}

            # ==================== PHASE 3: BUILD RESULT ====================

            cycle_summary = self._build_summary(
                current_date=current_date,
                decisions=decisions,
                discovered_tickers=discovered_tickers,
                resolved_events=resolved_events,
                mode=mode,
            )

            return DailyCycleResult(
                decisions=decisions,
                analyst_signals=analyst_signals,
                discovered_tickers=discovered_tickers,
                updated_tickers=working_tickers,
                resolved_events=resolved_events,
                updated_contexts=position_contexts,
                cycle_summary=cycle_summary,
                skip_day=False,
            )

        except Exception as e:
            logger.error(f"[{current_date}] Error in daily cycle: {e}", exc_info=True)
            return DailyCycleResult(
                decisions={},
                analyst_signals={},
                discovered_tickers=discovered_tickers,
                updated_tickers=working_tickers,
                resolved_events=resolved_events,
                updated_contexts=position_contexts,
                cycle_summary=f"[{current_date}] Error: {str(e)}",
                skip_day=True,
                error=str(e),
            )

    def _count_active_positions(self, portfolio: Dict) -> int:
        """
        Count the number of active positions in the portfolio.
        
        A position is considered active if it has non-zero long or short shares.
        
        Args:
            portfolio: Portfolio dictionary with positions
            
        Returns:
            Number of active positions
        """
        positions = portfolio.get("positions", {})
        count = 0
        for ticker, pos in positions.items():
            if isinstance(pos, dict):
                long_shares = pos.get("long", 0) or 0
                short_shares = pos.get("short", 0) or 0
                if long_shares > 0 or short_shares > 0:
                    count += 1
        return count

    def _build_summary(
        self,
        current_date: str,
        decisions: Dict,
        discovered_tickers: List[str],
        resolved_events: Dict[str, str],
        mode: str,
    ) -> str:
        """
        Build human-readable cycle summary.
        
        Args:
            current_date: The date of this cycle
            decisions: Trading decisions
            discovered_tickers: Newly discovered tickers
            resolved_events: Events that resolved
            mode: "backtest" or "live"
            
        Returns:
            Formatted summary string
        """
        lines = [f"=== {mode.upper()} CYCLE: {current_date} ==="]

        if discovered_tickers:
            lines.append(f"[DISCOVERY] New tickers: {', '.join(discovered_tickers)}")

        if resolved_events:
            for ticker, status in resolved_events.items():
                lines.append(f"[RESOLVED] {ticker}: {status}")

        action_counts = {"buy": 0, "sell": 0, "short": 0, "cover": 0, "hold": 0}
        for ticker, decision in decisions.items():
            action = decision.get("action", "hold")
            action_counts[action] = action_counts.get(action, 0) + 1

        active_actions = [f"{k}:{v}" for k, v in action_counts.items() if v > 0]
        if active_actions:
            lines.append(f"[DECISIONS] {', '.join(active_actions)}")
        else:
            lines.append("[DECISIONS] No decisions made")

        return "\n".join(lines)

    def get_position_tracker(self) -> PositionTracker:
        """
        Get the position tracker instance.
        
        Returns:
            The PositionTracker used by this cycle
        """
        return self.position_tracker

    def get_discovery_manager(self) -> DiscoveryManager:
        """
        Get the discovery manager instance.
        
        Returns:
            The DiscoveryManager used by this cycle
        """
        return self.discovery_manager

    def get_config(self) -> TradingConfig:
        """
        Get the trading configuration.
        
        Returns:
            The TradingConfig used by this cycle
        """
        return self.config


def is_weekend(date_str: str) -> bool:
    """
    Check if a date is a weekend.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        True if Saturday or Sunday
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.weekday() >= 5  # Saturday = 5, Sunday = 6


def adjust_to_business_day(date_str: str, forward: bool = True) -> str:
    """
    Adjust a weekend date to the nearest business day.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        forward: If True, move to next business day; if False, move to previous
        
    Returns:
        Adjusted date string in YYYY-MM-DD format
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = dt.weekday()
    
    if weekday == 5:  # Saturday
        delta = timedelta(days=2 if forward else -1)
    elif weekday == 6:  # Sunday
        delta = timedelta(days=1 if forward else -2)
    else:
        delta = timedelta(days=0)
    
    return (dt + delta).strftime("%Y-%m-%d")
