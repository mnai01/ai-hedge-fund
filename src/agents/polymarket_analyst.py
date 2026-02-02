"""Polymarket Analyst Agent for the AI Hedge Fund.

This agent analyzes Polymarket prediction market events and generates
trading signals for affected stocks. It uses:
- Polymarket API to fetch events and probability changes
- LLM (Gemini with Google Search grounding) to map events to affected stocks
- Persistent cache to track probability changes over time

Follows patterns from src/agents/news_sentiment.py for LLM integration
and src/agents/sentiment.py for agent structure.

BACKTESTING SUPPORT:
When used in backtesting mode, this agent supports point-in-time simulation:
- Uses the `end_date` from state as the cutoff date
- Only considers probability data up to that date (no future data leakage)
- Calculates probability changes based on historical data available at that time
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from typing_extensions import Literal

from src.graph.state import AgentState, show_agent_reasoning
from src.utils.llm import call_llm
from src.utils.progress import progress
from src.tools.polymarket_api import (
    get_active_events,
    get_price_history_for_event,
    get_events_with_probability_changes,
    get_trending_events,
    get_price_history,
    get_event_by_slug,
)
from src.data.polymarket_models import (
    PolymarketEvent,
    EventStockImpact,
    EventStockMapping,
    ProbabilityChange,
    PolymarketAnalysis,
    PriceHistory,
)
from src.data.polymarket_cache import get_polymarket_cache


# ==================== Pydantic Models for LLM Output ====================

class StockImpactAnalysis(BaseModel):
    """LLM output model for analyzing a single stock's impact from an event."""
    
    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL, TSLA)")
    direction: Literal["bullish", "bearish", "neutral"] = Field(
        description="Expected impact direction on the stock"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence score 0-100 for this prediction"
    )
    reasoning: str = Field(
        description="Brief explanation of why this stock is affected"
    )


class EventStockMappingResponse(BaseModel):
    """LLM output model for mapping an event to affected stocks."""
    
    affected_stocks: List[StockImpactAnalysis] = Field(
        default_factory=list,
        description="List of stocks affected by this event"
    )
    event_relevance: Literal["high", "medium", "low"] = Field(
        description="How relevant this event is to stock markets"
    )
    summary: str = Field(
        description="Brief summary of the event's market implications"
    )


class TickerEventRelevance(BaseModel):
    """LLM output model for checking if an event is relevant to a specific ticker."""
    
    is_relevant: bool = Field(
        description="Whether the event is relevant to the ticker"
    )
    direction: Literal["bullish", "bearish", "neutral"] = Field(
        description="Expected impact direction if relevant"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence score 0-100"
    )
    reasoning: str = Field(
        description="Explanation of the relevance and impact"
    )


# ==================== Main Agent Function ====================

