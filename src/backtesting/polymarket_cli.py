#!/usr/bin/env python3
"""
Polymarket Event Backtest CLI Tool

A standalone research tool for backtesting Polymarket event correlations with stock prices.
This is SEPARATE from the main hedge fund CLI (src/backtesting/cli.py).

WORKFLOW:
=========
1. Historical Backtest (--start-date):
   - Simulates running the app on a specific historical date
   - Fetches events that were ACTIVE on that date
   - Applies multi-stage filtering pipeline:
     a) Algorithmic scoring (EventScorer)
     b) AI stock relevance check (LLM filters non-stock-relevant events)
     c) Stock discovery (LLM maps events to affected stocks)
     d) News validation (validates stock picks with historical news)
   - Runs backtest simulation for each discovered stock

2. Single Event Backtest (--event-slug):
   - Tests a specific event directly (skips event discovery)
   - Uses LLM to discover affected stocks (or use --tickers to skip)
   - Calculates correlation between probability changes and stock prices

KEY FLAGS:
==========
    --start-date        Simulate running the app on this historical date
    --event-slug        Test a specific Polymarket event by slug
    --tickers           Skip LLM discovery, use these tickers (space-separated)
    --direction         Direction for manual tickers: bullish or bearish
    --no-short          Disable short selling (long positions only)
    --min-probability   Minimum probability threshold for entry signals (default: 0.70)
    --min-score         Minimum EventScorer score (default: 50.0)
    --min-relevance     Minimum stock relevance level: high, medium, low (default: medium)
    --verbose           Show detailed output

EXAMPLES:
=========
    # Historical backtest - simulate running on Jan 1, 2024
    poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --max-events 5

    # Historical backtest - long only (no short positions)
    poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --no-short

    # Single event with AI stock discovery
    poetry run python -m src.backtesting.polymarket_cli --event-slug presidential-election-winner-2024

    # Single event with manual tickers
    poetry run python -m src.backtesting.polymarket_cli --event-slug presidential-election-winner-2024 --tickers DJT XOM --direction bullish
"""

import argparse
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import json

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.tools.polymarket_api import (
    get_event_by_slug,
    get_price_history,
    get_price_history_for_event,
    get_resolved_events,
    get_event_outcome,
    get_events_active_on_date,
    get_outcome_landscape,
)
from src.tools.event_scorer import EventScorer
from src.tools.api import get_prices, prices_to_df
from src.data.polymarket_models import (
    PolymarketEvent,
    PriceHistory,
    EventStockImpact,
    OutcomeLandscape,
)
from src.data.polymarket_cache import get_polymarket_cache

# Import validation and relevance functions from polymarket_discovery
from src.agents.polymarket_discovery import (
    StockMapping,
    validate_stock_picks,
    ValidationResult,
    StockRelevanceResponse,
    assess_stock_relevance,
    batch_assess_stock_relevance,
)

# Import event portfolio for deduplication and entry signal checking
from src.data.event_portfolio import (
    EventPortfolio,
    EventExposure,
    has_entry_potential,
    get_entry_signal_summary,
    get_probability_at_date,
    compute_probability_conviction,
    compute_landscape_conviction,
    format_conviction_for_prompt,
    format_landscape_for_prompt,
    print_landscape_table,
    print_binary_event_table,
    check_duplicate,
    fuzzy_title_match,
    load_portfolio,
    save_portfolio,
    DeduplicationResult,
)
from src.data.polymarket_models import ProbabilityConviction

# Import Pydantic for model definitions
from pydantic import BaseModel, Field
from typing import Literal
from rich.console import Console

# Rich console for enhanced logging
_console = Console()


# ==================== Phase Progress Checklist ====================

PIPELINE_PHASES = [
    ("discovery",  "Event Discovery"),
    ("scoring",    "Algorithmic Scoring"),
    ("conviction", "Conviction & Probability Check"),
    ("dedup",      "Deduplication"),
    ("relevance",  "AI Stock Relevance Check"),
    ("backtest",   "Stock Discovery & Backtest"),
]


def print_progress(completed: set, current: str = "", summary: dict = None) -> None:
    """Print the pipeline progress checklist.

    Args:
        completed: Set of completed phase keys
        current: Key of the currently running phase (shown with spinner)
        summary: Optional dict mapping phase key -> short result string
    """
    summary = summary or {}
    print()
    for key, label in PIPELINE_PHASES:
        if key in completed:
            result = f"  {summary[key]}" if key in summary else ""
            print(f"   ✅ {label}{result}")
        elif key == current:
            print(f"   ⏳ {label} ...")
        else:
            print(f"   ⬚  {label}")
    print()


# ==================== Pydantic Models for LLM ====================

class StockImpact(BaseModel):
    """A single stock impact from a Polymarket event."""
    ticker: str = Field(description="US stock ticker symbol")
    direction: Literal["bullish", "bearish"] = Field(
        description="bullish if event probability increase is good for stock, bearish if bad"
    )
    confidence: int = Field(ge=0, le=100, description="Confidence 0-100")
    reasoning: str = Field(description="Brief explanation")


class StockDiscoveryResponse(BaseModel):
    """Response from LLM for stock discovery."""
    stocks: List[StockImpact] = Field(default_factory=list)
    event_relevance: Literal["high", "medium", "low"] = Field(
        description="How relevant this event is to stock markets"
    )


# ==================== LLM Stock Discovery ====================

def discover_affected_stocks(
    event: PolymarketEvent,
    max_stocks: int = 5,
    model_name: str = "gemini-3-flash-preview",
    model_provider: str = "Google",
    conviction: Optional[ProbabilityConviction] = None,
    landscape: Optional[OutcomeLandscape] = None,
) -> List[Dict[str, Any]]:
    """
    Use LLM to discover stocks affected by a Polymarket event.

    Args:
        event: The Polymarket event
        max_stocks: Maximum number of stocks to return
        model_name: LLM model name (default: gemini-3-flash-preview)
        model_provider: LLM provider (default: Google)
        conviction: Optional conviction analysis to inject into prompt
        landscape: Optional OutcomeLandscape for multi-outcome events

    Returns:
        List of dicts with ticker, direction, confidence, reasoning
    """
    try:
        from langchain_core.messages import HumanMessage
        from src.utils.llm import call_llm
        from src.data.event_portfolio import format_landscape_for_prompt

        # Build conviction section if available
        conviction_section = ""
        if conviction:
            conviction_section = "\n" + format_conviction_for_prompt(conviction) + "\n"

        # Build landscape section if available
        landscape_section = ""
        if landscape:
            landscape_section = "\n" + format_landscape_for_prompt(landscape) + "\n"

        prompt = f"""You are a financial analyst identifying US stocks affected by prediction market events.

EVENT DETAILS:
- Title: {event.title}
- Description: {event.description or 'No description available'}
- Current Probability: {event.probability:.1%} if event.probability else 'Unknown'
- Category: {event.category or 'Unknown'}
{conviction_section}{landscape_section}
ANALYSIS FRAMEWORK - Consider BOTH direct AND indirect impacts:

1. DIRECT CONNECTIONS:
   - Companies directly named or involved in the event
   - Example: DJT (Trump Media) for Trump election events

2. POLICY IMPLICATIONS (for political events):
   - Energy Policy: Solar/wind stocks (FSLR, ENPH, TAN) vs Oil/gas (XOM, CVX, OXY)
   - Defense Spending: Defense contractors (LMT, RTX, NOC, GD)
   - Trade/Tariffs: Import-dependent companies, China-exposed stocks
   - Regulation: Banks (JPM, GS) for deregulation, Tech for antitrust
   - Healthcare: Pharma (PFE, JNJ), Insurers (UNH) for policy changes
   - Immigration: Private prisons (GEO, CXW), agriculture, construction
   - EV Policy: Tesla (TSLA), traditional auto (F, GM), charging (CHPT)

3. HISTORICAL PATTERNS - What has history shown?
   - How did similar events affect markets in the past?
   - 2016 Trump election: Defense +, Solar -, Banks +, Private prisons +
   - 2020 Biden election: Clean energy +, Oil -, EV +
   - Fed rate decisions: Banks, REITs, growth vs value rotation
   - Geopolitical tensions: Defense +, Airlines -, Oil volatility

4. SECTOR ROTATIONS:
   - Risk-on vs risk-off sentiment shifts
   - Growth vs value implications
   - Domestic vs international exposure

REQUIREMENTS:
- Include BOTH bullish AND bearish stocks (winners AND losers)
- Maximum {max_stocks} stocks total
- Focus on liquid US-listed INDIVIDUAL stocks (NYSE, NASDAQ)
- NO ETFs or index funds (no SPY, QQQ, VNQ, SCHD, XLF, TAN, etc.) — only individual companies
- Higher confidence for direct connections, lower for indirect

For each stock provide:
- ticker: Individual stock symbol (e.g., XOM, FSLR, DJT) — NOT ETFs
- direction: "bullish" if event probability INCREASING helps the stock, "bearish" if it hurts
- confidence: 0-100 (higher for direct, lower for indirect policy implications)
- reasoning: Brief explanation including historical context if relevant

Respond ONLY with valid JSON:
{{"stocks": [{{"ticker": "SYMBOL", "direction": "bullish", "confidence": 80, "reasoning": "explanation"}}], "event_relevance": "high"}}
"""
        
        # Create a minimal state for call_llm with the selected model
        state = {
            "data": {},
            "metadata": {
                "model_name": model_name,
                "model_provider": model_provider,
            }
        }
        
        result = call_llm(
            prompt=prompt,
            pydantic_model=StockDiscoveryResponse,
            agent_name="polymarket_cli",
            state=state,
            max_retries=2,
        )
        
        if result and result.stocks:
            from src.agents.polymarket_discovery import is_etf
            stocks = []
            for s in result.stocks:
                if is_etf(s.ticker):
                    print(f"   ⚠️ Filtering out {s.ticker} (ETF — need individual stocks)")
                    continue
                stocks.append({
                    "ticker": s.ticker,
                    "direction": s.direction,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                })
            return stocks
        
        return []
        
    except ImportError as e:
        print(f"⚠ LLM not available: {e}")
        print("  Install langchain and set up API keys for LLM stock discovery")
        return []
    except Exception as e:
        print(f"⚠ Error discovering stocks: {e}")
        return []


