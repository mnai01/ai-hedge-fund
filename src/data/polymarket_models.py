"""Pydantic models for Polymarket data structures.

This module defines data models for:
- Events and markets from the Gamma API
- Price history from the CLOB API
- LLM-generated stock mappings
- Probability change tracking
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Literal


def parse_json_string_list(v: Any) -> Optional[List[str]]:
    """Parse a JSON string that contains a list, or return the list as-is."""
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


class PolymarketOutcome(BaseModel):
    """Represents an outcome/option within a market."""
    
    outcome: str
    outcome_price: Optional[float] = Field(None, alias="outcomePrices")
    
    class Config:
        populate_by_name = True


class PolymarketMarket(BaseModel):
    """Represents a market within a Polymarket event.
    
    A market is a specific question/prediction within an event.
    For example, an event about "2024 US Election" might have markets
    for "Will Biden win?" and "Will Trump win?"
    """
    
    id: str
    question: str
    condition_id: Optional[str] = Field(None, alias="conditionId")
    slug: Optional[str] = None
    end_date: Optional[str] = Field(None, alias="endDate")
    description: Optional[str] = None
    outcomes: Optional[List[str]] = None
    outcome_prices: Optional[List[str]] = Field(None, alias="outcomePrices")
    volume: Optional[float] = None
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    liquidity: Optional[float] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    
    # Token IDs for CLOB API price history
    clob_token_ids: Optional[List[str]] = Field(None, alias="clobTokenIds")
    
    class Config:
        populate_by_name = True
    
    @field_validator('outcomes', 'outcome_prices', 'clob_token_ids', mode='before')
    @classmethod
    def parse_json_string_lists(cls, v):
        """Parse JSON string lists from API response."""
        return parse_json_string_list(v)
    
    @property
    def primary_probability(self) -> Optional[float]:
        """Get the probability of the first outcome (typically 'Yes')."""
        if self.outcome_prices and len(self.outcome_prices) > 0:
            try:
                return float(self.outcome_prices[0])
            except (ValueError, TypeError):
                return None
        return None
    
    @property
    def primary_token_id(self) -> Optional[str]:
        """Get the primary token ID for price history queries."""
        if self.clob_token_ids and len(self.clob_token_ids) > 0:
            return self.clob_token_ids[0]
        return None


class PolymarketEvent(BaseModel):
    """Represents a Polymarket event containing one or more markets.
    
    Events are the top-level containers that group related markets.
    For example, "2024 US Presidential Election" is an event that
    contains multiple markets about different outcomes.
    """
    
    id: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = Field(None, alias="startDate")
    end_date: Optional[str] = Field(None, alias="endDate")
    volume: Optional[float] = None
    volume_24hr: Optional[float] = Field(None, alias="volume24hr")
    liquidity: Optional[float] = None
    markets: Optional[List[PolymarketMarket]] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    
    # Tags for categorization
    tags: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        populate_by_name = True
    
    @property
    def probability(self) -> Optional[float]:
        """Get the primary probability from the first market."""
        if self.markets and len(self.markets) > 0:
            return self.markets[0].primary_probability
        return None
    
    @property
    def primary_market(self) -> Optional[PolymarketMarket]:
        """Get the primary (first) market for this event."""
        if self.markets and len(self.markets) > 0:
            return self.markets[0]
        return None
    
    @property
    def category(self) -> Optional[str]:
        """Extract category from tags if available.
        
        Uses intelligent mapping to convert tag labels to official categories.
        For example, "Jerome Powell" maps to "Economy", "Trump" maps to "Politics".
        """
        if not self.tags:
            return None
        
        # Official Polymarket categories
        OFFICIAL_CATEGORIES = {
            "politics", "crypto", "economy", "finance", "tech",
            "sports", "culture", "climate-science", "mentions", "other",
            "world elections", "elections", "basketball", "football",
            "baseball", "hockey", "soccer", "mma", "golf", "tennis",
            "entertainment", "science", "health", "business",
        }
        
        # Mapping from common tag labels to official categories
        CATEGORY_MAPPING = {
            # Politics
            "world elections": "politics",
            "trump": "politics",
            "biden": "politics",
            "harris": "politics",
            "congress": "politics",
            "senate": "politics",
            "house": "politics",
            "supreme court": "politics",
            "government": "politics",
            "election": "politics",
            "elections": "politics",
            "president": "politics",
            "presidential": "politics",
            "democrat": "politics",
            "republican": "politics",
            "gop": "politics",
            "dnc": "politics",
            "rnc": "politics",
            "white house": "politics",
            "cabinet": "politics",
            "impeachment": "politics",
            "legislation": "politics",
            "policy": "politics",
            "geopolitics": "politics",
            "war": "politics",
            "military": "politics",
            "nato": "politics",
            "un": "politics",
            "china": "politics",
            "russia": "politics",
            "ukraine": "politics",
            "iran": "politics",
            "israel": "politics",
            "middle east": "politics",
            "europe": "politics",
            "asia": "politics",
            "macron": "politics",
            "uk": "politics",
            "brexit": "politics",
            
            # Economy
            "fed": "economy",
            "federal reserve": "economy",
            "interest rates": "economy",
            "inflation": "economy",
            "gdp": "economy",
            "unemployment": "economy",
            "recession": "economy",
            "economy": "economy",
            "economic": "economy",
            "monetary policy": "economy",
            "fiscal": "economy",
            "treasury": "economy",
            "bonds": "economy",
            "yield": "economy",
            "cpi": "economy",
            "ppi": "economy",
            "jobs": "economy",
            "employment": "economy",
            "labor": "economy",
            "jerome powell": "economy",
            "yellen": "economy",
            "central bank": "economy",
            
            # Crypto
            "bitcoin": "crypto",
            "btc": "crypto",
            "ethereum": "crypto",
            "eth": "crypto",
            "crypto": "crypto",
            "cryptocurrency": "crypto",
            "blockchain": "crypto",
            "defi": "crypto",
            "nft": "crypto",
            "solana": "crypto",
            "sol": "crypto",
            "dogecoin": "crypto",
            "doge": "crypto",
            "xrp": "crypto",
            "ripple": "crypto",
            "binance": "crypto",
            "coinbase": "crypto",
            "kraken": "crypto",
            "microstrategy": "crypto",
            
            # Sports
            "nba": "sports",
            "nfl": "sports",
            "mlb": "sports",
            "nhl": "sports",
            "mls": "sports",
            "ufc": "sports",
            "pga": "sports",
            "atp": "sports",
            "wta": "sports",
            "super bowl": "sports",
            "world series": "sports",
            "stanley cup": "sports",
            "march madness": "sports",
            "olympics": "sports",
            "world cup": "sports",
            "premier league": "sports",
            "champions league": "sports",
            "formula 1": "sports",
            "f1": "sports",
            "nascar": "sports",
            
            # Tech
            "ai": "tech",
            "artificial intelligence": "tech",
            "openai": "tech",
            "chatgpt": "tech",
            "google": "tech",
            "apple": "tech",
            "microsoft": "tech",
            "amazon": "tech",
            "meta": "tech",
            "facebook": "tech",
            "twitter": "tech",
            "x": "tech",
            "elon musk": "tech",
            "tesla": "tech",
            "spacex": "tech",
            "nvidia": "tech",
            "semiconductor": "tech",
            "chips": "tech",
            
            # Finance
            "stock": "finance",
            "stocks": "finance",
            "market": "finance",
            "markets": "finance",
            "s&p": "finance",
            "nasdaq": "finance",
            "dow": "finance",
            "ipo": "finance",
            "earnings": "finance",
            "merger": "finance",
            "acquisition": "finance",
            "hedge fund": "finance",
            "wall street": "finance",
            "sec": "finance",
            
            # Entertainment/Culture
            "oscars": "culture",
            "emmys": "culture",
            "grammys": "culture",
            "movie": "culture",
            "film": "culture",
            "music": "culture",
            "celebrity": "culture",
            "hollywood": "culture",
            "streaming": "culture",
            "netflix": "culture",
            "disney": "culture",
            "entertainment": "culture",
        }
        
        # First pass: look for official categories directly
        for tag in self.tags:
            if isinstance(tag, dict):
                label = tag.get("label", "").lower()
                if label in OFFICIAL_CATEGORIES:
                    return tag.get("label")  # Return original case
        
        # Second pass: map known tags to categories
        for tag in self.tags:
            if isinstance(tag, dict):
                label = tag.get("label", "").lower()
                if label in CATEGORY_MAPPING:
                    return CATEGORY_MAPPING[label].title()  # Return title case
        
        # Fallback: return first tag label if nothing else matches
        for tag in self.tags:
            if isinstance(tag, dict) and tag.get("label"):
                return tag["label"]
        
        return None


class PolymarketEventsResponse(BaseModel):
    """Response wrapper for Gamma API events endpoint."""
    
    events: List[PolymarketEvent] = Field(default_factory=list)


class PricePoint(BaseModel):
    """A single price/probability point in time."""
    
    timestamp: int = Field(alias="t")
    probability: float = Field(alias="p")
    
    class Config:
        populate_by_name = True
    
    @property
    def datetime(self) -> datetime:
        """Convert Unix timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp)
    
    @property
    def time_str(self) -> str:
        """Get ISO format timestamp string."""
        return self.datetime.isoformat()