def polymarket_analyst_agent(
    state: AgentState,
    agent_id: str = "polymarket_analyst_agent",
) -> Dict[str, Any]:
    """
    Analyzes Polymarket events and generates trading signals for affected stocks.
    
    This agent:
    1. Fetches active events from Polymarket (or uses specified events for backtesting)
    2. Identifies events with significant probability changes
    3. Uses LLM to map events to affected stocks
    4. Generates trading signals for the tickers in the portfolio
    
    BACKTESTING SUPPORT:
    When backtesting, set these in state["metadata"]:
    - polymarket_events: List of event slugs to track (e.g., ["presidential-election-winner-2024"])
    - polymarket_event_mappings: Dict mapping event_id to {ticker: direction} for pre-defined mappings
    
    The agent uses state["data"]["end_date"] as the point-in-time cutoff for probability data.
    
    Args:
        state: The current agent state containing tickers and metadata
        agent_id: Identifier for this agent
    
    Returns:
        Updated state with Polymarket analysis signals
    
    Output format matches other agents:
        state["data"]["analyst_signals"][agent_id] = {
            "AAPL": {
                "signal": "bullish",
                "confidence": 75.5,
                "reasoning": {...}
            },
            ...
        }
    """
    data = state.get("data", {})
    metadata = state.get("metadata", {})
    tickers = data.get("tickers", [])
    
    # Get point-in-time cutoff date for backtesting
    end_date_str = data.get("end_date")
    end_date_ts = None
    if end_date_str:
        try:
            end_date_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
            # Set to end of day
            end_date_ts = int(end_date_dt.timestamp()) + 86400 - 1
        except ValueError:
            pass
    
    # Check for backtesting mode with specific events
    backtest_event_slugs = metadata.get("polymarket_events", [])
    backtest_event_mappings = metadata.get("polymarket_event_mappings", {})
    is_backtest_mode = bool(backtest_event_slugs) or bool(backtest_event_mappings)
    
    # Initialize cache
    cache = get_polymarket_cache()
    
    # Initialize analysis results
    polymarket_analysis = {}
    
    progress.update_status(agent_id, None, "Fetching Polymarket events")
    
    # Fetch events - either specific events for backtesting or active events
    events = []
    if backtest_event_slugs:
        # Backtesting mode: fetch specific events by slug
        for slug in backtest_event_slugs:
            try:
                event = get_event_by_slug(slug, cache=cache)
                if event:
                    events.append(event)
            except Exception as e:
                progress.update_status(agent_id, None, f"Error fetching event {slug}: {e}")
    else:
        # Normal mode: fetch active events
        try:
            events = get_active_events(limit=50, cache=cache)
        except Exception as e:
            progress.update_status(agent_id, None, f"Error fetching events: {e}")
            events = []
    
    if not events:
        # Return neutral signals for all tickers if no events
        for ticker in tickers:
            polymarket_analysis[ticker] = {
                "signal": "neutral",
                "confidence": 0,
                "reasoning": {
                    "error": "No Polymarket events available",
                    "events_analyzed": 0,
                    "mode": "backtest" if is_backtest_mode else "live",
                }
            }
        
        return _finalize_agent_output(state, agent_id, polymarket_analysis)
    
    progress.update_status(agent_id, None, f"Analyzing {len(events)} events")
    
    # Calculate probability changes - with point-in-time support for backtesting
    probability_changes = []
    
    if is_backtest_mode and end_date_ts:
        # Backtesting mode: calculate probability changes using historical data
        probability_changes = _get_point_in_time_probability_changes(
            events=events,
            end_ts=end_date_ts,
            hours=24,
            threshold=0.05,
            cache=cache,
        )
    else:
        # Normal mode: use current probability changes
        try:
            probability_changes = get_events_with_probability_changes(
                events=events,
                hours=24,
                threshold=0.05,
                cache=cache,
            )
        except Exception as e:
            progress.update_status(agent_id, None, f"Error analyzing probability changes: {e}")
            probability_changes = []
    
    # Combine trending events with those having probability changes
    significant_events = _get_significant_events(events, probability_changes)
    
    progress.update_status(
        agent_id, None,
        f"Found {len(significant_events)} significant events"
    )
    
    # Analyze each ticker
    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Analyzing event impacts")
        
        # Check for pre-defined mappings (backtesting mode)
        predefined_mapping = None
        for event_id, mappings in backtest_event_mappings.items():
            if ticker in mappings:
                predefined_mapping = {
                    "event_id": event_id,
                    "direction": mappings[ticker].get("direction", "neutral"),
                    "confidence": mappings[ticker].get("confidence", 70),
                    "reasoning": mappings[ticker].get("reasoning", "Pre-defined mapping for backtesting"),
                }
                break
        
        # Check cache for existing mappings
        cached_mappings = cache.get_mappings_for_ticker(ticker)
        
        # Find relevant events for this ticker
        relevant_events = []
        
        for event, prob_change in significant_events[:10]:  # Limit to top 10 events
            # Check for pre-defined mapping first (backtesting)
            if predefined_mapping and predefined_mapping["event_id"] == event.id:
                relevant_events.append({
                    "event": event,
                    "prob_change": prob_change,
                    "impact": {
                        "direction": predefined_mapping["direction"],
                        "confidence": predefined_mapping["confidence"],
                        "reasoning": predefined_mapping["reasoning"],
                    },
                    "from_cache": False,
                    "from_backtest_mapping": True,
                })
                continue
            
            # Check if we have a cached mapping
            cached = _find_cached_mapping(cached_mappings, event.id)
            
            if cached:
                relevant_events.append({
                    "event": event,
                    "prob_change": prob_change,
                    "impact": cached,
                    "from_cache": True,
                })
            else:
                # Use LLM to determine relevance
                progress.update_status(
                    agent_id, ticker,
                    f"Analyzing event: {event.title[:50]}..."
                )
                
                impact = _analyze_event_relevance_for_ticker(
                    event=event,
                    ticker=ticker,
                    prob_change=prob_change,
                    state=state,
                    agent_id=agent_id,
                )
                
                if impact and impact.is_relevant:
                    # Cache the mapping
                    stock_impact = EventStockImpact(
                        ticker=ticker,
                        direction=impact.direction,
                        confidence=impact.confidence,
                        reasoning=impact.reasoning,
                        sources=[],
                    )
                    cache.set_stock_mapping(event.id, stock_impact)
                    
                    relevant_events.append({
                        "event": event,
                        "prob_change": prob_change,
                        "impact": {
                            "direction": impact.direction,
                            "confidence": impact.confidence,
                            "reasoning": impact.reasoning,
                        },
                        "from_cache": False,
                    })
        
        # Aggregate signals from relevant events
        # Apply probability threshold logic: only generate signals when probability is extreme
        signal, confidence, reasoning = _aggregate_event_signals_with_threshold(
            ticker=ticker,
            relevant_events=relevant_events,
            probability_threshold=0.70,  # Only trade when probability > 70% or < 30%
        )
        
        polymarket_analysis[ticker] = {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
        }
        
        progress.update_status(
            agent_id, ticker, "Done",
            analysis=json.dumps(reasoning, indent=2)
        )
    
    return _finalize_agent_output(state, agent_id, polymarket_analysis)


