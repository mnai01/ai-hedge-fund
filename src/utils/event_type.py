"""Event type detection utilities for Polymarket events.

IMPORTANT: Event type detection is PROGRAMMATIC, not LLM-based.
We detect event types by analyzing the API response structure:
- Number of markets
- Outcome patterns
- Question patterns (dates, ranges)

LLM is ONLY used for stock mapping (expensive, use sparingly).
"""

import re
from typing import Optional, Tuple, List

from src.data.polymarket_models import PolymarketEvent, PolymarketMarket
from src.data.position_context import EventType, SequentialEventData


def detect_event_type(event: PolymarketEvent) -> EventType:
    """Detect event type from API structure - NO LLM.
    
    Detection logic:
    1. Single market with Yes/No outcomes → BINARY
    2. Single market with multiple outcomes → MULTI_OPTION  
    3. Multiple markets with date patterns → SEQUENTIAL
    4. Multiple markets with numeric ranges → RANGE
    5. Multiple markets (other) → MULTI_OPTION
    
    Args:
        event: PolymarketEvent from API
        
    Returns:
        EventType enum value
    """
    markets = event.markets or []
    
    if len(markets) == 0:
        return EventType.BINARY  # Default fallback
    
    if len(markets) == 1:
        market = markets[0]
        outcomes = market.outcomes or []
        
        # Check if binary (Yes/No)
        if len(outcomes) == 2:
            outcome_lower = [o.lower() for o in outcomes]
            if 'yes' in outcome_lower and 'no' in outcome_lower:
                return EventType.BINARY
        
        # Multiple outcomes in single market = multi-option
        if len(outcomes) > 2:
            return EventType.MULTI_OPTION
            
        return EventType.BINARY
    
    # Multiple markets - check for patterns
    questions = [m.question for m in markets if m.question]
    
    # Check for sequential (date patterns)
    if _has_date_pattern(questions):
        return EventType.SEQUENTIAL
    
    # Check for range (numeric patterns)
    if _has_range_pattern(questions):
        return EventType.RANGE
    
    # Default to multi-option for multiple markets
    return EventType.MULTI_OPTION


def _has_date_pattern(questions: List[str]) -> bool:
    """Check if questions contain date patterns indicating sequential event.
    
    Args:
        questions: List of market questions to analyze
        
    Returns:
        True if date patterns are found in majority of questions
    """
    date_patterns = [
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b',
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
        r'\bq[1-4]\b',  # Q1, Q2, Q3, Q4
        r'\b20\d{2}\b',  # Years like 2024, 2025
        r'\bby\s+(end\s+of\s+)?\w+',  # "by March", "by end of Q2"
    ]
    
    date_count = 0
    for question in questions:
        question_lower = question.lower()
        for pattern in date_patterns:
            if re.search(pattern, question_lower):
                date_count += 1
                break
    
    # If most questions have date patterns, it's sequential
    return date_count >= len(questions) * 0.5 and len(questions) > 1


def _has_range_pattern(questions: List[str]) -> bool:
    """Check if questions contain numeric range patterns.
    
    Args:
        questions: List of market questions to analyze
        
    Returns:
        True if range patterns are found in majority of questions
    """
    range_patterns = [
        r'\$[\d,]+\s*-\s*\$[\d,]+',  # $50,000 - $60,000
        r'\d+k?\s*-\s*\d+k?',  # 50k - 60k
        r'between\s+\d+',  # between 50
        r'above\s+\d+',  # above 100
        r'below\s+\d+',  # below 50
        r'over\s+\$?[\d,]+',  # over $100,000
        r'under\s+\$?[\d,]+',  # under $50,000
    ]
    
    range_count = 0
    for question in questions:
        question_lower = question.lower()
        for pattern in range_patterns:
            if re.search(pattern, question_lower):
                range_count += 1
                break
    
    # If most questions have range patterns, it's a range event
    return range_count >= len(questions) * 0.5 and len(questions) > 1


def calculate_cumulative_probability(event: PolymarketEvent) -> Optional[float]:
    """Calculate cumulative probability for sequential events.
    
    For "BTC ATH by [month]" type events:
    P(happens by December) = 1 - ∏(1 - P(month_i))
    
    This is the probability it happens by the LAST deadline.
    
    Args:
        event: PolymarketEvent with multiple sequential markets
        
    Returns:
        Cumulative probability (0-1) or None if not applicable
    """
    markets = event.markets or []
    
    if len(markets) <= 1:
        return None
    
    # Get probabilities for each market
    probabilities = []
    for market in markets:
        prob = market.primary_probability
        if prob is not None:
            probabilities.append(prob)
    
    if not probabilities:
        return None
    
    # P(happens by last) = 1 - P(doesn't happen in any)
    # P(doesn't happen in any) = ∏(1 - P_i)
    prob_none = 1.0
    for p in probabilities:
        prob_none *= (1 - p)
    
    return 1 - prob_none


def build_sequential_data(event: PolymarketEvent) -> Optional[SequentialEventData]:
    """Build sequential event data structure.
    
    Args:
        event: PolymarketEvent that was detected as SEQUENTIAL
        
    Returns:
        SequentialEventData or None if not applicable
    """
    markets = event.markets or []
    
    if len(markets) <= 1:
        return None
    
    # Find current active market (first non-closed market)
    current_index = 0
    for i, market in enumerate(markets):
        if not market.closed:
            current_index = i
            break
    
    # Get deadlines from market end dates or questions
    deadlines = []
    for market in markets:
        if market.end_date:
            deadlines.append(market.end_date)
        else:
            # Extract date from question if no end_date
            deadlines.append(market.question or "Unknown")
    
    cumulative = calculate_cumulative_probability(event)
    
    return SequentialEventData(
        current_market_index=current_index,
        total_markets=len(markets),
        cumulative_probability=cumulative or 0.0,
        market_deadlines=deadlines
    )


def is_event_resolved(event: PolymarketEvent) -> Tuple[bool, Optional[str]]:
    """Check if event is resolved and get resolution outcome.
    
    Args:
        event: PolymarketEvent to check
        
    Returns:
        Tuple of (is_resolved, outcome) where outcome is 'yes', 'no', or None
    """
    # Check if event is marked as closed
    if event.closed:
        # Try to determine outcome from probability
        prob = event.probability
        if prob is not None:
            if prob >= 0.99:
                return True, "yes"
            elif prob <= 0.01:
                return True, "no"
        return True, None
    
    # Check primary market
    primary = event.primary_market
    if primary and primary.closed:
        prob = primary.primary_probability
        if prob is not None:
            if prob >= 0.99:
                return True, "yes"
            elif prob <= 0.01:
                return True, "no"
        return True, None
    
    return False, None