# ==================== Correlation Analysis ====================

def calculate_correlation(
    prob_changes: List[float],
    stock_changes: List[float],
) -> float:
    """Calculate Pearson correlation coefficient."""
    if len(prob_changes) < 2 or len(stock_changes) < 2:
        return 0.0
    
    n = len(prob_changes)
    mean_prob = sum(prob_changes) / n
    mean_stock = sum(stock_changes) / n
    
    numerator = sum(
        (prob_changes[i] - mean_prob) * (stock_changes[i] - mean_stock)
        for i in range(n)
    )
    
    denom_prob = sum((p - mean_prob) ** 2 for p in prob_changes) ** 0.5
    denom_stock = sum((s - mean_stock) ** 2 for s in stock_changes) ** 0.5
    
    if denom_prob == 0 or denom_stock == 0:
        return 0.0
    
    return numerator / (denom_prob * denom_stock)


def interpret_correlation(correlation: float) -> str:
    """Interpret correlation coefficient."""
    abs_corr = abs(correlation)
    
    if abs_corr < 0.1:
        strength = "negligible"
    elif abs_corr < 0.3:
        strength = "weak"
    elif abs_corr < 0.5:
        strength = "moderate"
    elif abs_corr < 0.7:
        strength = "strong"
    else:
        strength = "very strong"
    
    direction = "positive" if correlation > 0 else "negative"
    
    return f"{strength} {direction}"


def analyze_correlation(
    price_history: PriceHistory,
    stock_prices: Any,
    direction: str,
) -> Dict[str, Any]:
    """
    Analyze correlation between event probability and stock price.
    
    Args:
        price_history: Polymarket probability history
        stock_prices: DataFrame of stock prices
        direction: Expected direction ("bullish" or "bearish")
    
    Returns:
        Dict with correlation analysis results
    """
    if not price_history.history or len(price_history.history) < 2:
        return {"error": "Insufficient probability data"}
    
    if stock_prices is None or stock_prices.empty:
        return {"error": "No stock price data"}
    
    # Calculate daily changes
    prob_changes = []
    stock_changes = []
    matched_dates = []
    
    for i in range(1, len(price_history.history)):
        prev_prob = price_history.history[i - 1]
        curr_prob = price_history.history[i]
        
        prob_change = curr_prob.probability - prev_prob.probability
        
        # Find corresponding stock price change
        date_str = curr_prob.datetime.strftime("%Y-%m-%d")
        
        try:
            date_matches = stock_prices.index.strftime("%Y-%m-%d")
            if date_str in date_matches:
                idx = list(date_matches).index(date_str)
                if idx > 0:
                    # Use .item() to safely convert single-element Series to scalar
                    prev_close = stock_prices.iloc[idx - 1]["close"]
                    curr_close = stock_prices.iloc[idx]["close"]
                    prev_price = float(prev_close.item() if hasattr(prev_close, 'item') else prev_close)
                    curr_price = float(curr_close.item() if hasattr(curr_close, 'item') else curr_close)
                    stock_change = (curr_price - prev_price) / prev_price
                    
                    prob_changes.append(prob_change)
                    stock_changes.append(stock_change)
                    matched_dates.append(date_str)
        except (KeyError, IndexError, ValueError):
            continue
    
    if len(prob_changes) < 5:
        return {
            "error": "Insufficient matched data points",
            "matched_points": len(prob_changes),
        }
    
    # Calculate correlation
    correlation = calculate_correlation(prob_changes, stock_changes)
    
    # Adjust for expected direction
    # If direction is "bearish", we expect negative correlation
    expected_sign = 1 if direction == "bullish" else -1
    actual_sign = 1 if correlation > 0 else -1
    direction_match = expected_sign == actual_sign
    
    return {
        "correlation": round(correlation, 4),
        "interpretation": interpret_correlation(correlation),
        "data_points": len(prob_changes),
        "direction_match": direction_match,
        "expected_direction": direction,
        "avg_prob_change": round(sum(prob_changes) / len(prob_changes) * 100, 4),
        "avg_stock_change": round(sum(stock_changes) / len(stock_changes) * 100, 4),
    }


# ==================== Backtest Simulation ====================

def find_entry_date(
    price_history: PriceHistory,
    min_probability: float = 0.70,
    earliest_date: Optional[str] = None,
) -> Optional[str]:
    """
    Find the entry date when probability first crosses threshold.

    Both bullish and bearish stocks use the SAME entry signal (prob >= threshold)
    because we're betting ON the event happening. The direction just determines
    whether we go long (bullish) or short (bearish) on the stock.

    Args:
        price_history: Polymarket probability history
        min_probability: Minimum probability to trigger entry (default 70%)
        earliest_date: If set, ignore data points before this date (YYYY-MM-DD).
                       Used by historical backtests to prevent look-ahead bias.

    Returns:
        Entry date as string (YYYY-MM-DD) or None if threshold never crossed
    """
    if not price_history.history:
        return None

    earliest_dt = None
    if earliest_date:
        earliest_dt = datetime.strptime(earliest_date, "%Y-%m-%d")

    for point in price_history.history:
        # Skip data points before the simulation date
        if earliest_dt and point.datetime < earliest_dt:
            continue

        prob = point.probability

        # Entry signal: probability crosses threshold (same for all stocks)
        # Direction (bullish/bearish) determines long vs short position, not entry timing
        if prob >= min_probability:
            return point.datetime.strftime("%Y-%m-%d")

    return None