# ==================== Helper Functions ====================

def _get_significant_events(
    events: List[PolymarketEvent],
    probability_changes: List[ProbabilityChange],
) -> List[tuple]:
    """
    Combine and rank events by significance.
    
    Returns list of (event, probability_change) tuples.
    """
    # Create a map of event_id to probability change
    change_map = {pc.event_id: pc for pc in probability_changes}
    
    significant = []
    
    for event in events:
        prob_change = change_map.get(event.id)
        
        # Calculate significance score
        score = 0
        
        # Volume contributes to significance
        if event.volume:
            score += min(event.volume / 1000000, 10)  # Cap at 10 points
        
        # Probability change contributes significantly
        if prob_change:
            score += abs(prob_change.change) * 100  # Up to 100 points for 100% change
        
        # 24h volume indicates trending
        if event.volume_24hr:
            score += min(event.volume_24hr / 100000, 5)  # Cap at 5 points
        
        significant.append((event, prob_change, score))
    
    # Sort by score descending
    significant.sort(key=lambda x: x[2], reverse=True)
    
    # Return without the score
    return [(e, pc) for e, pc, _ in significant]


def _find_cached_mapping(
    cached_mappings: List[Dict[str, Any]],
    event_id: str,
) -> Optional[Dict[str, Any]]:
    """Find a cached mapping for a specific event."""
    for mapping in cached_mappings:
        if mapping.get("event_id") == event_id:
            return mapping
    return None


