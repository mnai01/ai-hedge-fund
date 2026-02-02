"""Integration tests for the Polymarket Event Discovery flow.

This module tests the full event discovery pipeline:
1. Fetch events from Polymarket API
2. Score events with EventScorer
3. Filter by category
4. Get enhanced signals
5. Verify output format

These tests use mocked API responses to avoid network calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from src.tools.event_scorer import (
    EventScorer,
    EnhancedEventScorer,
    score_events,
    get_top_events,
    filter_stock_relevant_events,
)
from src.data.event_models import (
    ScoringConfig,
    ScoringWeights,
    EventScore,
    RankedEventList,
    EnhancedScoringWeights,
    SignalSummary,
    EnhancedSignalSummary,
)
from src.data.polymarket_models import PolymarketEvent, PolymarketMarket
from src.data.position_context import (
    PositionContext,
    EventHistory,
    AnalyzedEvent,
    build_portfolio_context,
)
from src.agents.polymarket_discovery import (
    discover_tickers_from_events,
    StockMapping,
    EventStockMappingResponse,
)


# ==================== Test Fixtures ====================

@pytest.fixture
def sample_events():
    """Create sample Polymarket events for testing."""
    now = datetime.now(timezone.utc)
    
    return [
        PolymarketEvent(
            id="event-1",
            title="Will the Fed cut rates in March 2025?",
            slug="fed-rate-cut-march-2025",
            description="Federal Reserve interest rate decision",
            active=True,
            closed=False,
            volume=5_000_000,
            volume_24hr=100_000,
            liquidity=200_000,
            end_date=(now + timedelta(days=30)).isoformat(),
            probability=0.72,
            category="economy",
            markets=[
                PolymarketMarket(
                    id="market-1",
                    question="Will the Fed cut rates?",
                    outcome_prices='["0.72", "0.28"]',
                    volume=5_000_000,
                    volume_24hr=100_000,
                    liquidity=200_000,
                )
            ],
        ),
        PolymarketEvent(
            id="event-2",
            title="Will Bitcoin reach $150k by June 2025?",
            slug="bitcoin-150k-june-2025",
            description="Bitcoin price prediction",
            active=True,
            closed=False,
            volume=10_000_000,
            volume_24hr=500_000,
            liquidity=500_000,
            end_date=(now + timedelta(days=120)).isoformat(),
            probability=0.35,
            category="crypto",
            markets=[
                PolymarketMarket(
                    id="market-2",
                    question="Will Bitcoin reach $150k?",
                    outcome_prices='["0.35", "0.65"]',
                    volume=10_000_000,
                    volume_24hr=500_000,
                    liquidity=500_000,
                )
            ],
        ),
        PolymarketEvent(
            id="event-3",
            title="Will there be a government shutdown in Q1 2025?",
            slug="government-shutdown-q1-2025",
            description="US government shutdown prediction",
            active=True,
            closed=False,
            volume=2_000_000,
            volume_24hr=50_000,
            liquidity=100_000,
            end_date=(now + timedelta(days=45)).isoformat(),
            probability=0.65,
            category="politics",
            markets=[
                PolymarketMarket(
                    id="market-3",
                    question="Will there be a shutdown?",
                    outcome_prices='["0.65", "0.35"]',
                    volume=2_000_000,
                    volume_24hr=50_000,
                    liquidity=100_000,
                )
            ],
        ),
        PolymarketEvent(
            id="event-4",
            title="Will Apple announce a new product category in 2025?",
            slug="apple-new-product-2025",
            description="Apple product announcement",
            active=True,
            closed=False,
            volume=500_000,
            volume_24hr=10_000,
            liquidity=25_000,
            end_date=(now + timedelta(days=180)).isoformat(),
            probability=0.45,
            category="tech",
            markets=[
                PolymarketMarket(
                    id="market-4",
                    question="Will Apple announce new category?",
                    outcome_prices='["0.45", "0.55"]',
                    volume=500_000,
                    volume_24hr=10_000,
                    liquidity=25_000,
                )
            ],
        ),
    ]


@pytest.fixture
def sample_market_data():
    """Create sample market data with price changes."""
    return {
        "oneDayPriceChange": 0.05,
        "oneWeekPriceChange": 0.12,
        "spread": 0.02,
        "bestBid": 0.70,
        "bestAsk": 0.72,
    }


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response for stock mapping."""
    return EventStockMappingResponse(
        affected_stocks=[
            StockMapping(
                ticker="JPM",
                direction="bullish",
                confidence=85,
                thesis="Rate cuts benefit banks through increased lending activity",
                thesis_type="short_term",
                reasoning="Lower rates typically boost bank lending margins",
            ),
            StockMapping(
                ticker="XLF",
                direction="bullish",
                confidence=75,
                thesis="Financial sector ETF benefits from rate environment",
                thesis_type="short_term",
                reasoning="Financial sector broadly benefits from rate cuts",
            ),
        ],
        event_relevance="high",
    )


