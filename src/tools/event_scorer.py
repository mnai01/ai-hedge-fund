"""Event Scoring Engine for Polymarket event discovery.

This module provides the EventScorer class for ranking Polymarket events
based on their trading potential before LLM analysis.

Scoring Components:
- Volume: Total trading volume (volume, volume24hr, volume1wk)
- Liquidity: Current market liquidity
- Time Horizon: Days until event resolution (endDate)
- Category: Stock market relevance by category
- Momentum: Price movement (oneDayPriceChange, oneWeekPriceChange)
- Volume Trend: Volume acceleration (volume24hr / volume1wk ratio)
- Smart Money: Institutional activity proxy (openInterest)

Reference: plans/POLYMARKET_EVENT_DISCOVERY_DESIGN.md
API Reference: docs/Polymarket/api-reference/events/list-events.md
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union

from src.data.event_models import (
    ScoringWeights,
    EventScore,
    ScoringConfig,
    RankedEventList,
    EnhancedScoringWeights,
    SignalSummary,
    EnhancedSignalSummary,
)
from src.data.polymarket_models import PolymarketEvent


# Official Polymarket categories (10 total)
OFFICIAL_CATEGORIES = [
    "politics",
    "crypto",
    "economy",
    "finance",
    "tech",
    "sports",
    "culture",
    "climate-science",
    "mentions",
    "other",
]


class EventScorer:
    """Score and rank Polymarket events for trading potential.
    
    The EventScorer evaluates events using multiple criteria to identify
    the most promising events for stock market analysis. This reduces
    LLM costs by filtering out low-value events before expensive analysis.
    
    Attributes:
        config: ScoringConfig with weights and thresholds
        
    Example:
        >>> scorer = EventScorer()
        >>> events = get_active_events(limit=50)
        >>> ranked = scorer.rank_events(events)
        >>> for event in ranked.top_events:
        ...     print(f"{event.event_title}: {event.total_score:.1f}")
    """
    
    def __init__(self, config: Optional[ScoringConfig] = None):
        """Initialize the EventScorer.
        
        Args:
            config: Optional ScoringConfig. Uses defaults if not provided.
        """
        self.config = config or ScoringConfig()
    
    def score_event(
        self, 
        event: Union[Dict[str, Any], PolymarketEvent],
        market: Optional[Dict[str, Any]] = None,
    ) -> EventScore:
        """Calculate composite score for an event.
        
        Args:
            event: Event dict from Polymarket API or PolymarketEvent object
            market: Optional market dict with price change data
            
        Returns:
            EventScore with total score and component breakdown
            
        Example:
            >>> score = scorer.score_event(event_dict)
            >>> print(f"Score: {score.total_score}, Recommendation: {score.recommendation}")
        """
        # Convert PolymarketEvent to dict if needed
        if isinstance(event, PolymarketEvent):
            event_dict = self._event_to_dict(event)
        else:
            event_dict = event
        
        # Calculate individual component scores (0-100 each)
        component_scores = {
            "volume": self._volume_score(event_dict),
            "liquidity": self._liquidity_score(event_dict),
            "time_horizon": self._time_horizon_score(event_dict),
            "category": self._category_score(event_dict),
            "momentum": self._momentum_score(event_dict, market),
            "volume_trend": self._volume_trend_score(event_dict),
            "smart_money": self._smart_money_score(event_dict),
        }
        
        # Calculate weighted total score
        weights = self.config.weights.to_dict()
        total_score = sum(
            component_scores[key] * weights[key] 
            for key in component_scores
        )
        
        # Determine recommendation based on score
        recommendation = EventScore.get_recommendation(total_score)
        
        # Extract metadata
        event_id = event_dict.get("id", "")
        event_title = event_dict.get("title", "")
        category = self._extract_category(event_dict)
        end_date = event_dict.get("endDate") or event_dict.get("end_date")
        volume = event_dict.get("volume")
        liquidity = event_dict.get("liquidity")
        
        return EventScore(
            event_id=event_id,
            event_title=event_title,
            total_score=total_score,
            component_scores=component_scores,
            recommendation=recommendation,
            category=category,
            end_date=end_date,
            volume=volume,
            liquidity=liquidity,
        )
    
    def _volume_score(self, event: Dict[str, Any]) -> float:
        """Score based on trading volume.
        
        Uses: volume, volume24hr, volume1wk fields from Polymarket API.
        Higher volume indicates more market interest and better liquidity.
        
        Args:
            event: Event dict with volume fields
            
        Returns:
            Score from 0-100
        """
        volume = self._safe_float(event.get("volume"), 0)
        volume_24hr = self._safe_float(event.get("volume24hr") or event.get("volume_24hr"), 0)
        volume_1wk = self._safe_float(event.get("volume1wk") or event.get("volume_1wk"), 0)
        
        # Score total volume (observed range: 0 to 100M+)
        if volume >= 10_000_000:
            total_volume_score = 100
        elif volume >= 1_000_000:
            total_volume_score = 85
        elif volume >= 100_000:
            total_volume_score = 70
        elif volume >= 10_000:
            total_volume_score = 50
        elif volume >= 1_000:
            total_volume_score = 30
        else:
            total_volume_score = 15
        
        # Score 24h volume (recent activity)
        if volume_24hr >= 100_000:
            recent_volume_score = 100
        elif volume_24hr >= 50_000:
            recent_volume_score = 85
        elif volume_24hr >= 10_000:
            recent_volume_score = 70
        elif volume_24hr >= 1_000:
            recent_volume_score = 50
        else:
            recent_volume_score = 25
        
        # Combine with weights (total volume more important)
        return total_volume_score * 0.6 + recent_volume_score * 0.4
    
    def _liquidity_score(self, event: Dict[str, Any]) -> float:
        """Score based on current liquidity.
        
        Uses: liquidity field from Polymarket API.
        Higher liquidity means better execution and lower slippage.
        
        Args:
            event: Event dict with liquidity field
            
        Returns:
            Score from 0-100
        """
        liquidity = self._safe_float(event.get("liquidity"), 0)
        
        # Score liquidity (observed range: 0 to 1M+)
        if liquidity >= 500_000:
            return 100
        elif liquidity >= 100_000:
            return 85
        elif liquidity >= 50_000:
            return 70
        elif liquidity >= 10_000:
            return 55
        elif liquidity >= 5_000:
            return 40
        elif liquidity >= 1_000:
            return 25
        else:
            return 10
    
    def _time_horizon_score(self, event: Dict[str, Any]) -> float:
        """Score based on time to resolution.
        
        Uses: endDate field from Polymarket API.
        Sweet spot is 7-30 days - enough time to trade but not too far out.
        
        Args:
            event: Event dict with endDate field
            
        Returns:
            Score from 0-100
        """
        end_date_str = event.get("endDate") or event.get("end_date")
        
        if not end_date_str:
            return 50  # Unknown timing - neutral score
        
        try:
            # Parse ISO datetime (handle various formats)
            if isinstance(end_date_str, str):
                # Handle ISO format with or without timezone
                end_date_str = end_date_str.replace("Z", "+00:00")
                if "T" in end_date_str:
                    end_date = datetime.fromisoformat(end_date_str)
                else:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                    end_date = end_date.replace(tzinfo=timezone.utc)
            else:
                return 50
            
            # Calculate days to end
            now = datetime.now(timezone.utc)
            days_to_end = (end_date - now).days
            
        except (ValueError, TypeError, AttributeError):
            return 50  # Parse error - neutral score
        
        # Score based on time horizon
        # Sweet spot: 7-30 days (enough time to trade, not too far out)
        if 7 <= days_to_end <= 30:
            return 100  # Optimal range
        elif 3 <= days_to_end < 7:
            return 80  # Short term - still good
        elif 30 < days_to_end <= 60:
            return 75  # Medium term
        elif 60 < days_to_end <= 90:
            return 55  # Longer term
        elif days_to_end < 3:
            return 40  # Too soon - may not have time to react
        elif days_to_end > 90:
            return 30  # Too far out - high uncertainty
        else:
            return 50
    
    def _category_score(self, event: Dict[str, Any]) -> float:
        """Score based on category relevance to stock markets.
        
        Uses: category field from Polymarket API.
        Categories like economy/finance have higher stock market relevance.
        
        Official categories (10 total):
        - politics, crypto, economy, finance, tech
        - sports, culture, climate-science, mentions, other
        
        Args:
            event: Event dict with category field
            
        Returns:
            Score from 0-100
        """
        category = self._extract_category(event)
        weight = self.config.get_category_weight(category)
        
        # Convert weight (0-1) to score (0-100)
        return weight * 100
    
    def _momentum_score(
        self, 
        event: Dict[str, Any], 
        market: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Score based on price momentum.
        
        Uses: oneDayPriceChange, oneWeekPriceChange from market data.
        Strong momentum indicates clearer directional signal.
        
        Args:
            event: Event dict (may contain markets array)
            market: Optional separate market dict
            
        Returns:
            Score from 0-100
        """
        # Try to get market data from event or separate market dict
        market_data = market
        if not market_data:
            markets = event.get("markets", [])
            if markets and len(markets) > 0:
                market_data = markets[0]
        
        if not market_data:
            return 50  # No market data - neutral score
        
        # Get price changes
        day_change = self._safe_float(market_data.get("oneDayPriceChange"), 0)
        week_change = self._safe_float(market_data.get("oneWeekPriceChange"), 0)
        
        # Use absolute values for magnitude
        day_magnitude = abs(day_change)
        week_magnitude = abs(week_change)
        
        # Check for trend consistency (same direction)
        day_dir = 1 if day_change >= 0 else -1
        week_dir = 1 if week_change >= 0 else -1
        consistent = day_dir == week_dir
        
        # Weighted momentum magnitude
        momentum = day_magnitude * 0.6 + week_magnitude * 0.4
        
        # Consistency bonus
        consistency_bonus = 10 if consistent else 0
        
        # Score based on momentum magnitude
        if momentum >= 0.15:
            base_score = 90  # 15%+ move - very significant
        elif momentum >= 0.10:
            base_score = 75  # 10%+ move - significant
        elif momentum >= 0.05:
            base_score = 55  # 5%+ move - notable
        elif momentum >= 0.02:
            base_score = 40  # 2%+ move - some movement
        else:
            base_score = 30  # Low momentum
        
        return min(100, base_score + consistency_bonus)
    
    def _volume_trend_score(self, event: Dict[str, Any]) -> float:
        """Score based on volume acceleration.
        
        Uses: volume24hr, volume1wk from Polymarket API.
        High volume acceleration suggests informed trading activity.
        Similar to options unusual activity detection.
        
        Args:
            event: Event dict with volume fields
            
        Returns:
            Score from 0-100
        """
        vol_24h = self._safe_float(event.get("volume24hr") or event.get("volume_24hr"), 0)
        vol_1wk = self._safe_float(event.get("volume1wk") or event.get("volume_1wk"), 0)
        
        if vol_1wk == 0:
            return 50  # No baseline - neutral score
        
        # Calculate daily average over past week
        daily_avg = vol_1wk / 7
        
        if daily_avg == 0:
            return 50
        
        # Volume acceleration ratio
        acceleration = vol_24h / daily_avg
        
        # Score based on acceleration
        # High acceleration = unusual activity = potential signal
        if acceleration >= 3.0:
            return 100  # 3x+ normal volume - very unusual
        elif acceleration >= 2.0:
            return 85  # 2x normal - notable
        elif acceleration >= 1.5:
            return 70  # 1.5x normal - elevated
        elif acceleration >= 1.0:
            return 50  # Normal activity
        elif acceleration >= 0.5:
            return 35  # Below average
        else:
            return 20  # Declining interest
    
    def _smart_money_score(self, event: Dict[str, Any]) -> float:
        """Score based on institutional activity proxy.
        
        Uses: openInterest, volume24hr from Polymarket API.
        High volume relative to open interest suggests new positions being opened.
        
        Args:
            event: Event dict with openInterest field
            
        Returns:
            Score from 0-100
        """
        vol_24h = self._safe_float(event.get("volume24hr") or event.get("volume_24hr"), 0)
        open_interest = self._safe_float(event.get("openInterest") or event.get("open_interest"), 0)
        
        if open_interest == 0:
            # No open interest data - use volume as proxy
            if vol_24h >= 100_000:
                return 70
            elif vol_24h >= 10_000:
                return 50
            else:
                return 30
        
        # High volume relative to OI = new positions being opened
        ratio = vol_24h / open_interest
        
        if ratio >= 0.5:
            return 100  # Very active - 50%+ of OI traded in 24h
        elif ratio >= 0.2:
            return 80  # Active
        elif ratio >= 0.1:
            return 60  # Moderate
        elif ratio >= 0.05:
            return 45  # Low activity
        else:
            return 25  # Stale market
    
    def rank_events(
        self, 
        events: List[Union[Dict[str, Any], PolymarketEvent]],
        min_score: Optional[float] = None,
        categories: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> RankedEventList:
        """Score and rank multiple events.
        
        Args:
            events: List of event dicts or PolymarketEvent objects
            min_score: Optional minimum score filter
            categories: Optional list of categories to include
            limit: Optional maximum number of events to return
            
        Returns:
            RankedEventList with scored and ranked events
            
        Example:
            >>> ranked = scorer.rank_events(events, min_score=60, limit=10)
            >>> print(f"Top events: {len(ranked.top_events)}")
        """
        # Filter by category first if specified
        if categories:
            events = self.filter_by_category(events, categories)
        
        # Score all events
        scored_events: List[EventScore] = []
        for event in events:
            try:
                score = self.score_event(event)
                scored_events.append(score)
            except Exception as e:
                # Log but continue processing other events
                event_id = event.get("id", "unknown") if isinstance(event, dict) else getattr(event, "id", "unknown")
                print(f"Error scoring event {event_id}: {e}")
                continue
        
        # Sort by total score (highest first)
        scored_events.sort(key=lambda e: e.total_score, reverse=True)
        
        # Assign ranks
        for i, event in enumerate(scored_events, start=1):
            event.rank = i
        
        # Filter by minimum score if specified
        if min_score is not None:
            scored_events = [e for e in scored_events if e.total_score >= min_score]
        
        # Apply limit if specified
        total_before_limit = len(scored_events)
        if limit is not None:
            scored_events = scored_events[:limit]
        
        return RankedEventList(
            events=scored_events,
            total_events=len(events),
            filtered_count=total_before_limit,
            scoring_config=self.config,
        )
    
    def filter_by_category(
        self, 
        events: List[Union[Dict[str, Any], PolymarketEvent]],
        categories: List[str],
    ) -> List[Union[Dict[str, Any], PolymarketEvent]]:
        """Filter events by category.
        
        Args:
            events: List of events to filter
            categories: List of category names to include (case-insensitive)
            
        Returns:
            Filtered list of events
            
        Example:
            >>> filtered = scorer.filter_by_category(events, ["economy", "finance", "politics"])
        """
        # Normalize category names to lowercase
        categories_lower = [c.lower() for c in categories]
        
        filtered = []
        for event in events:
            category = self._extract_category(
                event if isinstance(event, dict) else self._event_to_dict(event)
            )
            
            if category and category.lower() in categories_lower:
                filtered.append(event)
        
        return filtered
    
    def get_high_relevance_events(
        self,
        events: List[Union[Dict[str, Any], PolymarketEvent]],
        min_score: float = 70,
    ) -> List[EventScore]:
        """Get events with high stock market relevance.
        
        Filters to high-relevance categories and minimum score.
        
        Args:
            events: List of events to filter
            min_score: Minimum score threshold
            
        Returns:
            List of EventScore objects for high-relevance events
        """
        # High relevance categories
        high_relevance_categories = ["economy", "finance", "politics", "tech"]
        
        # Filter and rank
        ranked = self.rank_events(
            events,
            min_score=min_score,
            categories=high_relevance_categories,
        )
        
        return ranked.events
    
    # Helper methods
    
    def _extract_category(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract category from event dict.
        
        Handles both direct category field and tags array.
        Prioritizes official Polymarket categories over specific tags.
        
        Official categories: politics, crypto, economy, finance, tech,
        sports, culture, climate-science, mentions, other
        
        Args:
            event: Event dict
            
        Returns:
            Category string or None
        """
        # Official Polymarket categories (prioritized)
        OFFICIAL_CATEGORIES = {
            "politics", "crypto", "economy", "finance", "tech",
            "sports", "culture", "climate-science", "mentions", "other",
            # Common variations
            "world elections", "elections", "basketball", "football",
            "baseball", "soccer", "hockey", "tennis", "golf",
        }
        
        # Category mapping for non-standard tags
        CATEGORY_MAPPING = {
            "world elections": "politics",
            "elections": "politics",
            "trump": "politics",
            "biden": "politics",
            "fed": "economy",
            "federal reserve": "economy",
            "interest rates": "economy",
            "inflation": "economy",
            "bitcoin": "crypto",
            "ethereum": "crypto",
            "nba": "sports",
            "nfl": "sports",
            "mlb": "sports",
            "basketball": "sports",
            "football": "sports",
            "baseball": "sports",
            "soccer": "sports",
            "superbowl": "sports",
            "ai": "tech",
            "artificial intelligence": "tech",
            "openai": "tech",
            "climate": "climate-science",
            "weather": "climate-science",
        }
        
        # Try direct category field first
        category = event.get("category")
        if category:
            cat_lower = category.lower()
            # Map to official category if needed
            if cat_lower in CATEGORY_MAPPING:
                return CATEGORY_MAPPING[cat_lower]
            return category
        
        # Try extracting from tags - prioritize official categories
        tags = event.get("tags", [])
        if tags and isinstance(tags, list):
            # First pass: look for official categories
            for tag in tags:
                if isinstance(tag, dict):
                    label = (tag.get("label") or tag.get("slug") or "").lower()
                    if label in OFFICIAL_CATEGORIES:
                        return label
                    if label in CATEGORY_MAPPING:
                        return CATEGORY_MAPPING[label]
                elif isinstance(tag, str):
                    label = tag.lower()
                    if label in OFFICIAL_CATEGORIES:
                        return label
                    if label in CATEGORY_MAPPING:
                        return CATEGORY_MAPPING[label]
            
            # Second pass: return first tag if no official category found
            for tag in tags:
                if isinstance(tag, dict):
                    label = tag.get("label") or tag.get("slug")
                    if label:
                        # Try to map it
                        label_lower = label.lower()
                        if label_lower in CATEGORY_MAPPING:
                            return CATEGORY_MAPPING[label_lower]
                        return label
                elif isinstance(tag, str):
                    return tag
        
        return None
    
    def _event_to_dict(self, event: PolymarketEvent) -> Dict[str, Any]:
        """Convert PolymarketEvent to dict for scoring.
        
        Args:
            event: PolymarketEvent object
            
        Returns:
            Dict representation
        """
        result = {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "volume": event.volume,
            "volume24hr": event.volume_24hr,
            "liquidity": event.liquidity,
            "endDate": event.end_date,
            "active": event.active,
            "closed": event.closed,
            "featured": event.featured,
            "tags": event.tags,
        }
        
        # Add markets if available
        if event.markets:
            result["markets"] = [
                {
                    "id": m.id,
                    "question": m.question,
                    "outcomePrices": m.outcome_prices,
                    "volume": m.volume,
                    "volume24hr": m.volume_24hr,
                    "liquidity": m.liquidity,
                }
                for m in event.markets
            ]
        
        return result
    
    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float.
        
        Args:
            value: Value to convert
            default: Default if conversion fails
            
        Returns:
            Float value or default
        """
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default


def create_scorer(
    weights: Optional[Dict[str, float]] = None,
    min_score_threshold: float = 70.0,
) -> EventScorer:
    """Factory function to create an EventScorer with custom configuration.
    
    Args:
        weights: Optional dict of scoring weights
        min_score_threshold: Minimum score for "analyze" recommendation
        
    Returns:
        Configured EventScorer instance
        
    Example:
        >>> scorer = create_scorer(weights={"volume": 0.3, "liquidity": 0.25})
    """
    config = ScoringConfig(min_score_threshold=min_score_threshold)
    
    if weights:
        config.weights = ScoringWeights(**weights).normalize()
    
    return EventScorer(config=config)


# Convenience functions for common operations

def score_events(
    events: List[Union[Dict[str, Any], PolymarketEvent]],
    min_score: float = 0,
    categories: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[EventScore]:
    """Score and rank events using default configuration.
    
    Args:
        events: List of events to score
        min_score: Minimum score filter
        categories: Optional category filter
        limit: Maximum events to return
        
    Returns:
        List of EventScore objects
        
    Example:
        >>> scores = score_events(events, min_score=60, limit=10)
    """
    scorer = EventScorer()
    ranked = scorer.rank_events(events, min_score=min_score, categories=categories, limit=limit)
    return ranked.events


def get_top_events(
    events: List[Union[Dict[str, Any], PolymarketEvent]],
    n: int = 10,
    categories: Optional[List[str]] = None,
) -> List[EventScore]:
    """Get the top N scored events.
    
    Args:
        events: List of events to score
        n: Number of top events to return
        categories: Optional category filter
        
    Returns:
        List of top N EventScore objects
    """
    scorer = EventScorer()
    ranked = scorer.rank_events(events, categories=categories, limit=n)
    return ranked.events


def filter_stock_relevant_events(
    events: List[Union[Dict[str, Any], PolymarketEvent]],
    min_score: float = 60,
) -> List[EventScore]:
    """Filter events to those relevant for stock market analysis.
    
    Uses high-relevance categories: economy, finance, politics, tech
    
    Args:
        events: List of events to filter
        min_score: Minimum score threshold
        
    Returns:
        List of stock-relevant EventScore objects
    """
    scorer = EventScorer()
    return scorer.get_high_relevance_events(events, min_score=min_score)


# Signal interpretation helpers

def interpret_signal(signal_name: str, strength: float) -> str:
    """Convert signal strength to human-readable interpretation.
    
    Args:
        signal_name: Name of the signal (e.g., "unusual_volume", "delta_movement")
        strength: Signal strength from 0.0 to 1.0
        
    Returns:
        Human-readable interpretation string
        
    Example:
        >>> interpret_signal("unusual_volume", 0.85)
        "Strong unusual volume signal"
    """
    # Format signal name for display
    display_name = signal_name.replace("_", " ")
    
    if strength >= 0.7:
        return f"Strong {display_name} signal"
    elif strength >= 0.4:
        return f"Moderate {display_name} signal"
    else:
        return f"Weak {display_name} signal"


def interpret_unusual_volume(ratio: float) -> str:
    """Interpret unusual volume ratio.
    
    Args:
        ratio: Volume ratio (24hr volume / 7-day daily average)
        
    Returns:
        Human-readable interpretation
    """
    if ratio >= 3.0:
        return "Very high unusual activity - potential informed trading"
    elif ratio >= 2.0:
        return "High unusual activity - notable interest spike"
    elif ratio >= 1.5:
        return "Elevated activity - above normal interest"
    elif ratio >= 1.0:
        return "Normal activity level"
    elif ratio >= 0.5:
        return "Below average activity"
    else:
        return "Low activity - declining interest"


def interpret_delta_movement(price_change: float) -> str:
    """Interpret delta/probability movement.
    
    Args:
        price_change: Absolute price change (0-1 scale)
        
    Returns:
        Human-readable interpretation
    """
    if price_change >= 0.15:
        return "Major probability shift - significant new information"
    elif price_change >= 0.10:
        return "Large probability shift - notable development"
    elif price_change >= 0.05:
        return "Moderate probability shift - some movement"
    elif price_change >= 0.02:
        return "Minor probability shift - slight adjustment"
    else:
        return "Minimal movement - stable probability"


def interpret_implied_volatility(spread: float) -> str:
    """Interpret implied volatility proxy (spread).
    
    Args:
        spread: Bid-ask spread as decimal
        
    Returns:
        Human-readable interpretation
    """
    if spread >= 0.10:
        return "Very high uncertainty - wide spread indicates disagreement"
    elif spread >= 0.05:
        return "High uncertainty - significant spread"
    elif spread >= 0.02:
        return "Moderate uncertainty - normal spread"
    elif spread >= 0.01:
        return "Low uncertainty - tight spread"
    else:
        return "Very low uncertainty - highly efficient market"


def interpret_smart_money(volume_oi_ratio: float) -> str:
    """Interpret smart money signal (volume/OI ratio).
    
    Args:
        volume_oi_ratio: 24hr volume / open interest ratio
        
    Returns:
        Human-readable interpretation
    """
    if volume_oi_ratio >= 0.5:
        return "Very high institutional interest - major position changes"
    elif volume_oi_ratio >= 0.2:
        return "High institutional interest - active positioning"
    elif volume_oi_ratio >= 0.1:
        return "Moderate institutional interest"
    elif volume_oi_ratio >= 0.05:
        return "Low institutional interest"
    else:
        return "Minimal institutional activity - stale market"


class EnhancedEventScorer(EventScorer):
    """Extended scorer with options-like signal analysis.
    
    This class extends the base EventScorer with additional methods that
    map Polymarket data to options market concepts for more sophisticated
    trading signal detection.
    
    Options-Like Signal Mapping:
    - Unusual Volume: volume24hr / (volume1wk / 7) ratio
    - Delta Movement: oneDayPriceChange, oneWeekPriceChange
    - Implied Volatility: spread (bid-ask) as proxy
    - Smart Money: openInterest + volume patterns
    
    Attributes:
        config: ScoringConfig with weights and thresholds
        enhanced_weights: EnhancedScoringWeights for signal weighting
        
    Example:
        >>> scorer = EnhancedEventScorer()
        >>> event = get_event_by_id("some-event-id")
        >>> market = event.get("markets", [{}])[0]
        >>> summary = scorer.get_signal_summary(event, market)
        >>> print(f"Overall signal: {summary.overall_signal_strength:.2f}")
    """
    
    def __init__(
        self,
        config: Optional[ScoringConfig] = None,
        enhanced_weights: Optional[EnhancedScoringWeights] = None,
    ):
        """Initialize the EnhancedEventScorer.
        
        Args:
            config: Optional ScoringConfig. Uses defaults if not provided.
            enhanced_weights: Optional EnhancedScoringWeights for signal weighting.
        """
        super().__init__(config)
        self.enhanced_weights = enhanced_weights or EnhancedScoringWeights()
    
    def _unusual_volume_signal(self, event: Dict[str, Any]) -> float:
        """Detect unusual volume activity (like options unusual activity).
        
        Signal strength based on volume24hr / (volume1wk / 7) ratio.
        This maps to options market unusual activity detection where
        high volume relative to historical average indicates informed trading.
        
        Args:
            event: Event dict with volume24hr and volume1wk fields
            
        Returns:
            Signal strength from 0.0 to 1.0
            
        Signal Interpretation:
            - Ratio > 3.0: strength >= 0.9 (very unusual)
            - Ratio > 2.0: strength >= 0.7 (notable)
            - Ratio > 1.5: strength >= 0.5 (elevated)
            - Ratio >= 1.0: strength ~0.3 (normal)
            - Ratio < 1.0: strength < 0.3 (declining)
        """
        vol_24h = self._safe_float(
            event.get("volume24hr") or event.get("volume_24hr"), 0
        )
        vol_1wk = self._safe_float(
            event.get("volume1wk") or event.get("volume_1wk"), 0
        )
        total_volume = self._safe_float(event.get("volume"), 0)
        
        # If we have volume24hr and volume1wk, use ratio-based signal
        if vol_24h > 0 and vol_1wk > 0:
            # Calculate daily average over past week
            daily_avg = vol_1wk / 7
            
            if daily_avg > 0:
                # Volume acceleration ratio
                ratio = vol_24h / daily_avg
                
                # Convert ratio to signal strength (0-1)
                if ratio >= 3.0:
                    return min(1.0, 0.9 + (ratio - 3.0) * 0.02)  # Cap at 1.0
                elif ratio >= 2.0:
                    return 0.7 + (ratio - 2.0) * 0.2  # 0.7-0.9
                elif ratio >= 1.5:
                    return 0.5 + (ratio - 1.5) * 0.4  # 0.5-0.7
                elif ratio >= 1.0:
                    return 0.3 + (ratio - 1.0) * 0.4  # 0.3-0.5
                elif ratio >= 0.5:
                    return 0.15 + (ratio - 0.5) * 0.3  # 0.15-0.3
                else:
                    return max(0.0, ratio * 0.3)  # 0.0-0.15
        
        # Fallback: Use total volume as absolute signal
        # This handles cases where volume24hr is None but total volume exists
        if total_volume > 0:
            # Scale based on total volume (higher volume = more interest)
            if total_volume >= 10_000_000:  # $10M+
                return 0.85
            elif total_volume >= 5_000_000:  # $5M+
                return 0.70
            elif total_volume >= 1_000_000:  # $1M+
                return 0.55
            elif total_volume >= 500_000:  # $500K+
                return 0.45
            elif total_volume >= 100_000:  # $100K+
                return 0.35
            elif total_volume >= 10_000:  # $10K+
                return 0.25
            else:
                return 0.15
        
        # Fallback to volume24hr if available (when total_volume not present)
        if vol_24h > 0:
            if vol_24h >= 500_000:
                return 0.55
            elif vol_24h >= 100_000:
                return 0.40
            elif vol_24h >= 50_000:
                return 0.30
            elif vol_24h >= 10_000:
                return 0.25
            else:
                return 0.20
        
        # Fallback to weekly volume if available
        if vol_1wk > 0:
            if vol_1wk >= 1_000_000:
                return 0.50
            elif vol_1wk >= 500_000:
                return 0.40
            elif vol_1wk >= 100_000:
                return 0.30
            else:
                return 0.20
        
        # No volume data at all - return low signal
        return 0.15
    
    def _delta_movement_signal(self, market: Dict[str, Any], event: Optional[Dict[str, Any]] = None) -> float:
        """Detect significant probability shifts (like delta changes).
        
        Uses oneDayPriceChange and oneWeekPriceChange to detect momentum.
        Large probability moves indicate significant new information,
        similar to how delta changes in options signal directional moves.
        
        Args:
            market: Market dict with oneDayPriceChange and oneWeekPriceChange
            event: Optional event dict (also checked for price change data)
            
        Returns:
            Signal strength from 0.0 to 1.0
            
        Signal Interpretation:
            - >10% move: strength >= 0.7 (strong signal)
            - 5-10% move: strength 0.4-0.7 (moderate signal)
            - <5% move: strength < 0.4 (weak signal)
        """
        # Try to get price change from market first, then event
        day_change = 0.0
        week_change = 0.0
        
        if market:
            day_change = self._safe_float(market.get("oneDayPriceChange"), 0)
            week_change = self._safe_float(market.get("oneWeekPriceChange"), 0)
        
        # Fallback to event-level data if market doesn't have it
        if day_change == 0 and event:
            day_change = self._safe_float(event.get("oneDayPriceChange"), 0)
        if week_change == 0 and event:
            week_change = self._safe_float(event.get("oneWeekPriceChange"), 0)
        
        # If still no data, check for markets array in event
        if day_change == 0 and week_change == 0 and event:
            markets = event.get("markets", [])
            if markets and len(markets) > 0:
                primary_market = markets[0]
                day_change = self._safe_float(primary_market.get("oneDayPriceChange"), 0)
                week_change = self._safe_float(primary_market.get("oneWeekPriceChange"), 0)
        
        # If no price change data at all, return low signal
        if day_change == 0 and week_change == 0:
            return 0.20
        
        # Use absolute values for magnitude
        day_magnitude = abs(day_change)
        week_magnitude = abs(week_change)
        
        # Check for trend consistency (same direction)
        day_dir = 1 if day_change >= 0 else -1
        week_dir = 1 if week_change >= 0 else -1
        consistent = day_dir == week_dir or day_change == 0 or week_change == 0
        
        # Weighted momentum magnitude (recent more important)
        momentum = day_magnitude * 0.6 + week_magnitude * 0.4
        
        # Consistency bonus (adds up to 0.1)
        consistency_bonus = 0.1 if consistent else 0.0
        
        # Convert momentum to signal strength
        if momentum >= 0.15:
            base_strength = 0.85
        elif momentum >= 0.10:
            base_strength = 0.7 + (momentum - 0.10) * 3.0  # 0.7-0.85
        elif momentum >= 0.05:
            base_strength = 0.4 + (momentum - 0.05) * 6.0  # 0.4-0.7
        elif momentum >= 0.02:
            base_strength = 0.2 + (momentum - 0.02) * 6.67  # 0.2-0.4
        else:
            base_strength = momentum * 10  # 0.0-0.2
        
        return min(1.0, base_strength + consistency_bonus)
    
    def _implied_volatility_proxy(self, market: Dict[str, Any]) -> float:
        """Use spread as proxy for implied volatility.
        
        Wider spreads indicate higher uncertainty about the true probability,
        similar to how higher implied volatility in options indicates
        expected larger price swings.
        
        Args:
            market: Market dict with spread field
            
        Returns:
            Signal strength from 0.0 to 1.0 (higher = more uncertainty)
            
        Signal Interpretation:
            - Spread > 10%: strength >= 0.8 (very high uncertainty)
            - Spread 5-10%: strength 0.5-0.8 (high uncertainty)
            - Spread 2-5%: strength 0.3-0.5 (moderate uncertainty)
            - Spread < 2%: strength < 0.3 (low uncertainty)
        """
        if not market:
            return 0.5  # Neutral if no market data
        
        spread = self._safe_float(market.get("spread"), 0)
        
        # Also try to calculate from bid/ask if spread not directly available
        if spread == 0:
            best_bid = self._safe_float(market.get("bestBid"), 0)
            best_ask = self._safe_float(market.get("bestAsk"), 0)
            if best_bid > 0 and best_ask > 0:
                spread = best_ask - best_bid
        
        # Convert spread to signal strength
        # Higher spread = higher uncertainty = higher signal
        if spread >= 0.10:
            return min(1.0, 0.8 + (spread - 0.10) * 2.0)  # 0.8-1.0
        elif spread >= 0.05:
            return 0.5 + (spread - 0.05) * 6.0  # 0.5-0.8
        elif spread >= 0.02:
            return 0.3 + (spread - 0.02) * 6.67  # 0.3-0.5
        elif spread >= 0.01:
            return 0.15 + (spread - 0.01) * 15.0  # 0.15-0.3
        else:
            return max(0.0, spread * 15.0)  # 0.0-0.15
    
    def _smart_money_signal(self, event: Dict[str, Any]) -> float:
        """Detect smart money activity via open interest changes.
        
        High OI + high volume indicates institutional interest.
        The ratio of 24hr volume to open interest shows how actively
        positions are being opened/closed, similar to options flow analysis.
        
        Args:
            event: Event dict with openInterest and volume24hr fields
            
        Returns:
            Signal strength from 0.0 to 1.0
            
        Signal Interpretation:
            - Vol/OI > 50%: strength >= 0.8 (very active institutional)
            - Vol/OI 20-50%: strength 0.5-0.8 (active)
            - Vol/OI 10-20%: strength 0.3-0.5 (moderate)
            - Vol/OI < 10%: strength < 0.3 (low activity)
        """
        vol_24h = self._safe_float(
            event.get("volume24hr") or event.get("volume_24hr"), 0
        )
        open_interest = self._safe_float(
            event.get("openInterest") or event.get("open_interest"), 0
        )
        total_volume = self._safe_float(event.get("volume"), 0)
        
        # If we have both volume24hr and openInterest, use ratio-based signal
        if open_interest > 0 and vol_24h > 0:
            # Calculate volume/OI ratio
            ratio = vol_24h / open_interest
            
            # Convert ratio to signal strength
            if ratio >= 0.5:
                return min(1.0, 0.8 + (ratio - 0.5) * 0.4)  # 0.8-1.0
            elif ratio >= 0.2:
                return 0.5 + (ratio - 0.2) * 1.0  # 0.5-0.8
            elif ratio >= 0.1:
                return 0.3 + (ratio - 0.1) * 2.0  # 0.3-0.5
            elif ratio >= 0.05:
                return 0.15 + (ratio - 0.05) * 3.0  # 0.15-0.3
            else:
                return max(0.0, ratio * 3.0)  # 0.0-0.15
        
        # Fallback: Use total volume as proxy for institutional interest
        # Higher total volume suggests more institutional participation
        if total_volume > 0:
            if total_volume >= 10_000_000:  # $10M+ = high institutional
                return 0.75
            elif total_volume >= 5_000_000:  # $5M+
                return 0.60
            elif total_volume >= 1_000_000:  # $1M+
                return 0.50
            elif total_volume >= 500_000:  # $500K+
                return 0.40
            elif total_volume >= 100_000:  # $100K+
                return 0.30
            elif total_volume >= 10_000:  # $10K+
                return 0.20
            else:
                return 0.15
        
        # Fallback to volume24hr if available
        if vol_24h > 0:
            if vol_24h >= 100_000:
                return 0.55
            elif vol_24h >= 50_000:
                return 0.40
            elif vol_24h >= 10_000:
                return 0.30
            else:
                return 0.20
        
        # No volume data - return low signal
        return 0.15
    
    def get_signal_summary(
        self,
        event: Dict[str, Any],
        market: Optional[Dict[str, Any]] = None,
    ) -> EnhancedSignalSummary:
        """Get all signals for an event in a summary format.
        
        Calculates all four options-like signals and provides human-readable
        interpretations for each.
        
        Args:
            event: Event dict from Polymarket API
            market: Optional market dict with price change and spread data.
                   If not provided, will try to extract from event["markets"][0]
                   
        Returns:
            EnhancedSignalSummary with all signal strengths and interpretations
            
        Example:
            >>> summary = scorer.get_signal_summary(event, market)
            >>> print(summary.to_dict())
            {
                "unusual_volume": {"strength": 0.8, "interpretation": "High unusual activity"},
                "delta_movement": {"strength": 0.5, "interpretation": "Moderate momentum"},
                ...
            }
        """
        # Try to get market data from event if not provided
        if market is None:
            markets = event.get("markets", [])
            if markets and len(markets) > 0:
                market = markets[0]
            else:
                market = {}
        
        # Calculate all signals
        unusual_vol_strength = self._unusual_volume_signal(event)
        delta_strength = self._delta_movement_signal(market, event)
        iv_strength = self._implied_volatility_proxy(market)
        smart_money_strength = self._smart_money_signal(event)
        
        # Calculate raw values for context
        vol_24h = self._safe_float(
            event.get("volume24hr") or event.get("volume_24hr"), 0
        )
        vol_1wk = self._safe_float(
            event.get("volume1wk") or event.get("volume_1wk"), 0
        )
        daily_avg = vol_1wk / 7 if vol_1wk > 0 else 0
        volume_ratio = vol_24h / daily_avg if daily_avg > 0 else 0
        
        day_change = self._safe_float(market.get("oneDayPriceChange"), 0)
        week_change = self._safe_float(market.get("oneWeekPriceChange"), 0)
        momentum = abs(day_change) * 0.6 + abs(week_change) * 0.4
        
        spread = self._safe_float(market.get("spread"), 0)
        
        open_interest = self._safe_float(
            event.get("openInterest") or event.get("open_interest"), 0
        )
        vol_oi_ratio = vol_24h / open_interest if open_interest > 0 else 0
        
        # Create signal summaries with interpretations
        unusual_volume_summary = SignalSummary(
            strength=unusual_vol_strength,
            interpretation=interpret_unusual_volume(volume_ratio),
            raw_value=volume_ratio,
        )
        
        delta_movement_summary = SignalSummary(
            strength=delta_strength,
            interpretation=interpret_delta_movement(momentum),
            raw_value=momentum,
        )
        
        iv_summary = SignalSummary(
            strength=iv_strength,
            interpretation=interpret_implied_volatility(spread),
            raw_value=spread,
        )
        
        smart_money_summary = SignalSummary(
            strength=smart_money_strength,
            interpretation=interpret_smart_money(vol_oi_ratio),
            raw_value=vol_oi_ratio,
        )
        
        # Calculate overall signal strength (weighted average)
        weights = self.enhanced_weights
        total_enhanced_weight = (
            weights.unusual_volume +
            weights.delta_movement +
            weights.implied_volatility +
            weights.smart_money_signal
        )
        
        if total_enhanced_weight > 0:
            overall_strength = (
                unusual_vol_strength * weights.unusual_volume +
                delta_strength * weights.delta_movement +
                iv_strength * weights.implied_volatility +
                smart_money_strength * weights.smart_money_signal
            ) / total_enhanced_weight
        else:
            # Equal weighting fallback
            overall_strength = (
                unusual_vol_strength +
                delta_strength +
                iv_strength +
                smart_money_strength
            ) / 4
        
        return EnhancedSignalSummary(
            unusual_volume=unusual_volume_summary,
            delta_movement=delta_movement_summary,
            implied_volatility=iv_summary,
            smart_money=smart_money_summary,
            overall_signal_strength=overall_strength,
        )
    
    def score_event_enhanced(
        self,
        event: Union[Dict[str, Any], PolymarketEvent],
        market: Optional[Dict[str, Any]] = None,
    ) -> EventScore:
        """Calculate composite score including enhanced signals.
        
        Extends the base score_event method to include options-like signals
        in the scoring calculation.
        
        Args:
            event: Event dict from Polymarket API or PolymarketEvent object
            market: Optional market dict with price change data
            
        Returns:
            EventScore with total score including enhanced signal components
        """
        # Get base score first
        base_score = self.score_event(event, market)
        
        # Convert event to dict if needed
        if isinstance(event, PolymarketEvent):
            event_dict = self._event_to_dict(event)
        else:
            event_dict = event
        
        # Get market data
        if market is None:
            markets = event_dict.get("markets", [])
            if markets and len(markets) > 0:
                market = markets[0]
            else:
                market = {}
        
        # Calculate enhanced signals (convert 0-1 to 0-100 for consistency)
        enhanced_scores = {
            "unusual_volume": self._unusual_volume_signal(event_dict) * 100,
            "delta_movement": self._delta_movement_signal(market) * 100,
            "implied_volatility": self._implied_volatility_proxy(market) * 100,
            "smart_money_signal": self._smart_money_signal(event_dict) * 100,
        }
        
        # Add enhanced scores to component scores
        base_score.component_scores.update(enhanced_scores)
        
        # Recalculate total with enhanced weights
        weights = self.enhanced_weights.to_dict()
        total_score = sum(
            base_score.component_scores.get(key, 0) * weights.get(key, 0)
            for key in weights
        )
        
        # Normalize by total weight
        total_weight = sum(weights.values())
        if total_weight > 0:
            total_score = total_score / total_weight * 100
        
        base_score.total_score = min(100, max(0, total_score))
        base_score.recommendation = EventScore.get_recommendation(base_score.total_score)
        
        return base_score


def create_enhanced_scorer(
    weights: Optional[Dict[str, float]] = None,
    enhanced_weights: Optional[Dict[str, float]] = None,
    min_score_threshold: float = 70.0,
) -> EnhancedEventScorer:
    """Factory function to create an EnhancedEventScorer with custom configuration.
    
    Args:
        weights: Optional dict of base scoring weights
        enhanced_weights: Optional dict of enhanced signal weights
        min_score_threshold: Minimum score for "analyze" recommendation
        
    Returns:
        Configured EnhancedEventScorer instance
        
    Example:
        >>> scorer = create_enhanced_scorer(
        ...     enhanced_weights={"unusual_volume": 0.15, "smart_money_signal": 0.10}
        ... )
    """
    config = ScoringConfig(min_score_threshold=min_score_threshold)
    
    if weights:
        config.weights = ScoringWeights(**weights).normalize()
    
    enhanced = None
    if enhanced_weights:
        enhanced = EnhancedScoringWeights(**enhanced_weights).normalize()
    
    return EnhancedEventScorer(config=config, enhanced_weights=enhanced)