def _analyze_event_relevance_for_ticker(
    event: PolymarketEvent,
    ticker: str,
    prob_change: Optional[ProbabilityChange],
    state: AgentState,
    agent_id: str,
) -> Optional[TickerEventRelevance]:
    """
    Use LLM to analyze if an event is relevant to a specific ticker.
    
    Uses Gemini with Google Search grounding for accurate analysis.
    """
    # Build the prompt
    prob_info = ""
    if prob_change:
        prob_info = f"""
Probability Change (last 24h):
- Previous: {prob_change.previous_probability:.1%}
- Current: {prob_change.current_probability:.1%}
- Change: {prob_change.change:+.1%} ({prob_change.direction})
"""
    
    prompt = f"""Analyze whether this Polymarket prediction market event is relevant to the stock {ticker}.

Event Title: {event.title}
Event Description: {event.description or 'No description available'}
Current Probability: {event.probability:.1%} if event.probability else 'Unknown'
Category: {event.category or 'Unknown'}
{prob_info}

Consider:
1. Does this event directly or indirectly affect {ticker}'s business, industry, or market?
2. If the event outcome changes, how would it impact {ticker}'s stock price?
3. Is there a clear causal relationship between this event and {ticker}?

Respond with:
- is_relevant: true/false
- direction: "bullish", "bearish", or "neutral" (if the event probability increasing is good/bad/neutral for the stock)
- confidence: 0-100 (how confident you are in this assessment)
- reasoning: Brief explanation

Be conservative - only mark as relevant if there's a clear connection.
"""
    
    try:
        result = call_llm(
            prompt=prompt,
            pydantic_model=TickerEventRelevance,
            agent_name=agent_id,
            state=state,
            max_retries=2,
        )
        return result
    except Exception as e:
        print(f"Error analyzing event relevance: {e}")
        return None


def _analyze_event_stock_mapping(
    event: PolymarketEvent,
    prob_change: Optional[ProbabilityChange],
    state: AgentState,
    agent_id: str,
) -> Optional[EventStockMappingResponse]:
    """
    Use LLM to identify all stocks affected by an event.
    
    This is an alternative approach that finds all affected stocks at once.
    """
    prob_info = ""
    if prob_change:
        prob_info = f"""
Probability Change (last 24h):
- Previous: {prob_change.previous_probability:.1%}
- Current: {prob_change.current_probability:.1%}
- Change: {prob_change.change:+.1%} ({prob_change.direction})
"""
    
    prompt = f"""Analyze this Polymarket prediction market event and identify US stocks that would be affected by its outcome.

Event Title: {event.title}
Event Description: {event.description or 'No description available'}
Current Probability: {event.probability:.1%} if event.probability else 'Unknown'
Category: {event.category or 'Unknown'}
{prob_info}

Identify stocks that would be directly affected if this event's probability changes.
For each stock, specify:
- ticker: The stock symbol
- direction: "bullish" if probability increase is good for the stock, "bearish" if bad, "neutral" if unclear
- confidence: 0-100 confidence in this assessment
- reasoning: Brief explanation

Only include stocks with clear, direct connections to the event.
Focus on major US-listed stocks.
"""
    
    try:
        result = call_llm(
            prompt=prompt,
            pydantic_model=EventStockMappingResponse,
            agent_name=agent_id,
            state=state,
            max_retries=2,
        )
        return result
    except Exception as e:
        print(f"Error analyzing event stock mapping: {e}")
        return None