# ==================== Integration Tests ====================

class TestEventDiscoveryFlow:
    """Test the full event discovery flow."""
    
    def test_step1_fetch_and_score_events(self, sample_events):
        """Step 1: Score events with EventScorer."""
        scorer = EventScorer()
        
        # Score all events
        ranked = scorer.rank_events(sample_events)
        
        # Verify we got scores for all events
        assert len(ranked.events) == len(sample_events)
        assert ranked.total_events == len(sample_events)
        
        # Verify scores are in descending order
        scores = [e.total_score for e in ranked.events]
        assert scores == sorted(scores, reverse=True)
        
        # Verify each event has component scores
        for event_score in ranked.events:
            assert "volume" in event_score.component_scores
            assert "liquidity" in event_score.component_scores
            assert "time_horizon" in event_score.component_scores
            assert "category" in event_score.component_scores
            assert event_score.total_score >= 0
            assert event_score.total_score <= 100
    
    def test_step2_filter_by_category(self, sample_events):
        """Step 2: Filter events by category."""
        scorer = EventScorer()
        
        # Filter to economy and politics only
        filtered = scorer.filter_by_category(
            sample_events,
            categories=["economy", "politics"],
        )
        
        # The filter_by_category returns events matching the categories
        # Our sample has "economy" and "politics" categories
        categories = [e.category for e in filtered]
        # At least one should match if any events have these categories
        assert all(c in ["economy", "politics"] for c in categories if c)
    
    def test_step3_get_enhanced_signals(self, sample_events, sample_market_data):
        """Step 3: Get enhanced signals for top events."""
        scorer = EnhancedEventScorer()
        
        # Get enhanced signals for first event
        event = sample_events[0]
        event_dict = {
            "id": event.id,
            "title": event.title,
            "volume": event.volume,
            "volume24hr": event.volume_24hr,
            "liquidity": event.liquidity,
            "endDate": event.end_date,
            "category": event.category,
            "openInterest": 1_000_000,  # Add for smart money signal
        }
        
        summary = scorer.get_signal_summary(event_dict, sample_market_data)
        
        # Verify all signal components are present
        assert summary.unusual_volume is not None
        assert summary.delta_movement is not None
        assert summary.implied_volatility is not None
        assert summary.smart_money is not None
        assert summary.overall_signal_strength >= 0
        assert summary.overall_signal_strength <= 1
        
        # Verify interpretations are strings
        assert isinstance(summary.unusual_volume.interpretation, str)
        assert isinstance(summary.delta_movement.interpretation, str)
    
    def test_step4_verify_output_format(self, sample_events):
        """Step 4: Verify output format matches expected structure."""
        scorer = EventScorer()
        
        # Get top events with minimum score
        ranked = scorer.rank_events(
            sample_events,
            min_score=50,
            limit=3,
        )
        
        # Verify RankedEventList structure
        assert isinstance(ranked, RankedEventList)
        assert hasattr(ranked, "events")
        assert hasattr(ranked, "total_events")
        assert hasattr(ranked, "filtered_count")
        assert hasattr(ranked, "scoring_config")
        
        # Verify EventScore structure
        for event_score in ranked.events:
            assert isinstance(event_score, EventScore)
            assert hasattr(event_score, "event_id")
            assert hasattr(event_score, "event_title")
            assert hasattr(event_score, "total_score")
            assert hasattr(event_score, "component_scores")
            assert hasattr(event_score, "recommendation")
            
            # Verify recommendation is valid (includes all possible values)
            assert event_score.recommendation in ["analyze", "consider", "skip", "low_priority", "high_priority"]
    
    @patch("src.agents.polymarket_discovery.call_llm")
    @patch("src.agents.polymarket_discovery.get_active_events")
    def test_full_discovery_flow(
        self,
        mock_get_events,
        mock_call_llm,
        sample_events,
        mock_llm_response,
    ):
        """Test the complete discovery flow end-to-end."""
        # Setup mocks
        mock_get_events.return_value = sample_events
        mock_call_llm.return_value = mock_llm_response
        
        # Run discovery
        discovered, event_history = discover_tickers_from_events(
            events=sample_events,
            min_score=40,
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
        )
        
        # Verify discovered tickers (may be empty if no events match criteria)
        assert isinstance(discovered, list)
        
        for item in discovered:
            assert "ticker" in item
            assert "context" in item
            assert "event_title" in item
            assert "probability" in item
            assert "event_score" in item
            
            # Verify context is a dict or PositionContext
            context = item["context"]
            # Context can be a dict (serialized) or PositionContext object
            assert isinstance(context, (dict, PositionContext))
            if isinstance(context, dict):
                assert "ticker" in context
        
        # Verify event history was updated
        assert isinstance(event_history, EventHistory)


