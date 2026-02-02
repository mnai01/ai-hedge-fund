"""Pydantic models for Polymarket event scoring.

This module defines data models for the Event Scoring Engine:
- ScoringWeights: Configurable weights for scoring components
- EventScore: Result of scoring an event
- ScoringConfig: Configuration for the scoring engine

Reference: plans/POLYMARKET_EVENT_DISCOVERY_DESIGN.md
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Literal


class ScoringWeights(BaseModel):
    """Configurable weights for event scoring components.
    
    All weights should sum to 1.0 for normalized scoring.
    Default weights are based on the design document's recommended values.
    
    Attributes:
        volume: Weight for total trading volume score (0-1)
        liquidity: Weight for current liquidity score (0-1)
        time_horizon: Weight for time to resolution score (0-1)
        category: Weight for category relevance score (0-1)
        momentum: Weight for price momentum score (0-1)
        volume_trend: Weight for volume acceleration score (0-1)
        smart_money: Weight for institutional activity proxy score (0-1)
    """
    
    volume: float = Field(default=0.25, ge=0.0, le=1.0, description="Weight for volume score")
    liquidity: float = Field(default=0.20, ge=0.0, le=1.0, description="Weight for liquidity score")
    time_horizon: float = Field(default=0.15, ge=0.0, le=1.0, description="Weight for time horizon score")
    category: float = Field(default=0.15, ge=0.0, le=1.0, description="Weight for category relevance score")
    momentum: float = Field(default=0.10, ge=0.0, le=1.0, description="Weight for momentum score")
    volume_trend: float = Field(default=0.10, ge=0.0, le=1.0, description="Weight for volume trend score")
    smart_money: float = Field(default=0.05, ge=0.0, le=1.0, description="Weight for smart money score")
    
    @property
    def total_weight(self) -> float:
        """Calculate the sum of all weights."""
        return (
            self.volume + 
            self.liquidity + 
            self.time_horizon + 
            self.category + 
            self.momentum + 
            self.volume_trend + 
            self.smart_money
        )
    
    def is_normalized(self, tolerance: float = 0.01) -> bool:
        """Check if weights sum to approximately 1.0."""
        return abs(self.total_weight - 1.0) <= tolerance
    
    def normalize(self) -> "ScoringWeights":
        """Return a new ScoringWeights with weights normalized to sum to 1.0."""
        total = self.total_weight
        if total == 0:
            return ScoringWeights()  # Return defaults if all zero
        
        return ScoringWeights(
            volume=self.volume / total,
            liquidity=self.liquidity / total,
            time_horizon=self.time_horizon / total,
            category=self.category / total,
            momentum=self.momentum / total,
            volume_trend=self.volume_trend / total,
            smart_money=self.smart_money / total,
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert weights to a dictionary."""
        return {
            "volume": self.volume,
            "liquidity": self.liquidity,
            "time_horizon": self.time_horizon,
            "category": self.category,
            "momentum": self.momentum,
            "volume_trend": self.volume_trend,
            "smart_money": self.smart_money,
        }