def _aggregate_event_signals(
    ticker: str,
    relevant_events: List[Dict[str, Any]],
) -> tuple:
    """
    Aggregate signals from multiple relevant events into a single signal.
    
    Returns (signal, confidence, reasoning) tuple.
    """
    if not relevant_events:
        return "neutral", 0, {
            "events_analyzed": 0,
            "relevant_events": 0,
            "message": "No relevant Polymarket events found for this ticker",
        }
    
    # Weight signals by confidence and probability change magnitude
    bullish_score = 0
    bearish_score = 0
    total_weight = 0
    
    event_details = []
    
    for event_data in relevant_events:
        event = event_data["event"]
        impact = event_data["impact"]
        prob_change = event_data.get("prob_change")
        
        # Get direction and confidence
        direction = impact.get("direction", "neutral")
        confidence = impact.get("confidence", 50)
        
        # Calculate weight based on confidence and probability change
        weight = confidence / 100
        if prob_change:
            weight *= (1 + abs(prob_change.change))  # Boost weight for larger changes
        
        if direction == "bullish":
            bullish_score += weight
        elif direction == "bearish":
            bearish_score += weight
        
        total_weight += weight
        
        # Record event details for reasoning
        event_details.append({
            "event_id": event.id,
            "title": event.title[:100],
            "probability": event.probability,
            "prob_change": prob_change.change if prob_change else None,
            "direction": direction,
            "confidence": confidence,
            "reasoning": impact.get("reasoning", ""),
            "from_cache": event_data.get("from_cache", False),
        })
    
    # Determine overall signal
    if total_weight == 0:
        signal = "neutral"
        confidence = 0
    else:
        bullish_ratio = bullish_score / total_weight
        bearish_ratio = bearish_score / total_weight
        
        if bullish_ratio > bearish_ratio + 0.1:  # Need 10% margin
            signal = "bullish"
            confidence = min(bullish_ratio * 100, 100)
        elif bearish_ratio > bullish_ratio + 0.1:
            signal = "bearish"
            confidence = min(bearish_ratio * 100, 100)
        else:
            signal = "neutral"
            confidence = 50  # Mixed signals
    
    reasoning = {
        "events_analyzed": len(relevant_events),
        "bullish_score": round(bullish_score, 2),
        "bearish_score": round(bearish_score, 2),
        "signal_determination": f"{'Bullish' if signal == 'bullish' else 'Bearish' if signal == 'bearish' else 'Neutral'} based on {len(relevant_events)} relevant events",
        "events": event_details,
    }
    
    return signal, round(confidence, 2), reasoning


def _get_point_in_time_probability_changes(
    events: List[PolymarketEvent],
    end_ts: int,
    hours: int = 24,
    threshold: float = 0.05,
    cache: Optional[Any] = None,
) -> List[ProbabilityChange]:
    """
    Calculate probability changes using historical data up to a specific timestamp.
    
    This is used for backtesting to ensure we only use data available at the
    point-in-time being simulated (no future data leakage).
    
    Args:
        events: List of events to analyze
        end_ts: Unix timestamp for the end of the analysis period (point-in-time cutoff)
        hours: Number of hours to look back for calculating change
        threshold: Minimum change to include in results
        cache: Optional cache for API responses
    
    Returns:
        List of ProbabilityChange objects for events with significant changes
    """
    probability_changes = []
    start_ts = end_ts - (hours * 3600)
    
    for event in events:
        if not event.primary_market or not event.primary_market.primary_token_id:
            continue
        
        token_id = event.primary_market.primary_token_id
        
        try:
            # Fetch historical price data up to the cutoff timestamp
            price_history = get_price_history(
                token_id=token_id,
                interval="max",
                fidelity=60,  # 1-minute intervals
                start_ts=start_ts,
                end_ts=end_ts,
                cache=cache,
            )
            
            if not price_history or len(price_history.history) < 2:
                continue
            
            # Get the earliest and latest probabilities within the window
            earliest_prob = price_history.earliest_probability
            latest_prob = price_history.latest_probability
            
            if earliest_prob is None or latest_prob is None:
                continue
            
            change = latest_prob - earliest_prob
            
            if abs(change) >= threshold:
                direction = "increasing" if change > 0 else "decreasing"
                
                probability_changes.append(ProbabilityChange(
                    event_id=event.id,
                    event_title=event.title,
                    previous_probability=earliest_prob,
                    current_probability=latest_prob,
                    change=change,
                    direction=direction,
                    hours=hours,
                ))
        except Exception as e:
            # Skip events that fail to fetch
            continue
    
    return probability_changes