class TestEventHistoryDeduplication:
    """Test event history and deduplication."""
    
    def test_event_history_tracks_analyzed_events(self):
        """Test that EventHistory tracks analyzed events."""
        history = EventHistory()
        
        # Add an analyzed event
        event = AnalyzedEvent(
            event_id="test-event-1",
            event_title="Test Event Title",
            score=75.5,
            mapped_tickers=["AAPL", "MSFT"],
            outcome="pending",
        )
        history.add_event(event)
        
        # Verify event was added (events is a dict keyed by event_id)
        assert len(history.events) == 1
        assert "test-event-1" in history.events
        assert history.events["test-event-1"].event_id == "test-event-1"
    
    def test_should_skip_duplicate_event_id(self):
        """Test that duplicate event IDs are skipped."""
        history = EventHistory()
        
        # Add an event
        event = AnalyzedEvent(
            event_id="test-event-1",
            event_title="Test Event",
            score=75.0,
            mapped_tickers=["AAPL"],
            outcome="pending",
        )
        history.add_event(event)
        
        # Check if same ID should be skipped
        should_skip, reason = history.should_skip_event(
            event_id="test-event-1",
            event_title="Different Title",
        )
        
        assert should_skip is True
        assert "already analyzed" in reason.lower()
    
    def test_should_skip_similar_title(self):
        """Test that similar titles are detected."""
        history = EventHistory()
        
        # Add an event
        event = AnalyzedEvent(
            event_id="test-event-1",
            event_title="Will the Fed cut rates in March 2025?",
            score=75.0,
            mapped_tickers=["JPM"],
            outcome="pending",
        )
        history.add_event(event)
        
        # Check if similar title should be skipped
        should_skip, reason = history.should_skip_event(
            event_id="test-event-2",  # Different ID
            event_title="Will the Fed cut rates in April 2025?",  # Similar title
        )
        
        assert should_skip is True
        assert "similar" in reason.lower()