class PriceHistory(BaseModel):
    """Historical price/probability data for a market.
    
    Retrieved from the CLOB API prices-history endpoint.
    """
    
    market_id: str
    token_id: str
    history: List[PricePoint] = Field(default_factory=list)
    
    @property
    def latest_probability(self) -> Optional[float]:
        """Get the most recent probability."""
        if self.history:
            return self.history[-1].probability
        return None
    
    @property
    def earliest_probability(self) -> Optional[float]:
        """Get the earliest probability in the history."""
        if self.history:
            return self.history[0].probability
        return None
    
    def get_probability_at(self, timestamp: int) -> Optional[float]:
        """Get probability closest to a given timestamp."""
        if not self.history:
            return None
        
        closest = min(self.history, key=lambda p: abs(p.timestamp - timestamp))
        return closest.probability
    
    def get_probability_change(self, hours: int = 24) -> Optional[float]:
        """Calculate probability change over the last N hours."""
        if len(self.history) < 2:
            return None
        
        current = self.history[-1]
        target_time = current.timestamp - (hours * 3600)
        
        # Find the closest point to target_time
        past = min(self.history, key=lambda p: abs(p.timestamp - target_time))
        
        return current.probability - past.probability


class PriceHistoryResponse(BaseModel):
    """Response wrapper for CLOB API prices-history endpoint."""
    
    history: List[Dict[str, Any]] = Field(default_factory=list)