def _aggregate_event_signals_with_threshold(
    ticker: str,
    relevant_events: List[Dict[str, Any]],
    probability_threshold: float = 0.70,
) -> tuple:
    """
    Aggregate signals from multiple relevant events into a single signal,
    applying probability threshold logic.
    
    Only generates non-neutral signals when event probability is extreme:
    - Probability > threshold (e.g., 70%) = high conviction the event will happen
    - Probability < (1 - threshold) (e.g., 30%) = high conviction the event won't happen
    
    This prevents trading on uncertain events and focuses on high-conviction scenarios.
    
    Args:
        ticker: The stock ticker being analyzed
        relevant_events: List of relevant events with their impacts
        probability_threshold: Threshold for high conviction (default 0.70)
    
    Returns:
        (signal, confidence, reasoning) tuple
    """
    if not relevant_events:
        return "neutral", 0, {
            "events_analyzed": 0,
            "relevant_events": 0,
            "message": "No relevant Polymarket events found for this ticker",
            "probability_threshold": probability_threshold,
        }
    
    # Weight signals by confidence, probability change, AND probability level
    bullish_score = 0
    bearish_score = 0
    total_weight = 0
    
    event_details = []
    threshold_filtered_count = 0
    
    for event_data in relevant_events:
        event = event_data["event"]
        impact = event_data["impact"]
        prob_change = event_data.get("prob_change")
        
        # Get current probability
        current_prob = event.probability if event.probability else 0.5
        
        # Check if probability is at extreme levels (high conviction)
        is_high_conviction = (
            current_prob >= probability_threshold or
            current_prob <= (1 - probability_threshold)
        )
        
        # Get direction and confidence
        direction = impact.get("direction", "neutral")
        confidence = impact.get("confidence", 50)
        
        # Calculate weight based on confidence and probability change
        weight = confidence / 100
        if prob_change:
            weight *= (1 + abs(prob_change.change))  # Boost weight for larger changes
        
        # Apply probability threshold filter
        # If probability is not at extreme levels, reduce the weight significantly
        if not is_high_conviction:
            weight *= 0.1  # Reduce weight by 90% for low-conviction events
            threshold_filtered_count += 1
        else:
            # Boost weight for high-conviction events
            # The further from 50%, the higher the conviction
            conviction_boost = abs(current_prob - 0.5) * 2  # 0 to 1 scale
            weight *= (1 + conviction_boost)
        
        if direction == "bullish":
            bullish_score += weight
        elif direction == "bearish":
            bearish_score += weight
        
        total_weight += weight
        
        # Record event details for reasoning
        event_details.append({
            "event_id": event.id,
            "title": event.title[:100],
            "probability": current_prob,
            "is_high_conviction": is_high_conviction,
            "prob_change": prob_change.change if prob_change else None,
            "direction": direction,
            "confidence": confidence,
            "weight": round(weight, 3),
            "reasoning": impact.get("reasoning", ""),
            "from_cache": event_data.get("from_cache", False),
            "from_backtest_mapping": event_data.get("from_backtest_mapping", False),
        })
    
    # Determine overall signal
    if total_weight == 0:
        signal = "neutral"
        confidence = 0
    else:
        bullish_ratio = bullish_score / total_weight
        bearish_ratio = bearish_score / total_weight
        
        # Require stronger margin for signals (15% instead of 10%)
        if bullish_ratio > bearish_ratio + 0.15:
            signal = "bullish"
            confidence = min(bullish_ratio * 100, 100)
        elif bearish_ratio > bullish_ratio + 0.15:
            signal = "bearish"
            confidence = min(bearish_ratio * 100, 100)
        else:
            signal = "neutral"
            confidence = 50  # Mixed signals
    
    # Count high-conviction events
    high_conviction_events = len(relevant_events) - threshold_filtered_count
    
    reasoning = {
        "events_analyzed": len(relevant_events),
        "high_conviction_events": high_conviction_events,
        "threshold_filtered_events": threshold_filtered_count,
        "probability_threshold": probability_threshold,
        "bullish_score": round(bullish_score, 2),
        "bearish_score": round(bearish_score, 2),
        "signal_determination": (
            f"{'Bullish' if signal == 'bullish' else 'Bearish' if signal == 'bearish' else 'Neutral'} "
            f"based on {high_conviction_events} high-conviction events "
            f"(threshold: {probability_threshold:.0%})"
        ),
        "events": event_details,
    }
    
    return signal, round(confidence, 2), reasoning