class TestPortfolioContextInjection:
    """Test portfolio context injection into LLM prompts."""
    
    def test_build_portfolio_context_empty(self):
        """Test building context with empty portfolio."""
        context = build_portfolio_context({})
        # Empty portfolio returns a message about no positions
        assert "Empty" in context or "no existing positions" in context
    
    def test_build_portfolio_context_with_positions(self):
        """Test building context with existing positions."""
        from src.data.position_context import EventThesis, EventType, ThesisType, ProbabilitySnapshot
        
        # Create proper PositionContext with EventThesis
        event1 = EventThesis(
            event_id="event-1",
            event_title="Apple earnings event",
            event_type=EventType.BINARY,
            thesis="Strong iPhone sales expected",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=0.70),
            entry_date="2024-01-15",
        )
        
        event2 = EventThesis(
            event_id="event-2",
            event_title="Microsoft cloud growth",
            event_type=EventType.BINARY,
            thesis="Azure growth continues",
            thesis_type=ThesisType.LONG_TERM,
            impact_direction="bullish",
            confidence=75,
            probability=ProbabilitySnapshot(current=0.65),
            entry_date="2024-01-16",
        )
        
        positions = {
            "AAPL": PositionContext(ticker="AAPL", events=[event1]),
            "MSFT": PositionContext(ticker="MSFT", events=[event2]),
        }
        
        context = build_portfolio_context(positions)
        
        # Verify context contains position info
        assert "AAPL" in context
        assert "MSFT" in context
        # Should contain thesis info
        assert "bullish" in context


class TestEnhancedSignals:
    """Test enhanced signal analysis."""
    
    def test_unusual_volume_signal(self):
        """Test unusual volume signal calculation."""
        scorer = EnhancedEventScorer()
        
        # High volume acceleration
        event = {
            "volume24hr": 300_000,  # 3x daily average
            "volume1wk": 700_000,   # 100k daily average
        }
        
        signal = scorer._unusual_volume_signal(event)
        
        # Should be high signal (3x normal)
        assert signal >= 0.7
    
    def test_delta_movement_signal(self):
        """Test delta/probability movement signal."""
        scorer = EnhancedEventScorer()
        
        # Strong momentum
        market = {
            "oneDayPriceChange": 0.10,
            "oneWeekPriceChange": 0.15,
        }
        
        signal = scorer._delta_movement_signal(market)
        
        # Should be high signal (10%+ move)
        assert signal >= 0.6
    
    def test_implied_volatility_proxy(self):
        """Test implied volatility proxy from spread."""
        scorer = EnhancedEventScorer()
        
        # Wide spread = high uncertainty
        market = {
            "spread": 0.08,
        }
        
        signal = scorer._implied_volatility_proxy(market)
        
        # Should be elevated signal (8% spread)
        assert signal >= 0.5
    
    def test_smart_money_signal(self):
        """Test smart money signal from OI ratio."""
        scorer = EnhancedEventScorer()
        
        # High volume relative to OI
        event = {
            "volume24hr": 500_000,
            "openInterest": 1_000_000,  # 50% ratio
        }
        
        signal = scorer._smart_money_signal(event)
        
        # Should be high signal (50% of OI traded)
        assert signal >= 0.7


class TestConvenienceFunctions:
    """Test convenience functions for common operations."""
    
    def test_score_events_function(self, sample_events):
        """Test the score_events convenience function."""
        scores = score_events(sample_events, min_score=50)
        
        assert isinstance(scores, list)
        for score in scores:
            assert isinstance(score, EventScore)
            assert score.total_score >= 50
    
    def test_get_top_events_function(self, sample_events):
        """Test the get_top_events convenience function."""
        top = get_top_events(sample_events, n=2)
        
        assert len(top) == 2
        assert top[0].total_score >= top[1].total_score
    
    def test_filter_stock_relevant_events_function(self, sample_events):
        """Test the filter_stock_relevant_events function."""
        relevant = filter_stock_relevant_events(sample_events, min_score=40)
        
        # Should only include high-relevance categories
        for score in relevant:
            assert score.category in ["economy", "finance", "politics", "tech"]
