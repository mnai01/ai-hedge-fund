"""Event Portfolio Management for Polymarket-driven trading.

This module implements industry-standard event filtering and deduplication:
1. Entry signal checking (before expensive LLM calls)
2. Event portfolio tracking (active exposures)
3. Fuzzy title matching (fast deduplication)
4. Embedding similarity (semantic deduplication)
5. LLM confirmation (edge cases)

Key principle: Filter cheap before expensive.
- Check entry potential BEFORE stock discovery
- Use fuzzy matching BEFORE embeddings
- Use embeddings BEFORE LLM confirmation
"""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple, Literal
from pydantic import BaseModel, Field
from enum import Enum
import hashlib
import json
import os

from src.data.polymarket_models import PolymarketEvent, PriceHistory


# =============================================================================
# Entry Signal Checking
# =============================================================================

def has_entry_potential(
    price_history: PriceHistory,
    threshold: float = 0.70,
    mode: Literal["backtest", "live"] = "backtest",
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check if an event has entry potential based on probability threshold.
    
    For BACKTEST mode: Check if probability EVER crossed threshold historically.
    For LIVE mode: Check if CURRENT probability is above threshold.
    
    Args:
        price_history: Historical probability data for the event
        threshold: Minimum probability to trigger entry (default: 70%)
        mode: "backtest" or "live"
        
    Returns:
        Tuple of (has_potential, entry_date, entry_probability)
        - has_potential: True if entry signal exists
        - entry_date: Date when threshold was first crossed (backtest) or None (live)
        - entry_probability: Probability at entry point
        
    Example:
        >>> has_potential, entry_date, entry_prob = has_entry_potential(history, 0.70)
        >>> if has_potential:
        ...     print(f"Entry signal on {entry_date} at {entry_prob:.1%}")
    """
    if not price_history or not price_history.history:
        return False, None, None
    
    if mode == "live":
        # Live mode: check current probability
        current_prob = price_history.latest_probability
        if current_prob and current_prob >= threshold:
            return True, None, current_prob
        return False, None, None
    
    # Backtest mode: find first date probability crossed threshold
    for point in price_history.history:
        prob = point.probability
        if prob >= threshold:
            entry_date = point.datetime.strftime("%Y-%m-%d")
            return True, entry_date, prob
    
    return False, None, None


def get_entry_signal_summary(
    price_history: PriceHistory,
    threshold: float = 0.70,
) -> Dict[str, Any]:
    """
    Get detailed summary of entry signal potential.
    
    Returns:
        Dict with:
        - has_entry: Whether entry signal exists
        - first_cross_date: First date threshold was crossed
        - first_cross_prob: Probability at first crossing
        - max_prob: Maximum probability reached
        - max_prob_date: Date of maximum probability
        - current_prob: Current/latest probability
        - days_above_threshold: Number of days above threshold
    """
    if not price_history or not price_history.history:
        return {
            "has_entry": False,
            "first_cross_date": None,
            "first_cross_prob": None,
            "max_prob": None,
            "max_prob_date": None,
            "current_prob": None,
            "days_above_threshold": 0,
        }
    
    first_cross_date = None
    first_cross_prob = None
    max_prob = 0.0
    max_prob_date = None
    days_above = 0
    
    for point in price_history.history:
        prob = point.probability
        date_str = point.datetime.strftime("%Y-%m-%d")
        
        # Track first crossing
        if prob >= threshold and first_cross_date is None:
            first_cross_date = date_str
            first_cross_prob = prob
        
        # Track max probability
        if prob > max_prob:
            max_prob = prob
            max_prob_date = date_str
        
        # Count days above threshold
        if prob >= threshold:
            days_above += 1
    
    return {
        "has_entry": first_cross_date is not None,
        "first_cross_date": first_cross_date,
        "first_cross_prob": first_cross_prob,
        "max_prob": max_prob,
        "max_prob_date": max_prob_date,
        "current_prob": price_history.latest_probability,
        "days_above_threshold": days_above,
    }


# =============================================================================
# Event Exposure Tracking
# =============================================================================

class EventExposure(BaseModel):
    """Represents exposure to a single Polymarket event."""
    
    event_id: str = Field(..., description="Polymarket event ID")
    event_title: str = Field(..., description="Event title for display")
    event_slug: str = Field(..., description="Event slug for API calls")
    
    # Affected stocks
    tickers: List[str] = Field(default_factory=list, description="Stocks affected by this event")
    directions: Dict[str, str] = Field(default_factory=dict, description="ticker -> 'bullish'/'bearish'")
    
    # Entry info
    entry_date: str = Field(..., description="Date exposure was added")
    entry_probability: float = Field(..., description="Probability at entry")
    
    # Current state
    is_active: bool = Field(default=True, description="Whether exposure is still active")
    resolved_date: Optional[str] = Field(None, description="Date event resolved")
    resolved_outcome: Optional[str] = Field(None, description="'Yes' or 'No'")
    
    # Metadata
    category: Optional[str] = Field(None, description="Event category")
    end_date: Optional[str] = Field(None, description="Expected resolution date")
    
    # For deduplication
    title_hash: str = Field(default="", description="Hash of normalized title for fast lookup")
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.title_hash:
            self.title_hash = self._compute_title_hash(self.event_title)
    
    @staticmethod
    def _compute_title_hash(title: str) -> str:
        """Compute hash of normalized title for fast deduplication."""
        normalized = title.lower().strip()
        # Remove common words that don't affect meaning
        for word in ["will", "the", "be", "a", "an", "in", "on", "at", "to", "for", "of", "?"]:
            normalized = normalized.replace(f" {word} ", " ")
        normalized = " ".join(normalized.split())  # Normalize whitespace
        return hashlib.md5(normalized.encode()).hexdigest()[:16]


class EventPortfolio(BaseModel):
    """
    Portfolio of active event exposures for deduplication and tracking.
    
    This class maintains a record of all events the system is currently
    exposed to, enabling:
    1. Fast duplicate detection (same event ID)
    2. Fuzzy title matching (similar events)
    3. Ticker overlap detection (same stocks affected)
    4. Portfolio-wide risk assessment
    """
    
    # Active exposures by event ID
    exposures: Dict[str, EventExposure] = Field(
        default_factory=dict,
        description="event_id -> EventExposure"
    )
    
    # Index for fast ticker lookup
    ticker_to_events: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="ticker -> [event_ids]"
    )
    
    # Index for fast title hash lookup
    title_hash_to_events: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="title_hash -> [event_ids]"
    )
    
    # Configuration
    fuzzy_threshold: float = Field(
        default=0.75,
        description="Minimum similarity score for fuzzy title match"
    )
    
    ticker_overlap_threshold: float = Field(
        default=0.80,
        description="Minimum ticker overlap to consider events similar"
    )
    
    def add_exposure(self, exposure: EventExposure) -> bool:
        """
        Add a new event exposure to the portfolio.
        
        Returns:
            True if added successfully, False if duplicate detected
        """
        # Check for exact duplicate
        if exposure.event_id in self.exposures:
            return False
        
        # Add to main index
        self.exposures[exposure.event_id] = exposure
        
        # Update ticker index
        for ticker in exposure.tickers:
            if ticker not in self.ticker_to_events:
                self.ticker_to_events[ticker] = []
            self.ticker_to_events[ticker].append(exposure.event_id)
        
        # Update title hash index
        if exposure.title_hash not in self.title_hash_to_events:
            self.title_hash_to_events[exposure.title_hash] = []
        self.title_hash_to_events[exposure.title_hash].append(exposure.event_id)
        
        return True
    
    def remove_exposure(self, event_id: str) -> bool:
        """Remove an event exposure from the portfolio."""
        if event_id not in self.exposures:
            return False
        
        exposure = self.exposures[event_id]
        
        # Remove from ticker index
        for ticker in exposure.tickers:
            if ticker in self.ticker_to_events:
                self.ticker_to_events[ticker] = [
                    eid for eid in self.ticker_to_events[ticker] if eid != event_id
                ]
                if not self.ticker_to_events[ticker]:
                    del self.ticker_to_events[ticker]
        
        # Remove from title hash index
        if exposure.title_hash in self.title_hash_to_events:
            self.title_hash_to_events[exposure.title_hash] = [
                eid for eid in self.title_hash_to_events[exposure.title_hash] if eid != event_id
            ]
            if not self.title_hash_to_events[exposure.title_hash]:
                del self.title_hash_to_events[exposure.title_hash]
        
        # Remove from main index
        del self.exposures[event_id]
        
        return True
    
    def mark_resolved(
        self,
        event_id: str,
        outcome: str,
        resolved_date: Optional[str] = None,
    ) -> bool:
        """Mark an event as resolved."""
        if event_id not in self.exposures:
            return False
        
        exposure = self.exposures[event_id]
        exposure.is_active = False
        exposure.resolved_outcome = outcome
        exposure.resolved_date = resolved_date or datetime.now().strftime("%Y-%m-%d")
        
        return True
    
    def is_duplicate(self, event: PolymarketEvent) -> Tuple[bool, Optional[str], str]:
        """
        Check if an event is a duplicate of an existing exposure.
        
        Returns:
            Tuple of (is_duplicate, matching_event_id, reason)
        """
        # 1. Check exact event ID match
        if event.id in self.exposures:
            return True, event.id, "exact_id_match"
        
        # 2. Check title hash match (fast)
        title_hash = EventExposure._compute_title_hash(event.title)
        if title_hash in self.title_hash_to_events:
            matching_ids = self.title_hash_to_events[title_hash]
            if matching_ids:
                return True, matching_ids[0], "title_hash_match"
        
        # 3. Check fuzzy title match (slower but catches variations)
        for existing_id, existing in self.exposures.items():
            if not existing.is_active:
                continue
            
            similarity = fuzzy_title_match(event.title, existing.event_title)
            if similarity >= self.fuzzy_threshold:
                return True, existing_id, f"fuzzy_match_{similarity:.2f}"
        
        return False, None, "not_duplicate"
    
    def get_ticker_exposure(self, ticker: str) -> List[EventExposure]:
        """Get all active exposures for a ticker."""
        if ticker not in self.ticker_to_events:
            return []
        
        return [
            self.exposures[eid]
            for eid in self.ticker_to_events[ticker]
            if eid in self.exposures and self.exposures[eid].is_active
        ]
    
    def get_active_exposures(self) -> List[EventExposure]:
        """Get all active event exposures."""
        return [e for e in self.exposures.values() if e.is_active]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get portfolio summary statistics."""
        active = self.get_active_exposures()
        all_tickers = set()
        for exp in active:
            all_tickers.update(exp.tickers)
        
        return {
            "total_exposures": len(self.exposures),
            "active_exposures": len(active),
            "resolved_exposures": len(self.exposures) - len(active),
            "unique_tickers": len(all_tickers),
            "tickers": sorted(all_tickers),
        }


# =============================================================================
# Fuzzy Title Matching
# =============================================================================

def normalize_title(title: str) -> str:
    """
    Normalize event title for comparison.
    
    - Lowercase
    - Remove punctuation
    - Remove common words
    - Normalize whitespace
    """
    import re
    
    # Lowercase
    normalized = title.lower()
    
    # Remove punctuation except hyphens
    normalized = re.sub(r'[^\w\s-]', '', normalized)
    
    # Remove common words that don't affect meaning
    stop_words = {
        "will", "the", "be", "a", "an", "in", "on", "at", "to", "for", "of",
        "by", "is", "are", "was", "were", "been", "being", "have", "has",
        "had", "do", "does", "did", "doing", "would", "could", "should",
        "may", "might", "must", "shall", "can", "need", "dare", "ought",
        "used", "and", "but", "or", "nor", "so", "yet", "both", "either",
        "neither", "not", "only", "own", "same", "than", "too", "very",
    }
    
    words = normalized.split()
    words = [w for w in words if w not in stop_words]
    
    # Normalize whitespace
    normalized = " ".join(words)
    
    return normalized


def fuzzy_title_match(title1: str, title2: str) -> float:
    """
    Calculate fuzzy similarity between two event titles.
    
    Uses SequenceMatcher for string similarity after normalization.
    
    Args:
        title1: First event title
        title2: Second event title
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)
    
    # Use SequenceMatcher for similarity
    return SequenceMatcher(None, norm1, norm2).ratio()


def find_similar_events(
    event: PolymarketEvent,
    candidates: List[PolymarketEvent],
    threshold: float = 0.75,
) -> List[Tuple[PolymarketEvent, float]]:
    """
    Find events similar to the given event.
    
    Args:
        event: Event to compare against
        candidates: List of candidate events
        threshold: Minimum similarity score
        
    Returns:
        List of (similar_event, similarity_score) tuples, sorted by score descending
    """
    similar = []
    
    for candidate in candidates:
        if candidate.id == event.id:
            continue
        
        similarity = fuzzy_title_match(event.title, candidate.title)
        if similarity >= threshold:
            similar.append((candidate, similarity))
    
    # Sort by similarity descending
    similar.sort(key=lambda x: x[1], reverse=True)
    
    return similar


# =============================================================================
# Embedding Similarity (Optional - requires sentence-transformers)
# =============================================================================

_embedding_model = None


def get_embedding_model():
    """
    Lazy-load the embedding model.
    
    Uses sentence-transformers if available, otherwise returns None.
    """
    global _embedding_model
    
    if _embedding_model is not None:
        return _embedding_model
    
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return _embedding_model
    except ImportError:
        return None


def compute_embedding(text: str) -> Optional[List[float]]:
    """
    Compute embedding vector for text.
    
    Returns None if sentence-transformers is not installed.
    """
    model = get_embedding_model()
    if model is None:
        return None
    
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    import math
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def embedding_similarity(title1: str, title2: str) -> Optional[float]:
    """
    Calculate semantic similarity using embeddings.
    
    Returns None if sentence-transformers is not installed.
    """
    emb1 = compute_embedding(title1)
    emb2 = compute_embedding(title2)
    
    if emb1 is None or emb2 is None:
        return None
    
    return cosine_similarity(emb1, emb2)


def find_semantically_similar_events(
    event: PolymarketEvent,
    candidates: List[PolymarketEvent],
    threshold: float = 0.85,
) -> List[Tuple[PolymarketEvent, float]]:
    """
    Find semantically similar events using embeddings.
    
    Falls back to fuzzy matching if embeddings are not available.
    """
    model = get_embedding_model()
    
    if model is None:
        # Fall back to fuzzy matching
        return find_similar_events(event, candidates, threshold=threshold - 0.10)
    
    event_embedding = compute_embedding(event.title)
    if event_embedding is None:
        return []
    
    similar = []
    
    for candidate in candidates:
        if candidate.id == event.id:
            continue
        
        candidate_embedding = compute_embedding(candidate.title)
        if candidate_embedding is None:
            continue
        
        similarity = cosine_similarity(event_embedding, candidate_embedding)
        if similarity >= threshold:
            similar.append((candidate, similarity))
    
    # Sort by similarity descending
    similar.sort(key=lambda x: x[1], reverse=True)
    
    return similar


# =============================================================================
# LLM Confirmation (for edge cases)
# =============================================================================

class DuplicateCheckResponse(BaseModel):
    """LLM response for duplicate event check."""
    
    is_duplicate: bool = Field(
        ...,
        description="True if the events are essentially the same"
    )
    
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description="Confidence in the assessment (0-100)"
    )
    
    reasoning: str = Field(
        ...,
        description="Brief explanation of why events are/aren't duplicates"
    )
    
    relationship: Literal["identical", "subset", "superset", "related", "unrelated"] = Field(
        ...,
        description="Relationship between the events"
    )


def llm_confirm_duplicate(
    event1_title: str,
    event1_description: str,
    event2_title: str,
    event2_description: str,
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
) -> Optional[DuplicateCheckResponse]:
    """
    Use LLM to confirm if two events are duplicates.
    
    This is the most expensive check and should only be used for edge cases
    where fuzzy matching and embeddings are inconclusive.
    """
    try:
        from src.llm.models import get_model
        
        llm = get_model(model_name, model_provider)
        if llm is None:
            return None
        
        # Use structured output
        structured_llm = llm.with_structured_output(DuplicateCheckResponse)
        
        prompt = f"""You are analyzing two Polymarket events to determine if they are duplicates.

EVENT 1:
Title: {event1_title}
Description: {event1_description[:500] if event1_description else 'No description'}

EVENT 2:
Title: {event2_title}
Description: {event2_description[:500] if event2_description else 'No description'}

QUESTION: Are these events essentially the same (duplicates)?

Consider:
1. Do they ask about the same outcome?
2. Do they have the same resolution criteria?
3. Would the same real-world event resolve both?

Examples of DUPLICATES:
- "Presidential Election Winner 2024" vs "Who will be inaugurated as President?"
- "Will Bitcoin hit $100k?" vs "BTC to $100,000 by end of year"

Examples of NOT DUPLICATES:
- "Presidential Election Winner 2024" vs "Senate Control 2024"
- "Will Bitcoin hit $100k?" vs "Will Ethereum hit $10k?"

Respond with your assessment."""

        response = structured_llm.invoke(prompt)
        return response
        
    except Exception as e:
        print(f"[WARN] LLM duplicate check failed: {e}")
        return None


# =============================================================================
# Combined Deduplication Pipeline
# =============================================================================

class DeduplicationResult(BaseModel):
    """Result of the deduplication check."""
    
    is_duplicate: bool = Field(..., description="Whether event is a duplicate")
    matching_event_id: Optional[str] = Field(None, description="ID of matching event if duplicate")
    matching_event_title: Optional[str] = Field(None, description="Title of matching event")
    method: str = Field(..., description="Method that detected duplicate")
    similarity_score: Optional[float] = Field(None, description="Similarity score if applicable")
    confidence: int = Field(default=100, description="Confidence in the result")


def check_duplicate(
    event: PolymarketEvent,
    portfolio: EventPortfolio,
    use_embeddings: bool = True,
    use_llm: bool = False,
    llm_threshold: float = 0.70,
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    verbose: bool = False,
) -> DeduplicationResult:
    """
    Run the full deduplication pipeline.
    
    Pipeline order (cheap to expensive):
    1. Exact ID match (instant)
    2. Title hash match (instant)
    3. Fuzzy title match (fast)
    4. Embedding similarity (medium) - optional
    5. LLM confirmation (slow) - optional, for edge cases
    
    Args:
        event: Event to check
        portfolio: Current event portfolio
        use_embeddings: Whether to use embedding similarity
        use_llm: Whether to use LLM for edge cases
        llm_threshold: Similarity threshold to trigger LLM confirmation
        model_name: LLM model name
        model_provider: LLM provider
        verbose: Print debug output
        
    Returns:
        DeduplicationResult with duplicate status and details
    """
    # 1. Check portfolio for exact match or fuzzy match
    is_dup, matching_id, reason = portfolio.is_duplicate(event)
    
    if is_dup:
        matching_exposure = portfolio.exposures.get(matching_id)
        return DeduplicationResult(
            is_duplicate=True,
            matching_event_id=matching_id,
            matching_event_title=matching_exposure.event_title if matching_exposure else None,
            method=reason,
            confidence=100 if "exact" in reason else 90,
        )
    
    # 2. Check embedding similarity if enabled
    if use_embeddings:
        active_exposures = portfolio.get_active_exposures()
        
        for exposure in active_exposures:
            similarity = embedding_similarity(event.title, exposure.event_title)
            
            if similarity is not None and similarity >= 0.85:
                if verbose:
                    print(f"   [DEBUG] Embedding similarity {similarity:.2f} with '{exposure.event_title[:50]}...'")
                
                # High similarity - likely duplicate
                if similarity >= 0.95:
                    return DeduplicationResult(
                        is_duplicate=True,
                        matching_event_id=exposure.event_id,
                        matching_event_title=exposure.event_title,
                        method="embedding_similarity",
                        similarity_score=similarity,
                        confidence=95,
                    )
                
                # Medium-high similarity - use LLM if enabled
                if use_llm and similarity >= llm_threshold:
                    llm_result = llm_confirm_duplicate(
                        event.title,
                        event.description or "",
                        exposure.event_title,
                        "",  # We don't store descriptions in exposures
                        model_name=model_name,
                        model_provider=model_provider,
                    )
                    
                    if llm_result and llm_result.is_duplicate:
                        return DeduplicationResult(
                            is_duplicate=True,
                            matching_event_id=exposure.event_id,
                            matching_event_title=exposure.event_title,
                            method="llm_confirmation",
                            similarity_score=similarity,
                            confidence=llm_result.confidence,
                        )
    
    # Not a duplicate
    return DeduplicationResult(
        is_duplicate=False,
        method="passed_all_checks",
        confidence=100,
    )


# =============================================================================
# Event Filtering Pipeline
# =============================================================================

class FilteredEvent(BaseModel):
    """Event that passed all filters."""
    
    event: Dict[str, Any] = Field(..., description="Event data")
    score: float = Field(..., description="Event score")
    relevance: str = Field(..., description="Stock market relevance")
    entry_potential: bool = Field(..., description="Has entry signal potential")
    entry_date: Optional[str] = Field(None, description="First entry date if applicable")
    entry_probability: Optional[float] = Field(None, description="Probability at entry")


def filter_events_pipeline(
    events: List[PolymarketEvent],
    portfolio: EventPortfolio,
    price_histories: Dict[str, PriceHistory],
    min_probability_threshold: float = 0.70,
    use_embeddings: bool = True,
    verbose: bool = False,
) -> Tuple[List[FilteredEvent], Dict[str, Any]]:
    """
    Run the full event filtering pipeline.
    
    Pipeline stages:
    1. Entry signal check (skip events that can never trigger)
    2. Deduplication (skip events already in portfolio)
    
    Args:
        events: List of candidate events
        portfolio: Current event portfolio
        price_histories: Dict of event_id -> PriceHistory
        min_probability_threshold: Minimum probability for entry
        use_embeddings: Whether to use embedding similarity for dedup
        verbose: Print debug output
        
    Returns:
        Tuple of (filtered_events, filter_stats)
    """
    stats = {
        "total_input": len(events),
        "filtered_no_entry": 0,
        "filtered_duplicate": 0,
        "passed": 0,
    }
    
    filtered = []
    
    for event in events:
        event_id = event.id
        
        # 1. Check entry potential
        price_history = price_histories.get(event_id)
        if price_history:
            has_entry, entry_date, entry_prob = has_entry_potential(
                price_history,
                threshold=min_probability_threshold,
                mode="backtest",
            )
            
            if not has_entry:
                stats["filtered_no_entry"] += 1
                if verbose:
                    print(f"   [SKIP] No entry signal: '{event.title[:50]}...'")
                continue
        else:
            # No price history - can't check entry potential
            entry_date = None
            entry_prob = None
        
        # 2. Check for duplicates
        dedup_result = check_duplicate(
            event,
            portfolio,
            use_embeddings=use_embeddings,
            use_llm=False,  # Don't use LLM in bulk filtering
            verbose=verbose,
        )
        
        if dedup_result.is_duplicate:
            stats["filtered_duplicate"] += 1
            if verbose:
                print(f"   [SKIP] Duplicate ({dedup_result.method}): '{event.title[:50]}...'")
                print(f"          Matches: '{dedup_result.matching_event_title[:50]}...'")
            continue
        
        # Event passed all filters
        stats["passed"] += 1
        filtered.append(FilteredEvent(
            event=event.__dict__ if hasattr(event, '__dict__') else dict(event),
            score=0.0,  # Will be set by caller
            relevance="unknown",  # Will be set by caller
            entry_potential=True,
            entry_date=entry_date,
            entry_probability=entry_prob,
        ))
    
    return filtered, stats


# =============================================================================
# Persistence
# =============================================================================

def save_portfolio(portfolio: EventPortfolio, filepath: str) -> None:
    """Save portfolio to JSON file."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(portfolio.model_dump(), f, indent=2, default=str)


def load_portfolio(filepath: str) -> EventPortfolio:
    """Load portfolio from JSON file."""
    if not os.path.exists(filepath):
        return EventPortfolio()
    
    with open(filepath, "r") as f:
        data = json.load(f)
    
    return EventPortfolio(**data)