class ProbabilityChange(BaseModel):
    """Represents a significant probability change for an event."""
    
    event_id: str
    event_title: str
    market_id: str
    market_question: str
    previous_probability: float
    current_probability: float
    change: float
    change_percent: float
    direction: Literal["up", "down"]
    detected_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def is_significant(self) -> bool:
        """Check if the change is significant (>5%)."""
        return abs(self.change) > 0.05


class EventStockImpact(BaseModel):
    """LLM-generated mapping of an event to affected stocks.
    
    This model captures the relationship between a Polymarket event
    and stocks that may be affected by its outcome.
    """
    
    ticker: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(ge=0, le=100, description="Confidence score 0-100")
    reasoning: str
    sources: List[str] = Field(default_factory=list)
    
    @property
    def signal(self) -> str:
        """Convert direction to signal format used by other agents."""
        return self.direction


class EventStockMapping(BaseModel):
    """Complete mapping of an event to all affected stocks.
    
    Generated by the LLM to identify which stocks are affected
    by a Polymarket event and how.
    """
    
    event_id: str
    event_title: str
    event_description: Optional[str] = None
    current_probability: float
    probability_direction: Literal["up", "down", "stable"]
    affected_stocks: List[EventStockImpact] = Field(default_factory=list)
    analysis_timestamp: datetime = Field(default_factory=datetime.now)
    model_used: Optional[str] = None
    
    def get_impact_for_ticker(self, ticker: str) -> Optional[EventStockImpact]:
        """Get the impact analysis for a specific ticker."""
        for impact in self.affected_stocks:
            if impact.ticker.upper() == ticker.upper():
                return impact
        return None
    
    def get_bullish_tickers(self) -> List[str]:
        """Get all tickers with bullish impact."""
        return [s.ticker for s in self.affected_stocks if s.direction == "bullish"]
    
    def get_bearish_tickers(self) -> List[str]:
        """Get all tickers with bearish impact."""
        return [s.ticker for s in self.affected_stocks if s.direction == "bearish"]


class PolymarketAnalysis(BaseModel):
    """Analysis result for a single ticker from Polymarket events.
    
    This matches the output format expected by other agents in the system.
    """
    
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0, le=100)
    reasoning: Dict[str, Any]
    
    class Config:
        extra = "allow"


class PolymarketTradeDecision(BaseModel):
    """A trade decision based on Polymarket analysis.
    
    Used for backtesting and tracking decision history.
    """
    
    ticker: str
    event_id: str
    event_title: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    probability_at_decision: float
    probability_change: float
    decision_timestamp: datetime = Field(default_factory=datetime.now)
    reasoning: str
    
    # For backtesting
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    profit_loss: Optional[float] = None
    profit_loss_percent: Optional[float] = None


class BacktestResult(BaseModel):
    """Results from backtesting Polymarket-based trading strategy."""
    
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_percent: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    average_profit: float
    average_loss: float
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    
    # Detailed trade history
    trades: List[PolymarketTradeDecision] = Field(default_factory=list)
    
    # Event correlation analysis
    event_correlations: Dict[str, float] = Field(default_factory=dict)


# Cache-related models for SQLite persistence

class CachedEvent(BaseModel):
    """Event data stored in SQLite cache."""
    
    event_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    active: bool = True
    closed: bool = False
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    first_seen: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)


class CachedProbability(BaseModel):
    """Probability snapshot stored in SQLite cache."""
    
    event_id: str
    market_id: str
    probability: float
    timestamp: datetime = Field(default_factory=datetime.now)


class CachedStockMapping(BaseModel):
    """Stock mapping stored in SQLite cache."""
    
    event_id: str
    ticker: str
    direction: str
    confidence: int
    reasoning: str
    sources: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