def _finalize_agent_output(
    state: AgentState,
    agent_id: str,
    analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Finalize the agent output in the standard format.
    
    Follows the pattern from src/agents/sentiment.py.
    """
    data = state.get("data", {})
    
    # Create the message
    message = HumanMessage(
        content=json.dumps(analysis),
        name=agent_id,
    )
    
    # Show reasoning if flag is set
    if state.get("metadata", {}).get("show_reasoning"):
        show_agent_reasoning(analysis, "Polymarket Analyst Agent")
    
    # Add signals to analyst_signals
    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    state["data"]["analyst_signals"][agent_id] = analysis
    
    progress.update_status(agent_id, None, "Done")
    
    return {
        "messages": [message],
        "data": data,
    }


# ==================== Standalone Analysis Functions ====================

def analyze_events_for_tickers(
    tickers: List[str],
    max_events: int = 20,
    probability_threshold: float = 0.05,
) -> Dict[str, PolymarketAnalysis]:
    """
    Standalone function to analyze Polymarket events for a list of tickers.
    
    This can be used outside of the agent framework for quick analysis.
    
    Args:
        tickers: List of stock tickers to analyze
        max_events: Maximum number of events to consider
        probability_threshold: Minimum probability change to consider significant
    
    Returns:
        Dict mapping tickers to PolymarketAnalysis objects
    """
    cache = get_polymarket_cache()
    
    # Fetch events
    events = get_active_events(limit=max_events, cache=cache)
    
    # Get probability changes
    prob_changes = get_events_with_probability_changes(
        events=events,
        hours=24,
        threshold=probability_threshold,
        cache=cache,
    )
    
    results = {}
    
    for ticker in tickers:
        # Check cached mappings
        mappings = cache.get_mappings_for_ticker(ticker)
        
        if mappings:
            # Aggregate from cached mappings
            bullish = sum(1 for m in mappings if m["direction"] == "bullish")
            bearish = sum(1 for m in mappings if m["direction"] == "bearish")
            
            if bullish > bearish:
                signal = "bullish"
            elif bearish > bullish:
                signal = "bearish"
            else:
                signal = "neutral"
            
            avg_confidence = sum(m["confidence"] for m in mappings) / len(mappings)
            
            results[ticker] = PolymarketAnalysis(
                signal=signal,
                confidence=avg_confidence,
                reasoning={
                    "source": "cached_mappings",
                    "events_count": len(mappings),
                    "bullish_events": bullish,
                    "bearish_events": bearish,
                }
            )
        else:
            results[ticker] = PolymarketAnalysis(
                signal="neutral",
                confidence=0,
                reasoning={
                    "source": "no_mappings",
                    "message": "No cached event mappings for this ticker",
                }
            )
    
    return results


def get_market_moving_events(
    min_volume: float = 500000,
    min_probability_change: float = 0.10,
) -> List[Dict[str, Any]]:
    """
    Get events that are likely to move markets.
    
    Returns events with high volume and significant probability changes.
    """
    cache = get_polymarket_cache()
    
    # Get high volume events
    events = get_active_events(limit=100, order="volume", cache=cache)
    events = [e for e in events if e.volume and e.volume >= min_volume]
    
    # Get probability changes
    prob_changes = get_events_with_probability_changes(
        events=events,
        hours=24,
        threshold=min_probability_change,
        cache=cache,
    )
    
    # Create change map
    change_map = {pc.event_id: pc for pc in prob_changes}
    
    market_movers = []
    
    for event in events:
        prob_change = change_map.get(event.id)
        
        if prob_change and abs(prob_change.change) >= min_probability_change:
            market_movers.append({
                "event_id": event.id,
                "title": event.title,
                "category": event.category,
                "volume": event.volume,
                "probability": event.probability,
                "probability_change": prob_change.change,
                "direction": prob_change.direction,
            })
    
    # Sort by probability change magnitude
    market_movers.sort(key=lambda x: abs(x["probability_change"]), reverse=True)
    
    return market_movers