class EventScore(BaseModel):
    """Result of scoring a Polymarket event.
    
    Contains the total score, component scores, and recommendation
    for whether to analyze the event further.
    
    Attributes:
        event_id: Unique identifier for the event
        event_title: Title/question of the event
        total_score: Composite score from 0-100
        component_scores: Individual scores for each component
        rank: Position in ranked list (1 = highest score)
        recommendation: Action recommendation based on score
        category: Event category (if available)
        end_date: Event end date (if available)
        volume: Total trading volume
        liquidity: Current liquidity
        scored_at: Timestamp when scoring was performed
    """
    
    event_id: str = Field(..., description="Unique event identifier")
    event_title: str = Field(..., description="Event title/question")
    total_score: float = Field(..., ge=0.0, le=100.0, description="Composite score 0-100")
    component_scores: Dict[str, float] = Field(
        default_factory=dict, 
        description="Individual component scores"
    )
    rank: int = Field(default=0, ge=0, description="Position in ranked list")
    recommendation: Literal["analyze", "skip", "low_priority"] = Field(
        default="low_priority",
        description="Action recommendation"
    )
    
    # Optional metadata
    category: Optional[str] = Field(default=None, description="Event category")
    end_date: Optional[str] = Field(default=None, description="Event end date")
    volume: Optional[float] = Field(default=None, description="Total trading volume")
    liquidity: Optional[float] = Field(default=None, description="Current liquidity")
    scored_at: datetime = Field(default_factory=datetime.now, description="Scoring timestamp")
    
    @field_validator('component_scores')
    @classmethod
    def validate_component_scores(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Ensure all component scores are in valid range."""
        for key, score in v.items():
            if not 0.0 <= score <= 100.0:
                raise ValueError(f"Component score '{key}' must be between 0 and 100, got {score}")
        return v
    
    @classmethod
    def get_recommendation(cls, score: float) -> Literal["analyze", "skip", "low_priority"]:
        """Determine recommendation based on score.
        
        Args:
            score: Total score from 0-100
            
        Returns:
            Recommendation string
        """
        if score >= 70:
            return "analyze"
        elif score >= 40:
            return "low_priority"
        else:
            return "skip"
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Get a summary dictionary for display."""
        return {
            "event_id": self.event_id,
            "title": self.event_title,
            "score": round(self.total_score, 1),
            "rank": self.rank,
            "recommendation": self.recommendation,
            "category": self.category,
        }


class ScoringConfig(BaseModel):
    """Configuration for the Event Scoring Engine.
    
    Attributes:
        weights: Scoring weights for each component
        min_score_threshold: Minimum score to recommend analysis
        low_priority_threshold: Score threshold for low priority
        default_categories: Categories to include by default
        category_weights: Stock market relevance weights by category
    """
    
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    min_score_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    low_priority_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
    
    # Official Polymarket categories (10 total)
    default_categories: List[str] = Field(
        default=[
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
    )
    
    # Category weights for stock market relevance
    # Higher weight = more relevant to stock market
    category_weights: Dict[str, float] = Field(
        default={
            # High relevance - direct stock market impact
            "economy": 1.0,
            "finance": 1.0,
            "politics": 0.8,
            "tech": 0.7,
            "crypto": 0.6,
            
            # Medium relevance
            "climate-science": 0.5,
            "mentions": 0.4,
            
            # Low relevance - minimal stock impact
            "culture": 0.3,
            "sports": 0.2,
            "other": 0.3,
        }
    )
    
    def get_category_weight(self, category: Optional[str]) -> float:
        """Get the weight for a category.
        
        Args:
            category: Category name (case-insensitive)
            
        Returns:
            Weight from 0-1, defaults to 0.3 for unknown categories
        """
        if not category:
            return 0.3
        return self.category_weights.get(category.lower(), 0.3)
    
    def is_high_relevance_category(self, category: Optional[str]) -> bool:
        """Check if a category has high stock market relevance.
        
        Args:
            category: Category name
            
        Returns:
            True if category weight >= 0.7
        """
        return self.get_category_weight(category) >= 0.7


class RankedEventList(BaseModel):
    """A ranked list of scored events.
    
    Attributes:
        events: List of EventScore objects, sorted by score
        total_events: Total number of events scored
        filtered_count: Number of events after filtering
        scoring_config: Configuration used for scoring
        generated_at: Timestamp when ranking was generated
    """
    
    events: List[EventScore] = Field(default_factory=list)
    total_events: int = Field(default=0)
    filtered_count: int = Field(default=0)
    scoring_config: Optional[ScoringConfig] = Field(default=None)
    generated_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def top_events(self) -> List[EventScore]:
        """Get events recommended for analysis."""
        return [e for e in self.events if e.recommendation == "analyze"]
    
    @property
    def low_priority_events(self) -> List[EventScore]:
        """Get low priority events."""
        return [e for e in self.events if e.recommendation == "low_priority"]
    
    @property
    def skipped_events(self) -> List[EventScore]:
        """Get events recommended to skip."""
        return [e for e in self.events if e.recommendation == "skip"]
    
    def get_by_category(self, category: str) -> List[EventScore]:
        """Get events filtered by category.
        
        Args:
            category: Category name (case-insensitive)
            
        Returns:
            List of EventScore objects in the category
        """
        category_lower = category.lower()
        return [e for e in self.events if e.category and e.category.lower() == category_lower]
    
    def get_top_n(self, n: int = 10) -> List[EventScore]:
        """Get the top N scored events.
        
        Args:
            n: Number of events to return
            
        Returns:
            List of top N EventScore objects
        """
        return self.events[:n]
    
    def to_summary(self) -> Dict[str, Any]:
        """Get a summary of the ranked list."""
        return {
            "total_events": self.total_events,
            "filtered_count": self.filtered_count,
            "analyze_count": len(self.top_events),
            "low_priority_count": len(self.low_priority_events),
            "skip_count": len(self.skipped_events),
            "generated_at": self.generated_at.isoformat(),
        }


class EnhancedScoringWeights(ScoringWeights):
    """Extended scoring weights including options-like signal weights.
    
    Adds weights for enhanced signals that map Polymarket data to
    options market concepts for more sophisticated analysis.
    
    Attributes:
        unusual_volume: Weight for unusual volume activity signal (0-1)
        delta_movement: Weight for delta/probability movement signal (0-1)
        implied_volatility: Weight for IV proxy (spread-based) signal (0-1)
        smart_money_signal: Weight for smart money detection signal (0-1)
    """
    
    unusual_volume: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Weight for unusual volume signal"
    )
    delta_movement: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        description="Weight for delta movement signal"
    )
    implied_volatility: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Weight for implied volatility proxy signal"
    )
    smart_money_signal: float = Field(
        default=0.07,
        ge=0.0,
        le=1.0,
        description="Weight for smart money signal"
    )
    
    @property
    def total_weight(self) -> float:
        """Calculate the sum of all weights including enhanced signals."""
        base_weight = super().total_weight
        return (
            base_weight +
            self.unusual_volume +
            self.delta_movement +
            self.implied_volatility +
            self.smart_money_signal
        )
    
    def normalize(self) -> "EnhancedScoringWeights":
        """Return a new EnhancedScoringWeights with weights normalized to sum to 1.0."""
        total = self.total_weight
        if total == 0:
            return EnhancedScoringWeights()  # Return defaults if all zero
        
        return EnhancedScoringWeights(
            # Base weights
            volume=self.volume / total,
            liquidity=self.liquidity / total,
            time_horizon=self.time_horizon / total,
            category=self.category / total,
            momentum=self.momentum / total,
            volume_trend=self.volume_trend / total,
            smart_money=self.smart_money / total,
            # Enhanced weights
            unusual_volume=self.unusual_volume / total,
            delta_movement=self.delta_movement / total,
            implied_volatility=self.implied_volatility / total,
            smart_money_signal=self.smart_money_signal / total,
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert weights to a dictionary including enhanced signals."""
        base_dict = super().to_dict()
        base_dict.update({
            "unusual_volume": self.unusual_volume,
            "delta_movement": self.delta_movement,
            "implied_volatility": self.implied_volatility,
            "smart_money_signal": self.smart_money_signal,
        })
        return base_dict


class SignalSummary(BaseModel):
    """Summary of an options-like signal analysis.
    
    Attributes:
        strength: Signal strength from 0.0 to 1.0
        interpretation: Human-readable interpretation of the signal
        raw_value: The raw calculated value before normalization
    """
    
    strength: float = Field(..., ge=0.0, le=1.0, description="Signal strength 0-1")
    interpretation: str = Field(..., description="Human-readable interpretation")
    raw_value: Optional[float] = Field(default=None, description="Raw calculated value")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strength": self.strength,
            "interpretation": self.interpretation,
            "raw_value": self.raw_value,
        }


class EnhancedSignalSummary(BaseModel):
    """Complete summary of all enhanced signals for an event.
    
    Attributes:
        unusual_volume: Unusual volume activity signal
        delta_movement: Delta/probability movement signal
        implied_volatility: Implied volatility proxy signal
        smart_money: Smart money detection signal
        overall_signal_strength: Average of all signal strengths
    """
    
    unusual_volume: SignalSummary = Field(..., description="Unusual volume signal")
    delta_movement: SignalSummary = Field(..., description="Delta movement signal")
    implied_volatility: SignalSummary = Field(..., description="IV proxy signal")
    smart_money: SignalSummary = Field(..., description="Smart money signal")
    overall_signal_strength: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Average signal strength"
    )
    
    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert to dictionary format."""
        return {
            "unusual_volume": self.unusual_volume.to_dict(),
            "delta_movement": self.delta_movement.to_dict(),
            "implied_volatility": self.implied_volatility.to_dict(),
            "smart_money": self.smart_money.to_dict(),
            "overall_signal_strength": self.overall_signal_strength,
        }