def simulate_backtest(
    price_history: PriceHistory,
    stock_prices: Any,
    direction: str,
    min_probability: float = 0.70,
    hold_days: int = 0,
    earliest_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulate trading based on probability threshold.

    Both bullish and bearish stocks use the SAME entry signal (prob >= threshold)
    because we're betting ON the event happening. The direction determines:
    - Bullish: Go LONG on the stock (stock goes UP if event happens)
    - Bearish: Go SHORT on the stock (stock goes DOWN if event happens)

    Args:
        price_history: Polymarket probability history
        stock_prices: DataFrame of stock prices (should extend beyond event end if hold_days > 0)
        direction: Expected direction ("bullish" = long, "bearish" = short)
        min_probability: Minimum probability to trigger entry (default 70%)
        hold_days: Days to hold after event resolution (default 0 = exit at event end)
        earliest_date: If set, ignore data points before this date (YYYY-MM-DD).
                       Used by historical backtests to prevent look-ahead bias.

    Returns:
        Dict with backtest results
    """
    if not price_history.history or stock_prices is None or stock_prices.empty:
        return {"error": "Insufficient data"}

    earliest_dt = None
    if earliest_date:
        earliest_dt = datetime.strptime(earliest_date, "%Y-%m-%d")

    # Find entry point (when probability first crosses threshold)
    # Same threshold for both bullish and bearish - we're betting the event happens
    entry_date = None
    entry_prob = None
    entry_price = None

    for point in price_history.history:
        # Skip data points before the simulation date
        if earliest_dt and point.datetime < earliest_dt:
            continue

        prob = point.probability

        # Entry signal: probability crosses threshold (same for all stocks)
        # Direction determines long vs short position, not entry timing
        if prob >= min_probability:
            entry_date = point.datetime
            entry_prob = prob
            break

    if entry_date is None:
        return {
            "error": f"Probability never crossed {min_probability:.0%} threshold after {earliest_date or 'start'}",
            "max_probability": max(p.probability for p in price_history.history),
            "min_probability": min(p.probability for p in price_history.history),
        }
    
    # Find entry price
    entry_date_str = entry_date.strftime("%Y-%m-%d")
    try:
        date_matches = stock_prices.index.strftime("%Y-%m-%d")
        if entry_date_str in date_matches:
            idx = list(date_matches).index(entry_date_str)
            close_val = stock_prices.iloc[idx]["close"]
            entry_price = float(close_val.item() if hasattr(close_val, 'item') else close_val)
        else:
            # Find closest date after entry
            for i, d in enumerate(date_matches):
                if d >= entry_date_str:
                    close_val = stock_prices.iloc[i]["close"]
                    entry_price = float(close_val.item() if hasattr(close_val, 'item') else close_val)
                    entry_date_str = d
                    break
    except (KeyError, IndexError, ValueError):
        return {"error": "Could not find entry price"}
    
    if entry_price is None:
        return {"error": "Could not find entry price"}
    
    # Exit at end of event + hold_days
    event_end_date = price_history.history[-1].datetime
    exit_prob = price_history.history[-1].probability
    
    # Calculate target exit date (event end + hold days)
    from datetime import timedelta
    target_exit_date = event_end_date + timedelta(days=hold_days)
    target_exit_str = target_exit_date.strftime("%Y-%m-%d")
    
    # Find the exit price - either at target date or last available
    exit_price = None
    exit_date_str = None
    
    try:
        date_matches = stock_prices.index.strftime("%Y-%m-%d")
        
        # Try to find exact target date or closest date after
        for i, d in enumerate(date_matches):
            if d >= target_exit_str:
                exit_close = stock_prices.iloc[i]["close"]
                exit_price = float(exit_close.item() if hasattr(exit_close, 'item') else exit_close)
                exit_date_str = d
                break
        
        # If no date found after target, use last available
        if exit_price is None:
            exit_close = stock_prices.iloc[-1]["close"]
            exit_price = float(exit_close.item() if hasattr(exit_close, 'item') else exit_close)
            exit_date_str = stock_prices.index[-1].strftime("%Y-%m-%d")
    except (KeyError, IndexError, ValueError):
        # Fallback to last available price
        exit_close = stock_prices.iloc[-1]["close"]
        exit_price = float(exit_close.item() if hasattr(exit_close, 'item') else exit_close)
        exit_date_str = stock_prices.index[-1].strftime("%Y-%m-%d")
    
    # Calculate return
    if direction == "bullish":
        # Long position
        return_pct = (exit_price - entry_price) / entry_price * 100
    else:
        # Short position
        return_pct = (entry_price - exit_price) / entry_price * 100
    
    return {
        "entry_date": entry_date_str,
        "entry_price": round(entry_price, 2),
        "entry_probability": round(entry_prob * 100, 1),
        "exit_date": exit_date_str,
        "exit_price": round(exit_price, 2),
        "exit_probability": round(exit_prob * 100, 1),
        "position": "long" if direction == "bullish" else "short",
        "return_pct": round(return_pct, 2),
        "holding_days": (datetime.strptime(exit_date_str, "%Y-%m-%d") - 
                        datetime.strptime(entry_date_str, "%Y-%m-%d")).days,
    }


# ==================== Main CLI ====================

def run_backtest(
    event_slug: str,
    tickers: Optional[List[str]] = None,
    direction: str = "bullish",
    min_probability: float = 0.70,
    verbose: bool = False,
    use_llm: bool = True,
    model_name: str = "gemini-3-flash-preview",
    model_provider: str = "Google",
    long_hold_days: int = 7,
    short_hold_days: int = 0,
    long_only: bool = False,
    simulation_date: Optional[str] = None,
    conviction: Optional[ProbabilityConviction] = None,
    landscape: Optional[OutcomeLandscape] = None,
) -> Dict[str, Any]:
    """
    Run a complete backtest for a Polymarket event.

    Args:
        event_slug: The event slug from Polymarket URL
        tickers: Optional list of tickers (if None, LLM discovers them)
        direction: Direction for manual tickers - 'bullish' (long) or 'bearish' (short)
        min_probability: Minimum probability threshold for signals
        verbose: Print detailed output
        use_llm: Whether to use LLM for stock discovery (auto-disabled when tickers provided)
        model_name: LLM model name for stock discovery (default: gemini-3-flash-preview)
        model_provider: LLM provider (default: Google)
        long_hold_days: Days to hold long positions after event resolution (default: 7)
        short_hold_days: Days to hold short positions after event resolution (default: 0)
        long_only: Disable short selling - filter out bearish stocks (--no-short flag)
        simulation_date: If set, constrain entry to this date or later (YYYY-MM-DD).
                         Prevents look-ahead bias in historical backtests.
        conviction: Optional ProbabilityConviction for strategy guidance in LLM prompt.

    Returns:
        Dict with complete backtest results
    """
    results = {
        "event_slug": event_slug,
        "timestamp": datetime.now().isoformat(),
        "min_probability_threshold": min_probability,
    }
    
    # Step 1: Fetch event
    print(f"\n{'='*60}")
    print(f"📊 Polymarket Event Backtest")
    print(f"{'='*60}")
    print(f"\nFetching event: {event_slug}...")
    
    cache = get_polymarket_cache()
    
    try:
        event = get_event_by_slug(event_slug, cache=cache)
    except Exception as e:
        print(f"❌ Error fetching event: {e}")
        results["error"] = str(e)
        return results
    
    if not event:
        print(f"❌ Event not found: {event_slug}")
        results["error"] = "Event not found"
        return results
    
    print(f"\n✅ Event: {event.title}")
    print(f"   Category: {event.category or 'Unknown'}")
    print(f"   Current Probability: {event.probability:.1%}" if event.probability else "   Probability: Unknown")
    if event.is_multi_outcome:
        print(f"   Multi-outcome: Yes ({len(event.markets)} markets, neg-risk)")

    # Show landscape if provided, or fetch it for multi-outcome events
    if landscape:
        print_landscape_table(landscape, indent="   ")
    elif event.is_multi_outcome:
        try:
            landscape = get_outcome_landscape(event, cache=cache)
            if landscape:
                print_landscape_table(landscape, indent="   ")
        except Exception:
            pass

    results["event"] = {
        "id": event.id,
        "title": event.title,
        "category": event.category,
        "probability": event.probability,
        "description": event.description[:200] if event.description else None,
        "is_multi_outcome": event.is_multi_outcome,
        "num_markets": len(event.markets) if event.markets else 1,
    }

    # Step 2: Get price history
    print(f"\nFetching probability history...")
    
    try:
        price_history = get_price_history_for_event(
            event=event,
            interval="max",
            fidelity=1440,  # Daily data
            cache=cache,
        )
    except Exception as e:
        print(f"❌ Error fetching price history: {e}")
        results["error"] = str(e)
        return results
    
    if not price_history or not price_history.history:
        print(f"❌ No price history available")
        results["error"] = "No price history"
        return results
    
    # Extract date range from history
    start_date = price_history.history[0].datetime
    end_date = price_history.history[-1].datetime
    
    print(f"✅ Price history: {len(price_history.history)} data points")
    print(f"   Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"   Earliest probability: {price_history.earliest_probability:.1%}")
    print(f"   Latest probability: {price_history.latest_probability:.1%}")
    
    results["price_history"] = {
        "data_points": len(price_history.history),
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "earliest_probability": price_history.earliest_probability,
        "latest_probability": price_history.latest_probability,
    }
    
    # Step 3: Discover or use provided tickers
    stock_mappings = []
    entry_date = None  # Will be set when we find entry signal
    
    if tickers:
        print(f"\n📈 Using provided tickers: {', '.join(tickers)} ({direction})")
        position_type = "LONG" if direction == "bullish" else "SHORT"
        stock_mappings = [{"ticker": t, "direction": direction, "confidence": 50, "reasoning": "User provided"} for t in tickers]
        
        # Find entry date for manual tickers too
        entry_date = find_entry_date(
            price_history=price_history,
            min_probability=min_probability,
            earliest_date=simulation_date,
        )

        if not entry_date:
            constraint = f" after {simulation_date}" if simulation_date else ""
            print(f"\n⚠️ No entry signal: Probability never crossed >{min_probability:.0%} threshold{constraint}")
            results["error"] = f"No entry signal{constraint}"
            return results

        print(f"📅 Entry signal date: {entry_date} (prob crossed {min_probability:.0%})")
        
    elif use_llm:
        print(f"\n🤖 Discovering affected stocks with AI ({model_name})...")
        stock_mappings = discover_affected_stocks(
            event,
            max_stocks=5,
            model_name=model_name,
            model_provider=model_provider,
            conviction=conviction,
            landscape=landscape,
        )
        
        if stock_mappings:
            print(f"\n✅ AI-Identified Affected Stocks ({len(stock_mappings)}):")
            for s in stock_mappings:
                direction_emoji = "📈" if s['direction'] == "bullish" else "📉"
                position_type = "LONG" if s['direction'] == "bullish" else "SHORT"
                print(f"   • {s['ticker']} ({position_type}) {direction_emoji} - Confidence: {s['confidence']}%")
                # Always show thesis (truncated)
                reasoning = s.get('reasoning', '')
                if reasoning:
                    thesis_preview = reasoning[:80] + ('...' if len(reasoning) > 80 else '')
                    print(f"     └─ {thesis_preview}")
            
            # Step 3b: Find entry date (same for all stocks - when prob crosses threshold)
            # When simulation_date is set, entry can't be before that date (no look-ahead)
            entry_date = find_entry_date(
                price_history=price_history,
                min_probability=min_probability,
                earliest_date=simulation_date,
            )

            if not entry_date:
                constraint = f" after {simulation_date}" if simulation_date else ""
                print(f"\n⚠️ No entry signal: Probability never crossed >{min_probability:.0%} threshold{constraint}")
                results["error"] = f"No entry signal{constraint}"
                return results

            print(f"\n📅 Entry signal date: {entry_date} (prob crossed {min_probability:.0%})")
            
            # Step 3c: Validate ALL stocks in one batch with news from entry date
            print(f"\n📰 Validating {len(stock_mappings)} stocks with historical news (as of {entry_date})...")
            
            # Convert to StockMapping objects for validation
            stock_mapping_objects = [
                StockMapping(
                    ticker=s['ticker'],
                    direction=s['direction'],
                    confidence=s['confidence'],
                    thesis=s.get('reasoning', ''),
                    thesis_type="short_term",
                    reasoning=s.get('reasoning', ''),
                )
                for s in stock_mappings
            ]
            
            # Validate all stocks in one batch call
            validated_mappings = validate_stock_picks(
                event=event,
                stock_mappings=stock_mapping_objects,
                model_name=model_name,
                model_provider=model_provider,
                max_validation_retries=1,
                news_lookback_days=7,
                min_news_articles=3,
                as_of_date=entry_date,
            )
            
            # Filter out rejected stocks and convert back to dict format
            stock_mappings = [
                {
                    "ticker": vm.ticker,
                    "direction": vm.direction,
                    "confidence": vm.confidence,
                    "original_confidence": vm.original_confidence,
                    "reasoning": vm.reasoning,
                    "validation_result": vm.validation_result.value,
                    "company_status": vm.company_status.value,
                    "news_event_insight": vm.news_event_insight,
                    "validation_reasoning": vm.validation_reasoning,
                }
                for vm in validated_mappings
                if vm.validation_result != ValidationResult.REJECT
            ]
            
            # Show final validated picks
            if stock_mappings:
                print(f"\n🎯 Final Validated Stock Picks ({len(stock_mappings)}):")
                for s in stock_mappings:
                    direction_emoji = "📈" if s['direction'] == "bullish" else "📉"
                    position_type = "LONG" if s['direction'] == "bullish" else "SHORT"
                    validation_emoji = {"keep": "✅", "adjust": "🔄", "replace": "🔀"}.get(s.get('validation_result', 'keep'), "✅")
                    print(f"   • {s['ticker']} ({position_type}) {direction_emoji} - Confidence: {s['confidence']}% [{validation_emoji}]")
            else:
                print(f"\n⚠️ All stocks were rejected during validation")
        else:
            print(f"⚠️ No stocks identified by AI")
    else:
        print(f"\n⚠ No tickers provided and LLM disabled. Use --tickers to specify stocks.")
        results["error"] = "No tickers to analyze"
        return results
    
    if not stock_mappings:
        results["error"] = "No stocks to analyze"
        return results
    
    # Filter out bearish stocks when long_only is enabled (--no-short flag)
    if long_only:
        original_count = len(stock_mappings)
        stock_mappings = [s for s in stock_mappings if s['direction'] == 'bullish']
        filtered_count = original_count - len(stock_mappings)
        if filtered_count > 0:
            print(f"\n🚫 Long-only mode: Filtered out {filtered_count} bearish (short) positions")
        if not stock_mappings:
            print(f"\n⚠️ No bullish stocks remaining after long-only filter")
            results["error"] = "No bullish stocks to analyze (long-only mode)"
            return results
    
    results["stock_mappings"] = stock_mappings
    
    # Step 4: Analyze each stock (validation already done in batch above)
    print(f"\n{'='*60}")
    print(f"📈 Correlation Analysis")
    print(f"{'='*60}")
    
    stock_results = []
    
    for mapping in stock_mappings:
        ticker = mapping["ticker"]
        stock_direction = mapping["direction"]
        validated_confidence = mapping.get("confidence", 50)
        original_confidence = mapping.get("original_confidence", validated_confidence)
        
        # Determine hold days based on direction (long vs short position)
        hold_days = long_hold_days if stock_direction == "bullish" else short_hold_days
        position_type = "LONG" if stock_direction == "bullish" else "SHORT"
        
        print(f"\nAnalyzing {ticker} ({position_type})...")
        
        # Fetch stock prices for the event date range + hold days
        # Extend end date to capture post-event price action
        from datetime import timedelta
        extended_end_date = end_date + timedelta(days=hold_days + 7)  # Extra buffer for weekends
        
        try:
            stock_price_data = get_prices(
                ticker=ticker,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=extended_end_date.strftime("%Y-%m-%d"),
                data_provider="yfinance",
            )
            
            if not stock_price_data:
                print(f"   ⚠ No price data for {ticker}")
                stock_results.append({
                    "ticker": ticker,
                    "direction": stock_direction,
                    "error": "No price data",
                })
                continue
            
            stock_df = prices_to_df(stock_price_data)
            
        except Exception as e:
            print(f"   ⚠ Error fetching {ticker}: {e}")
            stock_results.append({
                "ticker": ticker,
                "direction": stock_direction,
                "error": str(e),
            })
            continue
        
        # Calculate correlation (use only event date range for correlation)
        correlation_result = analyze_correlation(
            price_history=price_history,
            stock_prices=stock_df,
            direction=stock_direction,
        )
        
        if "error" in correlation_result:
            print(f"   ⚠ {correlation_result['error']}")
            stock_results.append({
                "ticker": ticker,
                "direction": stock_direction,
                **correlation_result,
            })
            continue
        
        # Print correlation results
        corr = correlation_result["correlation"]
        interp = correlation_result["interpretation"]
        match = "✅" if correlation_result["direction_match"] else "❌"
        
        print(f"   Correlation: {corr:+.4f} ({interp}) {match}")
        print(f"   Data points: {correlation_result['data_points']}")
        
        # Simulate backtest (uses extended stock data for hold period)
        backtest_result = simulate_backtest(
            price_history=price_history,
            stock_prices=stock_df,
            direction=stock_direction,
            min_probability=min_probability,
            hold_days=hold_days,
            earliest_date=simulation_date,
        )
        
        if "error" not in backtest_result:
            print(f"\n   📊 Backtest (threshold: {min_probability:.0%}):")
            print(f"      Entry: {backtest_result['entry_date']} @ ${backtest_result['entry_price']:.2f} (prob: {backtest_result['entry_probability']:.1f}%)")
            print(f"      Exit:  {backtest_result['exit_date']} @ ${backtest_result['exit_price']:.2f} (prob: {backtest_result['exit_probability']:.1f}%)")
            print(f"      Position: {backtest_result['position']}")
            print(f"      Return: {backtest_result['return_pct']:+.2f}%")
            print(f"      Holding: {backtest_result['holding_days']} days")
        else:
            print(f"   ⚠ Backtest: {backtest_result['error']}")
        
        stock_results.append({
            "ticker": ticker,
            "direction": stock_direction,
            "position": position_type,
            "confidence": validated_confidence,
            "original_confidence": original_confidence,
            "reasoning": mapping.get("reasoning", ""),
            "correlation": correlation_result,
            "backtest": backtest_result,
            "hold_days": hold_days,
            "entry_signal_date": entry_date,  # From batch validation
            "validation_result": mapping.get("validation_result"),
            "company_status": mapping.get("company_status"),
            "news_event_insight": mapping.get("news_event_insight"),
        })
    
    results["stock_results"] = stock_results
    
    # Step 5: Summary
    print(f"\n{'='*60}")
    print(f"📋 Summary")
    print(f"{'='*60}")
    
    successful = [s for s in stock_results if "correlation" in s and "error" not in s.get("correlation", {})]
    
    if successful:
        # Calculate average correlation
        correlations = [s["correlation"]["correlation"] for s in successful]
        avg_corr = sum(correlations) / len(correlations)
        
        # Count direction matches
        matches = sum(1 for s in successful if s["correlation"].get("direction_match", False))
        
        # Calculate total return from backtests
        returns = [s["backtest"]["return_pct"] for s in successful if "return_pct" in s.get("backtest", {})]
        avg_return = sum(returns) / len(returns) if returns else 0
        
        print(f"\nStocks analyzed: {len(successful)}/{len(stock_mappings)}")
        print(f"Average correlation: {avg_corr:+.4f}")
        print(f"Direction matches: {matches}/{len(successful)}")
        
        if returns:
            print(f"Average backtest return: {avg_return:+.2f}%")
        
        # Verdict
        if avg_corr > 0.3 and matches >= len(successful) / 2:
            print(f"\n✅ Strategy Validated: Polymarket signals show meaningful correlation")
        elif avg_corr > 0.1:
            print(f"\n⚠ Weak Signal: Some correlation exists but may not be reliable")
        else:
            print(f"\n❌ No Signal: Polymarket probabilities don't correlate with stock movements")
        
        results["summary"] = {
            "stocks_analyzed": len(successful),
            "average_correlation": round(avg_corr, 4),
            "direction_matches": matches,
            "average_return": round(avg_return, 2) if returns else None,
        }
    else:
        print(f"\n❌ No successful analyses")
        results["summary"] = {"error": "No successful analyses"}
    
    return results


def run_historical_backtest(
    start_date: str,
    max_events: int = 5,
    min_volume: float = 50000,
    min_liquidity: float = 10000,
    categories: Optional[List[str]] = None,
    tickers: Optional[List[str]] = None,
    direction: str = "bullish",
    min_probability: float = 0.25,
    max_probability: float = 0.75,
    verbose: bool = False,
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    long_hold_days: int = 7,
    short_hold_days: int = 0,
    min_score: float = 30.0,
    min_relevance: str = "medium",
    long_only: bool = False,
    discovery_only: bool = False,
    min_conviction: float = 0.0,
) -> Dict[str, Any]:
    """
    Run historical backtest simulating live mode at a specific date.

    This is the new architecture that simulates what would have happened
    if you ran the app on a historical date. It:
    1. Fetches events that were ACTIVE on start_date
    2. Scores and ranks events (algorithmic)
    3. Conviction-based probability check (replaces simple band filter)
    4. AI stock relevance check (filters out irrelevant events)
    5. For each relevant event:
       a. Discovers affected stocks (LLM)
       b. Validates stocks with news (as of start date)
       c. Runs backtest
    6. Aggregates results

    Args:
        start_date: Simulate running the app on this date (ISO format: "2024-01-01")
        max_events: Maximum events to analyze (default: 5)
        min_volume: Minimum volume in USD (default: 50000)
        min_liquidity: Minimum liquidity (default: 10000)
        categories: Filter by category list
        tickers: Optional list of tickers (skip stock discovery if provided)
        direction: Direction for manual tickers
        min_probability: Minimum probability for band filter (default: 0.25)
        max_probability: Maximum probability for band filter (default: 0.75)
        verbose: Print detailed output
        model_name: LLM model name
        model_provider: LLM provider
        long_hold_days: Days to hold long positions after event resolution
        short_hold_days: Days to hold short positions after event resolution
        min_score: Minimum EventScorer score to analyze (default: 50.0)
        min_relevance: Minimum relevance level ("high", "medium", "low")
        long_only: Disable short selling - filter out bearish stocks (--no-short flag)
        min_conviction: Minimum conviction score to pass (default: 0 = no hard filter)

    Returns:
        Dict with aggregated backtest results
    """
    print(f"\n{'='*60}")
    print(f"📊 Historical Backtest Simulation")
    print(f"{'='*60}")
    print(f"   Simulation Date: {start_date}")
    print(f"   Min Volume: ${min_volume:,.0f}")
    print(f"   Min Liquidity: ${min_liquidity:,.0f}")
    print(f"   Max Events: {max_events}")
    if categories:
        print(f"   Categories: {', '.join(categories)}")

    # Progress tracking
    _completed_phases: set = set()
    _phase_summary: dict = {}

    print_progress(_completed_phases, current="discovery")

    cache = get_polymarket_cache()
    scorer = EventScorer()

    results = {
        "timestamp": datetime.now().isoformat(),
        "simulation_date": start_date,
        "parameters": {
            "min_volume": min_volume,
            "min_liquidity": min_liquidity,
            "max_events": max_events,
            "min_probability": min_probability,
            "max_probability": max_probability,
            "min_score": min_score,
            "min_relevance": min_relevance,
        },
        "phases": {},
        "event_results": [],
        "summary": {},
    }
    
    # ==================== Phase 1: Event Discovery ====================
    print(f"\n🔍 Phase 1: Event Discovery")
    print(f"   Fetching events active on {start_date}...")
    
    try:
        events = get_events_active_on_date(
            as_of_date=start_date,
            min_volume=min_volume,
            min_liquidity=min_liquidity,
            categories=categories,
            cache=cache,
            verbose=verbose,
        )
    except Exception as e:
        print(f"❌ Error fetching events: {e}")
        results["error"] = str(e)
        return results
    
    if not events:
        print(f"❌ No events found active on {start_date}")
        print(f"   💡 Tip: Try lowering --min-volume or --min-liquidity filters")
        print(f"   💡 Tip: Use --verbose to see detailed API response info")
        results["error"] = "No events found"
        return results
    
    print(f"   Found {len(events)} events matching criteria")
    results["phases"]["discovery"] = {
        "events_found": len(events),
    }

    _completed_phases.add("discovery")
    _phase_summary["discovery"] = f"— {len(events)} events found"
    print_progress(_completed_phases, current="scoring", summary=_phase_summary)

    # ==================== Phase 1b: Algorithmic Scoring ====================
    print(f"   Scoring events...")
    
    scored_events = scorer.rank_events(
        events,
        min_score=min_score,
        limit=max_events * 3,  # Keep more for relevance filtering
    )
    
    print(f"   Events with score > {min_score}: {len(scored_events.events)}")
    
    # Verbose logging for scoring phase
    if verbose:
        print(f"\n   [DEBUG] Scoring breakdown for all {len(events)} events:")
        # Create local event map for debugging
        debug_event_map = {e.id: e for e in events}
        # Score all events (not just those above threshold) for debugging
        all_scored = scorer.rank_events(events, min_score=0.0, limit=len(events))
        for i, es in enumerate(all_scored.events[:10]):  # Show top 10
            event = debug_event_map.get(es.event_id)
            title = event.title[:40] if event and event.title else es.event_id[:30]
            slug = event.slug if event and event.slug else None
            url = f"https://polymarket.com/event/{slug}" if slug else "N/A"
            print(f"   [DEBUG]   {i+1}. Score: {es.total_score:.1f} - '{title}...'")
            print(f"   [DEBUG]      URL: {url}")
            print(f"   [DEBUG]      Volume: {es.component_scores.get('volume', 0):.1f}, Liquidity: {es.component_scores.get('liquidity', 0):.1f}, "
                  f"Recency: {es.component_scores.get('time_horizon', 0):.1f}, Category: {es.component_scores.get('category', 0):.1f}")
            if es.total_score < min_score:
                print(f"   [DEBUG]      ⚠️ Below threshold ({min_score})")
        
        # Show how many events are below threshold
        below_threshold = sum(1 for es in all_scored.events if es.total_score < min_score)
        print(f"\n   [DEBUG] Events below threshold ({min_score}): {below_threshold}/{len(all_scored.events)}")
        if below_threshold > 0 and min_score > 0:
            print(f"   [DEBUG] 💡 Tip: Use --min-score 0 to see all events regardless of score")
    
    results["phases"]["scoring"] = {
        "events_above_threshold": len(scored_events.events),
        "min_score": min_score,
    }
    
    if not scored_events.events:
        print(f"❌ No events above score threshold")
        results["error"] = "No events above score threshold"
        return results
    
    # Map scored events back to full event objects
    event_map = {e.id: e for e in events}
    scored_event_list = [
        (event_map[es.event_id], es)
        for es in scored_events.events
        if es.event_id in event_map
    ]
    
    _completed_phases.add("scoring")
    _phase_summary["scoring"] = f"— {len(scored_events.events)} above threshold"
    print_progress(_completed_phases, current="conviction", summary=_phase_summary)

    # ==================== Phase 1c: Conviction-Based Probability Check ====================
    # Replaces simple band check with conviction scoring.
    # High-conviction events outside the old band can pass via override.
    # Near-expiry or data-poor events get filtered.
    print(f"📊 Conviction-Based Probability Check")
    print(f"   Band: [{min_probability:.0%}-{max_probability:.0%}] | Min conviction: {min_conviction:.0f}")

    entry_filtered_events = []
    entry_check_stats = {
        "total_checked": len(scored_event_list),
        "passed": 0,
        "passed_in_band": 0,
        "passed_high_conviction_override": 0,
        "filtered_outside_band": 0,
        "filtered_skip": 0,
        "filtered_low_conviction": 0,
        "filtered_no_flow": 0,
        "no_price_history": 0,
    }

    for event, event_score in scored_event_list:
        # Fetch price history for probability check
        try:
            price_history = get_price_history_for_event(
                event=event,
                interval="max",
                fidelity=1440,  # Daily data
                cache=cache,
            )
        except Exception as e:
            if verbose:
                print(f"   [DEBUG] Error fetching price history for {event.id}: {e}")
            entry_check_stats["no_price_history"] += 1
            continue

        if not price_history or not price_history.history:
            entry_check_stats["no_price_history"] += 1
            event_url = f"https://polymarket.com/event/{event.slug}" if event.slug else ""
            print(f"   ❌ Prob@{start_date}: N/A (no data near date): {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            continue

        # Get probability at the simulation start date
        prob_at_date = get_probability_at_date(price_history, start_date)

        event_url = f"https://polymarket.com/event/{event.slug}" if event.slug else ""

        if prob_at_date is None:
            entry_check_stats["no_price_history"] += 1
            ph_start = price_history.history[0].datetime.strftime("%Y-%m-%d")
            ph_end = price_history.history[-1].datetime.strftime("%Y-%m-%d")
            print(f"   ❌ Prob@{start_date}: N/A (no data near date, history: {ph_start} to {ph_end}): {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            continue

        # Compute conviction score
        conviction = compute_probability_conviction(price_history, event, start_date)

        # Fetch outcome landscape for multi-outcome (neg-risk) events
        landscape = None
        if event.is_multi_outcome:
            try:
                landscape = get_outcome_landscape(
                    event,
                    top_n=7,
                    analysis_date=start_date,
                    cache=cache,
                )
                if landscape:
                    # Use landscape-based conviction for neg-risk events
                    landscape_conviction = compute_landscape_conviction(landscape, event, start_date)
                    if landscape_conviction is not None:
                        conviction = landscape_conviction
            except Exception as e:
                if verbose:
                    print(f"   [DEBUG] Error fetching landscape for {event.id}: {e}")

        if conviction is None or conviction.pick_strategy == "skip":
            entry_check_stats["filtered_skip"] += 1
            skip_reason = conviction.pick_strategy_reasoning if conviction else "no conviction data"
            print(f"   ❌ Prob@{start_date}: {prob_at_date:.1%} [conviction=N/A, skip]: {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            if landscape:
                print_landscape_table(landscape, indent="      ")
            else:
                print_binary_event_table(price_history, event, analysis_date=start_date, indent="      ")
            continue

        # Apply min_conviction hard filter if set
        if min_conviction > 0 and conviction.conviction_score < min_conviction:
            entry_check_stats["filtered_low_conviction"] += 1
            print(f"   ❌ Prob@{start_date}: {prob_at_date:.1%} [conviction={conviction.conviction_score:.0f}, below min {min_conviction:.0f}]: {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            if landscape:
                print_landscape_table(landscape, indent="      ")
            else:
                print_binary_event_table(price_history, event, analysis_date=start_date, indent="      ")
            continue

        # Filter DISTRIBUTED multi-outcome events with no probability flow
        # CONTESTED or better: always accept
        # DISTRIBUTED with flow (fading/gaining outcomes): accept — the trend is the signal
        # DISTRIBUTED with no flow: skip — no outcome signal AND no trend
        if landscape and landscape.concentration == "distributed":
            has_flow = bool(landscape.fading_outcomes or landscape.gaining_outcomes)
            if not has_flow:
                entry_check_stats["filtered_no_flow"] += 1
                print(f"   ❌ Prob@{start_date}: {prob_at_date:.1%} [distributed, no flow]: {event.title[:50]}")
                if event_url:
                    print(f"      {event_url}")
                print_landscape_table(landscape, indent="      ")
                continue

        in_band = min_probability <= prob_at_date <= max_probability

        # HIGH CONVICTION OVERRIDE: Allow events outside the band
        # if market has sustained a clear direction
        high_conviction = (
            conviction.conviction_score >= 65
            and conviction.sustained_days >= 7
            and conviction.distance_from_uncertainty >= 0.25
            and not conviction.near_expiry
        )

        if in_band or high_conviction:
            entry_check_stats["passed"] += 1
            entry_filtered_events.append((event, event_score, price_history, start_date, prob_at_date, conviction, landscape))

            override_tag = " OVERRIDE" if not in_band and high_conviction else ""
            if not in_band and high_conviction:
                entry_check_stats["passed_high_conviction_override"] += 1
            else:
                entry_check_stats["passed_in_band"] += 1

            print(f"   ✅ Prob@{start_date}: {prob_at_date:.1%} [conviction={conviction.conviction_score:.0f}, sustained {conviction.sustained_days}d, {conviction.pick_strategy}]{override_tag}: {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            if landscape:
                print_landscape_table(landscape, indent="      ")
            else:
                print_binary_event_table(price_history, event, analysis_date=start_date, indent="      ")
        else:
            entry_check_stats["filtered_outside_band"] += 1
            print(f"   ❌ Prob@{start_date}: {prob_at_date:.1%} [conviction={conviction.conviction_score:.0f}, sustained {conviction.sustained_days}d, {conviction.pick_strategy}]: {event.title[:50]}")
            if event_url:
                print(f"      {event_url}")
            if landscape:
                print_landscape_table(landscape, indent="      ")
            else:
                print_binary_event_table(price_history, event, analysis_date=start_date, indent="      ")

    print(f"   Passed: {entry_check_stats['passed']}/{entry_check_stats['total_checked']}")
    print(f"     In band: {entry_check_stats['passed_in_band']}")
    print(f"     High conviction override: {entry_check_stats['passed_high_conviction_override']}")
    print(f"   Filtered (outside band, low conviction): {entry_check_stats['filtered_outside_band']}")
    print(f"   Filtered (skip/near-expiry): {entry_check_stats['filtered_skip']}")
    if entry_check_stats['filtered_low_conviction'] > 0:
        print(f"   Filtered (below min conviction {min_conviction:.0f}): {entry_check_stats['filtered_low_conviction']}")
    if entry_check_stats['filtered_no_flow'] > 0:
        print(f"   Filtered (distributed, no flow): {entry_check_stats['filtered_no_flow']}")
    print(f"   Filtered (no data): {entry_check_stats['no_price_history']}")

    results["phases"]["entry_signal_check"] = entry_check_stats

    if not entry_filtered_events:
        print(f"❌ No events passed conviction check on {start_date}")
        print(f"   💡 Tip: Try widening --min-probability / --max-probability band")
        results["error"] = "No events passed conviction check"
        return results
    
    _completed_phases.add("conviction")
    _phase_summary["conviction"] = f"— {entry_check_stats['passed']}/{entry_check_stats['total_checked']} passed"
    print_progress(_completed_phases, current="dedup", summary=_phase_summary)

    # ==================== Phase 1d: Deduplication Check ====================
    print(f"🔍 Deduplication Check")
    print(f"   Checking for duplicate/similar events...")
    
    # Initialize event portfolio for deduplication
    portfolio = EventPortfolio()
    
    deduplicated_events = []
    dedup_stats = {
        "total_checked": len(entry_filtered_events),
        "passed": 0,
        "filtered_duplicate": 0,
    }
    
    for event, event_score, price_history, entry_date, entry_prob, conviction, landscape in entry_filtered_events:
        # Check for duplicates
        dedup_result = check_duplicate(
            event=event,
            portfolio=portfolio,
            use_embeddings=True,  # Use semantic similarity
            use_llm=False,  # Don't use LLM for bulk filtering (too expensive)
            verbose=verbose,
        )

        if dedup_result.is_duplicate:
            dedup_stats["filtered_duplicate"] += 1
            if verbose:
                print(f"   ❌ Duplicate ({dedup_result.method}): {event.title[:40]}...")
                if dedup_result.matching_event_title:
                    print(f"      └─ Matches: {dedup_result.matching_event_title[:40]}...")
            continue

        # Not a duplicate - add to portfolio and keep
        dedup_stats["passed"] += 1
        deduplicated_events.append((event, event_score, price_history, entry_date, entry_prob, conviction, landscape))
        
        # Add to portfolio for future dedup checks
        exposure = EventExposure(
            event_id=event.id,
            event_title=event.title,
            event_slug=event.slug,
            entry_date=entry_date,
            entry_probability=entry_prob,
            category=event.category,
            end_date=event.end_date,
        )
        portfolio.add_exposure(exposure)
        
        if verbose:
            print(f"   ✅ Unique event: {event.title[:40]}...")
    
    print(f"   Unique events: {dedup_stats['passed']}/{dedup_stats['total_checked']}")
    print(f"   Filtered duplicates: {dedup_stats['filtered_duplicate']}")
    
    results["phases"]["deduplication"] = dedup_stats
    
    if not deduplicated_events:
        print(f"❌ All events were duplicates")
        results["error"] = "All events were duplicates"
        return results
    
    # Update scored_event_list for next phase (without price history for compatibility)
    scored_event_list = [(event, event_score) for event, event_score, _, _, _, _, _ in deduplicated_events]

    # Store price histories, conviction, and landscape for later use
    price_history_cache = {
        event.id: (price_history, entry_date, entry_prob, conviction, landscape)
        for event, _, price_history, entry_date, entry_prob, conviction, landscape in deduplicated_events
    }

    _completed_phases.add("dedup")
    _phase_summary["dedup"] = f"— {dedup_stats['passed']} unique events"

    # ==================== Discovery-Only Summary ====================
    if discovery_only:
        print_progress(_completed_phases, summary=_phase_summary)
        print(f"{'='*60}")
        print(f"  Discovery Pipeline Summary (--discovery-only)")
        print(f"{'='*60}")
        print(f"  Simulation date:       {start_date}")
        print(f"  Prob band:             [{min_probability:.0%}-{max_probability:.0%}]")
        print(f"  Events from API:       {len(events)}")
        print(f"  After scoring (>{min_score}):  {len(scored_events.events)}")
        print(f"  In probability band:   {entry_check_stats['passed_in_band']}")
        print(f"  After dedup:           {dedup_stats['passed']}")
        print(f"\n  Qualified events:")
        for i, (event, event_score, ph, edate, eprob, conv, lscape) in enumerate(deduplicated_events, 1):
            title = (event.title or "?")[:55]
            event_url = f"https://polymarket.com/event/{event.slug}" if event.slug else ""
            conv_str = f"conviction={conv.conviction_score:.0f}, {conv.pick_strategy}" if conv else "conviction=N/A"
            print(f"  {i:3d}. {title}")
            print(f"       score={event_score.total_score:.1f}  "
                  f"prob@{edate}={eprob:.1%}  "
                  f"{conv_str}  "
                  f"vol=${(event.volume or 0):,.0f}")
            if event_url:
                print(f"       {event_url}")
        print(f"\n  Next steps: remove --discovery-only to run LLM relevance + stock mapping + backtest")
        results["discovery_only"] = True
        results["qualified_events"] = [
            {
                "event_id": ev.id,
                "title": ev.title,
                "score": es.total_score,
                "prob_date": ed,
                "prob_at_date": ep,
                "conviction_score": conv.conviction_score if conv else None,
                "pick_strategy": conv.pick_strategy if conv else None,
                "volume": ev.volume,
                "category": ev.category,
            }
            for ev, es, _, ed, ep, conv, _ in deduplicated_events
        ]
        return results

    # ==================== Phase 2: AI Stock Relevance Check ====================
    print_progress(_completed_phases, current="relevance", summary=_phase_summary)
    print(f"🤖 AI Stock Relevance Check")
    print(f"   Checking {len(scored_event_list)} events for US stock market relevance...")
    
    # If tickers are provided, skip relevance check
    if tickers:
        print(f"   ⏭️ Skipping relevance check (tickers provided: {', '.join(tickers)})")
        relevant_events = scored_event_list[:max_events]
        results["phases"]["relevance"] = {
            "skipped": True,
            "reason": "tickers_provided",
        }
    else:
        # Run AI relevance check
        relevant_events = []
        relevance_results = []
        
        for event, event_score in scored_event_list:
            relevance = assess_stock_relevance(
                event=event,
                model_name=model_name,
                model_provider=model_provider,
            )
            
            # Log the result
            relevance_emoji = {
                "high": "✅",
                "medium": "⚠️",
                "low": "❌",
                "none": "❌",
            }.get(relevance.relevance, "❓")
            
            title_preview = (event.title or "Unknown")[:50]
            if len(event.title or "") > 50:
                title_preview += "..."
            
            print(f"   {relevance_emoji} {relevance.relevance.upper()}: {title_preview}")
            if event.slug:
                print(f"      └─ https://polymarket.com/event/{event.slug}")
            if relevance.potential_sectors:
                sectors_str = ", ".join(relevance.potential_sectors[:5])
                print(f"      └─ Sectors: {sectors_str}")
            
            relevance_results.append({
                "event_id": event.id,
                "event_title": event.title,
                "relevance": relevance.relevance,
                "reasoning": relevance.reasoning,
                "sectors": relevance.potential_sectors,
                "confidence": relevance.confidence,
            })
            
            # Filter by minimum relevance
            relevance_order = {"high": 3, "medium": 2, "low": 1, "none": 0}
            min_level = relevance_order.get(min_relevance, 2)
            event_level = relevance_order.get(relevance.relevance, 0)
            
            if event_level >= min_level:
                relevant_events.append((event, event_score, relevance))
            
            if len(relevant_events) >= max_events:
                break
        
        print(f"\n   Stock-relevant events: {len(relevant_events)}")
        results["phases"]["relevance"] = {
            "events_checked": len(relevance_results),
            "events_relevant": len(relevant_events),
            "min_relevance": min_relevance,
            "details": relevance_results,
        }
    
    if not relevant_events:
        print(f"❌ No stock-relevant events found")
        results["error"] = "No stock-relevant events"
        return results
    
    # ==================== Phase 3: Stock Discovery & Backtest ====================
    _completed_phases.add("relevance")
    _phase_summary["relevance"] = f"— {len(relevant_events)} relevant"
    print_progress(_completed_phases, current="backtest", summary=_phase_summary)
    print(f"📈 Stock Discovery & Backtest")
    
    all_event_results = []
    aggregate_metrics = {
        "total_events": len(relevant_events),
        "total_stocks": 0,
        "total_return": 0.0,
        "winning_trades": 0,
        "losing_trades": 0,
    }
    
    for i, event_data in enumerate(relevant_events, 1):
        if tickers:
            event, event_score = event_data
            relevance = None
        else:
            event, event_score, relevance = event_data
        
        # Get cached entry date info, conviction, and landscape
        cached_entry_info = price_history_cache.get(event.id)
        entry_date_cached = cached_entry_info[1] if cached_entry_info else None
        entry_prob_cached = cached_entry_info[2] if cached_entry_info else None
        conviction_cached = cached_entry_info[3] if cached_entry_info and len(cached_entry_info) > 3 else None
        landscape_cached = cached_entry_info[4] if cached_entry_info and len(cached_entry_info) > 4 else None
        
        event_url = f"https://polymarket.com/event/{event.slug}" if event.slug else ""
        print(f"\n{'='*60}")
        print(f"📊 Event {i}/{len(relevant_events)}: {event.title}")
        if event_url:
            print(f"   {event_url}")
        print(f"   Score: {event_score.total_score:.1f}")
        if relevance:
            print(f"   Relevance: {relevance.relevance} ({relevance.confidence}% confidence)")
        if entry_date_cached:
            print(f"   Entry Signal: {entry_date_cached} ({entry_prob_cached:.1%})")
        if conviction_cached:
            print(f"   Conviction: {conviction_cached.conviction_score:.0f}/100 | Strategy: {conviction_cached.pick_strategy}")
        if landscape_cached:
            print_landscape_table(landscape_cached, indent="   ")
        print(f"{'='*60}")
        
        # Run backtest for this event
        try:
            if tickers:
                # Use provided tickers
                result = run_backtest(
                    event_slug=event.slug,
                    tickers=tickers,
                    direction=direction,
                    min_probability=min_probability,
                    verbose=verbose,
                    use_llm=False,  # Don't discover stocks
                    model_name=model_name,
                    model_provider=model_provider,
                    long_hold_days=long_hold_days,
                    short_hold_days=short_hold_days,
                    long_only=long_only,
                    simulation_date=start_date,
                    conviction=conviction_cached,
                    landscape=landscape_cached,
                )
            else:
                # Use LLM to discover stocks
                result = run_backtest(
                    event_slug=event.slug,
                    tickers=None,
                    direction=direction,
                    min_probability=min_probability,
                    verbose=verbose,
                    use_llm=True,
                    model_name=model_name,
                    model_provider=model_provider,
                    long_hold_days=long_hold_days,
                    short_hold_days=short_hold_days,
                    long_only=long_only,
                    simulation_date=start_date,
                    conviction=conviction_cached,
                    landscape=landscape_cached,
                )
            
            # Add event metadata
            result["event_score"] = event_score.total_score
            if relevance:
                result["relevance"] = relevance.relevance
                result["relevance_sectors"] = relevance.potential_sectors
            
            # Add cached entry signal info
            if entry_date_cached:
                result["entry_signal_date"] = entry_date_cached
                result["entry_signal_probability"] = entry_prob_cached
            
            # Get actual outcome if event is resolved
            outcome = get_event_outcome(event)
            if outcome:
                result["actual_outcome"] = outcome
            
            # Aggregate metrics
            if "stock_results" in result:
                for stock_result in result["stock_results"]:
                    aggregate_metrics["total_stocks"] += 1
                    if "backtest" in stock_result and "return_pct" in stock_result["backtest"]:
                        return_pct = stock_result["backtest"]["return_pct"]
                        aggregate_metrics["total_return"] += return_pct
                        
                        if return_pct > 0:
                            aggregate_metrics["winning_trades"] += 1
                        else:
                            aggregate_metrics["losing_trades"] += 1
            
            all_event_results.append(result)
            
        except Exception as e:
            print(f"   ⚠ Error backtesting event: {e}")
            all_event_results.append({
                "event_slug": event.slug,
                "event_title": event.title,
                "event_score": event_score.total_score,
                "error": str(e),
            })
    
    results["event_results"] = all_event_results

    _completed_phases.add("backtest")
    total_trades = aggregate_metrics["winning_trades"] + aggregate_metrics["losing_trades"]
    _phase_summary["backtest"] = f"— {aggregate_metrics['total_stocks']} stocks, {total_trades} trades"
    print_progress(_completed_phases, summary=_phase_summary)

    # ==================== Summary ====================
    total_trades = aggregate_metrics["winning_trades"] + aggregate_metrics["losing_trades"]
    if total_trades > 0:
        aggregate_metrics["win_rate"] = round(
            aggregate_metrics["winning_trades"] / total_trades * 100, 2
        )
        aggregate_metrics["avg_return"] = round(
            aggregate_metrics["total_return"] / total_trades, 2
        )
    else:
        aggregate_metrics["win_rate"] = 0.0
        aggregate_metrics["avg_return"] = 0.0
    
    results["summary"] = aggregate_metrics
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"📋 Historical Backtest Summary")
    print(f"{'='*60}")
    print(f"\nSimulation Date: {start_date}")
    print(f"Events Analyzed: {aggregate_metrics['total_events']}")
    print(f"Stocks Traded: {aggregate_metrics['total_stocks']}")
    print(f"\nTrading Performance:")
    print(f"   Win rate: {aggregate_metrics['win_rate']:.1f}%")
    print(f"   Total return: {aggregate_metrics['total_return']:+.2f}%")
    print(f"   Avg return per trade: {aggregate_metrics['avg_return']:+.2f}%")
    
    # Print filtering pipeline stats
    print(f"\n📊 Filtering Pipeline Stats:")
    if "entry_signal_check" in results["phases"]:
        esc = results["phases"]["entry_signal_check"]
        passed = esc.get('passed', esc.get('in_band', 0))
        overrides = esc.get('passed_high_conviction_override', 0)
        filtered_out = esc.get('filtered_outside_band', 0) + esc.get('filtered_skip', 0) + esc.get('filtered_low_conviction', 0)
        print(f"   Conviction Check: {passed}/{esc['total_checked']} passed")
        if overrides > 0:
            print(f"      └─ {overrides} high-conviction overrides (outside band but sustained)")
        print(f"      └─ Saved ~{filtered_out} LLM calls (filtered)")
    if "deduplication" in results["phases"]:
        dd = results["phases"]["deduplication"]
        print(f"   Deduplication: {dd['passed']}/{dd['total_checked']} unique")
        print(f"      └─ Saved ~{dd['filtered_duplicate']} LLM calls (duplicates)")
    
    # Calculate total LLM calls saved
    total_filtered = 0
    if "entry_signal_check" in results["phases"]:
        esc2 = results["phases"]["entry_signal_check"]
        total_filtered += esc2.get("filtered_outside_band", esc2.get("outside_band", 0))
        total_filtered += esc2.get("filtered_skip", 0)
        total_filtered += esc2.get("filtered_low_conviction", 0)
        total_filtered += esc2.get("filtered_no_flow", 0)
        total_filtered += esc2.get("no_price_history", 0)
    if "deduplication" in results["phases"]:
        total_filtered += results["phases"]["deduplication"]["filtered_duplicate"]
    
    if total_filtered > 0:
        # Each filtered event saves ~2-3 LLM calls (relevance check + stock discovery + validation)
        estimated_savings = total_filtered * 2.5
        print(f"\n   💰 Estimated LLM calls saved: ~{estimated_savings:.0f}")
    
    return results


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Backtest Polymarket event correlations with stock prices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backtest a single event by slug
  poetry run python -m src.backtesting.polymarket_cli --event-slug "presidential-election-winner-2024"
  poetry run python -m src.backtesting.polymarket_cli --event-slug "us-x-venezuela-military-engagement-by" --verbose
  poetry run python -m src.backtesting.polymarket_cli --event-slug "presidential-election-winner-2024" --tickers DJT XOM

  # Historical backtest - simulate running the app on a specific date
  poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --max-events 5
  poetry run python -m src.backtesting.polymarket_cli --start-date 2024-06-01 --min-volume 50000 --verbose
  poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --tickers DJT XOM --direction bullish
        """
    )
    
    # Event selection (mutually exclusive)
    event_group = parser.add_mutually_exclusive_group(required=True)
    event_group.add_argument(
        "--event-slug",
        help="The Polymarket event slug (from the URL, e.g., 'presidential-election-winner-2024')"
    )
    event_group.add_argument(
        "--start-date",
        type=str,
        help="Simulate running the app on this date (ISO format: 2024-01-01). "
             "Fetches events that were active on this date and runs full discovery + backtest."
    )
    
    # Historical backtest filters
    parser.add_argument(
        "--min-volume",
        type=float,
        default=50000,
        help="Minimum event volume (default: 50000)"
    )
    
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=10000,
        help="Minimum event liquidity (default: 10000)"
    )
    
    parser.add_argument(
        "--category",
        type=str,
        help="Filter events by category (e.g., 'politics', 'crypto')"
    )
    
    parser.add_argument(
        "--max-events",
        type=int,
        default=5,
        help="Maximum number of events to analyze (default: 5)"
    )
    
    parser.add_argument(
        "--min-score",
        type=float,
        default=30.0,
        help="Minimum EventScorer score to analyze (default: 30.0). Use 0 to see all events."
    )
    
    parser.add_argument(
        "--min-relevance",
        choices=["high", "medium", "low"],
        default="medium",
        help="Minimum stock relevance level (default: medium)"
    )
    
    # Stock selection
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific stock tickers to analyze (optional, otherwise AI discovers them)"
    )
    
    parser.add_argument(
        "--min-probability",
        type=float,
        default=0.25,
        help="Minimum probability for band filter (default: 0.25). Events below this are too uncertain."
    )

    parser.add_argument(
        "--max-probability",
        type=float,
        default=0.75,
        help="Maximum probability for band filter (default: 0.75). Events above this are already priced in."
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    
    parser.add_argument(
        "--direction",
        choices=["bullish", "bearish"],
        default="bullish",
        help="Direction for manual tickers: 'bullish' (long) or 'bearish' (short). Default: bullish"
    )
    
    parser.add_argument(
        "--long-hold-days",
        type=int,
        default=7,
        help="Days to hold long positions after event resolution (default: 7)"
    )
    
    parser.add_argument(
        "--short-hold-days",
        type=int,
        default=0,
        help="Days to hold short positions after event resolution (default: 0, exit immediately)"
    )
    
    parser.add_argument(
        "--no-short",
        action="store_true",
        default=False,
        help="Disable short selling (long positions only)"
    )
    
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash",
        help="LLM model name for stock discovery (default: gemini-2.0-flash)"
    )
    
    parser.add_argument(
        "--provider",
        default="Google",
        help="LLM provider (default: Google). Options: Google, OpenAI, Anthropic, Groq"
    )
    
    parser.add_argument(
        "--min-conviction",
        type=float,
        default=0.0,
        help="Minimum conviction score to pass (default: 0 = computed but not used as hard filter). "
             "Events below this conviction score are filtered out."
    )

    parser.add_argument(
        "--discovery-only",
        action="store_true",
        default=False,
        help="Run discovery pipeline only (fetch, score, entry signal, dedup) — "
             "skip LLM relevance check, stock discovery, and backtest simulation"
    )

    parser.add_argument(
        "--output",
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    # Determine if we should use LLM (only when no tickers provided)
    use_llm = args.tickers is None
    
    if args.start_date:
        # Run historical backtest - simulate running the app on a specific date
        print(f"\n🕐 Running historical backtest simulation for {args.start_date}")
        
        # Parse categories
        categories = [args.category] if args.category else None
        
        results = run_historical_backtest(
            start_date=args.start_date,
            max_events=args.max_events,
            min_volume=args.min_volume,
            min_liquidity=args.min_liquidity,
            categories=categories,
            tickers=args.tickers,
            direction=args.direction,
            min_probability=args.min_probability,
            max_probability=args.max_probability,
            verbose=args.verbose,
            model_name=args.model,
            model_provider=args.provider,
            long_hold_days=args.long_hold_days,
            short_hold_days=args.short_hold_days,
            min_score=args.min_score,
            min_relevance=args.min_relevance,
            long_only=args.no_short,
            discovery_only=args.discovery_only,
            min_conviction=args.min_conviction,
        )
    else:
        # Run single event backtest by slug
        if use_llm:
            print(f"\n🤖 No tickers provided - AI will discover affected stocks")
        else:
            print(f"\n📈 Using provided tickers with direction: {args.direction}")
        
        results = run_backtest(
            event_slug=args.event_slug,
            tickers=args.tickers,
            direction=args.direction,
            min_probability=args.min_probability,
            verbose=args.verbose,
            use_llm=use_llm,
            model_name=args.model,
            model_provider=args.provider,
            long_hold_days=args.long_hold_days,
            short_hold_days=args.short_hold_days,
            long_only=args.no_short,
        )
    
    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {args.output}")
    
    # Return exit code based on success
    if "error" in results:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
