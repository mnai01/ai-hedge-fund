"""Position context utilities for agents.

This module provides helper functions for agents to access position context
from the AgentState. Agents can optionally use these to get thesis information
for Polymarket-driven positions.

Usage in an agent:
    from src.utils.position_context import get_ticker_context, format_context_for_prompt
    
    context = get_ticker_context(state, ticker)
    if context:
        prompt_addition = format_context_for_prompt(context)
"""

from typing import Dict, Any, Optional


def get_ticker_context(state: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
    """Get position context for a specific ticker.
    
    Args:
        state: AgentState dict
        ticker: Stock ticker symbol
        
    Returns:
        Position context dict if exists, None otherwise
    """
    data = state.get("data", {})
    position_context = data.get("position_context", {})
    return position_context.get(ticker)


def get_all_polymarket_tickers(state: Dict[str, Any]) -> list[str]:
    """Get all tickers that have Polymarket context.
    
    Args:
        state: AgentState dict
        
    Returns:
        List of tickers with Polymarket context
    """
    data = state.get("data", {})
    position_context = data.get("position_context", {})
    return [
        ticker for ticker, ctx in position_context.items()
        if ctx.get("source") == "polymarket_event" or ctx.get("event_id")
    ]


def has_polymarket_context(state: Dict[str, Any], ticker: str) -> bool:
    """Check if a ticker has Polymarket context.
    
    Args:
        state: AgentState dict
        ticker: Stock ticker symbol
        
    Returns:
        True if ticker has Polymarket context
    """
    context = get_ticker_context(state, ticker)
    if not context:
        return False
    return context.get("source") == "polymarket_event" or context.get("event_id") is not None


def format_context_for_prompt(context: Dict[str, Any]) -> str:
    """Format position context as a string for LLM prompts.
    
    This creates a human-readable summary of the thesis that can be
    appended to agent prompts.
    
    Args:
        context: Position context dict
        
    Returns:
        Formatted string for prompt inclusion
    """
    if not context:
        return ""
    
    event_title = context.get("event_title", "Unknown Event")
    thesis = context.get("thesis", "No thesis provided")
    thesis_type = context.get("thesis_type", "unknown")
    direction = context.get("impact_direction", context.get("direction", "unknown"))
    
    prob_data = context.get("probability", {})
    current_prob = prob_data.get("current")
    prob_change = prob_data.get("since_entry")
    
    lines = [
        "=== POLYMARKET CONTEXT ===",
        f"Event: {event_title}",
        f"Thesis: {thesis}",
        f"Expected Impact: {direction}",
        f"Thesis Type: {thesis_type}",
    ]
    
    if current_prob is not None:
        lines.append(f"Current Probability: {current_prob:.1%}")
    
    if prob_change is not None:
        direction_word = "up" if prob_change > 0 else "down"
        lines.append(f"Probability Change Since Entry: {direction_word} {abs(prob_change):.1%}")
    
    event_state = context.get("event_state")
    if event_state and event_state != "active":
        lines.append(f"Event Status: {event_state.upper()}")
    
    lines.append("=" * 26)
    
    return "\n".join(lines)


def get_context_summary(state: Dict[str, Any]) -> Dict[str, str]:
    """Get a summary of all position contexts.
    
    Useful for logging/debugging.
    
    Args:
        state: AgentState dict
        
    Returns:
        Dict of ticker -> brief summary string
    """
    data = state.get("data", {})
    position_context = data.get("position_context", {})
    
    summaries = {}
    for ticker, ctx in position_context.items():
        if ctx.get("event_id"):
            prob = ctx.get("probability", {}).get("current")
            prob_str = f"{prob:.0%}" if prob else "?"
            summaries[ticker] = f"{ctx.get('event_title', 'Unknown')[:30]}... ({prob_str})"
        else:
            summaries[ticker] = "User-selected (no Polymarket context)"
    
    return summaries
