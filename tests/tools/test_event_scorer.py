"""Unit tests for the Event Scoring Engine.

Tests cover:
- Individual scoring methods (volume, liquidity, time_horizon, etc.)
- Composite scoring
- Event ranking
- Category filtering
- Edge cases and null handling
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from src.tools.event_scorer import (
    EventScorer,
    create_scorer,
    score_events,
    get_top_events,
    filter_stock_relevant_events,
    OFFICIAL_CATEGORIES,
)
from src.data.event_models import (
    ScoringWeights,
    EventScore,
    ScoringConfig,
    RankedEventList,
)


# Test fixtures

@pytest.fixture
def scorer() -> EventScorer:
    """Create a default EventScorer instance."""
    return EventScorer()


@pytest.fixture
def high_volume_event() -> Dict[str, Any]:
    """Create a high-volume event for testing."""
    return {
        "id": "event-001",
        "title": "Will the Fed cut rates in March?",
        "volume": 15_000_000,
        "volume24hr": 500_000,
        "volume1wk": 2_000_000,
        "liquidity": 750_000,
        "openInterest": 1_000_000,
        "category": "economy",
        "endDate": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        "markets": [
            {
                "id": "market-001",
                "question": "Fed rate cut in March",
                "oneDayPriceChange": 0.08,
                "oneWeekPriceChange": 0.12,
            }
        ],
    }


@pytest.fixture
def low_volume_event() -> Dict[str, Any]:
    """Create a low-volume event for testing."""
    return {
        "id": "event-002",
        "title": "Will Lakers win the championship?",
        "volume": 5_000,
        "volume24hr": 500,
        "volume1wk": 3_000,
        "liquidity": 2_000,
        "openInterest": 5_000,
        "category": "sports",
        "endDate": (datetime.now(timezone.utc) + timedelta(days=120)).isoformat(),
        "markets": [
            {
                "id": "market-002",
                "question": "Lakers championship",
                "oneDayPriceChange": 0.01,
                "oneWeekPriceChange": -0.02,
            }
        ],
    }


@pytest.fixture
def medium_event() -> Dict[str, Any]:
    """Create a medium-scoring event for testing."""
    return {
        "id": "event-003",
        "title": "Will Bitcoin reach $100k by EOY?",
        "volume": 500_000,
        "volume24hr": 25_000,
        "volume1wk": 150_000,
        "liquidity": 50_000,
        "openInterest": 200_000,
        "category": "crypto",
        "endDate": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat(),
        "markets": [
            {
                "id": "market-003",
                "question": "Bitcoin $100k",
                "oneDayPriceChange": 0.03,
                "oneWeekPriceChange": 0.05,
            }
        ],
    }


@pytest.fixture
def event_with_missing_fields() -> Dict[str, Any]:
    """Create an event with missing/null fields."""
    return {
        "id": "event-004",
        "title": "Event with missing data",
        "volume": None,
        "volume24hr": None,
        "liquidity": None,
        "category": None,
        "endDate": None,
    }


@pytest.fixture
def sample_events(
    high_volume_event: Dict[str, Any],
    low_volume_event: Dict[str, Any],
    medium_event: Dict[str, Any],
) -> list:
    """Create a list of sample events for ranking tests."""
    return [high_volume_event, low_volume_event, medium_event]


# Test ScoringWeights model

class TestScoringWeights:
    """Tests for ScoringWeights model."""
    
    def test_default_weights(self):
        """Test default weight values."""
        weights = ScoringWeights()
        
        assert weights.volume == 0.25
        assert weights.liquidity == 0.20
        assert weights.time_horizon == 0.15
        assert weights.category == 0.15
        assert weights.momentum == 0.10
        assert weights.volume_trend == 0.10
        assert weights.smart_money == 0.05
    
    def test_total_weight(self):
        """Test that default weights sum to 1.0."""
        weights = ScoringWeights()
        assert abs(weights.total_weight - 1.0) < 0.01
    
    def test_is_normalized(self):
        """Test normalization check."""
        weights = ScoringWeights()
        assert weights.is_normalized()
        
        # Non-normalized weights
        custom = ScoringWeights(volume=0.5, liquidity=0.5)
        assert not custom.is_normalized()
    
    def test_normalize(self):
        """Test weight normalization."""
        custom = ScoringWeights(volume=0.5, liquidity=0.5, time_horizon=0.5)
        normalized = custom.normalize()
        
        assert normalized.is_normalized()
        assert abs(normalized.total_weight - 1.0) < 0.01
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        weights = ScoringWeights()
        d = weights.to_dict()
        
        assert isinstance(d, dict)
        assert "volume" in d
        assert "liquidity" in d
        assert len(d) == 7


# Test EventScore model

class TestEventScore:
    """Tests for EventScore model."""
    
    def test_create_event_score(self):
        """Test creating an EventScore."""
        score = EventScore(
            event_id="test-001",
            event_title="Test Event",
            total_score=75.5,
            component_scores={"volume": 80, "liquidity": 70},
            rank=1,
            recommendation="analyze",
        )
        
        assert score.event_id == "test-001"
        assert score.total_score == 75.5
        assert score.recommendation == "analyze"
    
    def test_get_recommendation(self):
        """Test recommendation thresholds."""
        assert EventScore.get_recommendation(85) == "analyze"
        assert EventScore.get_recommendation(70) == "analyze"
        assert EventScore.get_recommendation(55) == "low_priority"
        assert EventScore.get_recommendation(40) == "low_priority"
        assert EventScore.get_recommendation(30) == "skip"
        assert EventScore.get_recommendation(0) == "skip"
    
    def test_component_score_validation(self):
        """Test that component scores must be 0-100."""
        with pytest.raises(ValueError):
            EventScore(
                event_id="test",
                event_title="Test",
                total_score=50,
                component_scores={"volume": 150},  # Invalid
            )
    
    def test_to_summary_dict(self):
        """Test summary dictionary generation."""
        score = EventScore(
            event_id="test-001",
            event_title="Test Event",
            total_score=75.5,
            rank=1,
            recommendation="analyze",
            category="economy",
        )
        
        summary = score.to_summary_dict()
        assert summary["event_id"] == "test-001"
        assert summary["score"] == 75.5
        assert summary["category"] == "economy"


# Test EventScorer - Volume Scoring

class TestVolumeScoring:
    """Tests for volume scoring method."""
    
    def test_high_volume_score(self, scorer: EventScorer):
        """Test scoring for high volume events."""
        event = {"volume": 15_000_000, "volume24hr": 500_000}
        score = scorer._volume_score(event)
        
        assert score >= 90  # High volume should score high
    
    def test_medium_volume_score(self, scorer: EventScorer):
        """Test scoring for medium volume events."""
        event = {"volume": 500_000, "volume24hr": 25_000}
        score = scorer._volume_score(event)
        
        assert 50 <= score <= 80
    
    def test_low_volume_score(self, scorer: EventScorer):
        """Test scoring for low volume events."""
        event = {"volume": 500, "volume24hr": 50}
        score = scorer._volume_score(event)
        
        assert score <= 30
    
    def test_null_volume(self, scorer: EventScorer):
        """Test handling of null volume values."""
        event = {"volume": None, "volume24hr": None}
        score = scorer._volume_score(event)
        
        assert score >= 0  # Should not crash
        assert score <= 100
    
    def test_volume_score_range(self, scorer: EventScorer):
        """Test that volume scores are in valid range."""
        test_cases = [
            {"volume": 0, "volume24hr": 0},
            {"volume": 1_000, "volume24hr": 100},
            {"volume": 100_000_000, "volume24hr": 10_000_000},
        ]
        
        for event in test_cases:
            score = scorer._volume_score(event)
            assert 0 <= score <= 100


# Test EventScorer - Liquidity Scoring

class TestLiquidityScoring:
    """Tests for liquidity scoring method."""
    
    def test_high_liquidity_score(self, scorer: EventScorer):
        """Test scoring for high liquidity events."""
        event = {"liquidity": 750_000}
        score = scorer._liquidity_score(event)
        
        assert score >= 90
    
    def test_medium_liquidity_score(self, scorer: EventScorer):
        """Test scoring for medium liquidity events."""
        event = {"liquidity": 25_000}
        score = scorer._liquidity_score(event)
        
        assert 40 <= score <= 70
    
    def test_low_liquidity_score(self, scorer: EventScorer):
        """Test scoring for low liquidity events."""
        event = {"liquidity": 500}
        score = scorer._liquidity_score(event)
        
        assert score <= 25
    
    def test_null_liquidity(self, scorer: EventScorer):
        """Test handling of null liquidity."""
        event = {"liquidity": None}
        score = scorer._liquidity_score(event)
        
        assert 0 <= score <= 100


# Test EventScorer - Time Horizon Scoring

class TestTimeHorizonScoring:
    """Tests for time horizon scoring method."""
    
    def test_optimal_time_horizon(self, scorer: EventScorer):
        """Test scoring for optimal time horizon (7-30 days)."""
        event = {
            "endDate": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        }
        score = scorer._time_horizon_score(event)
        
        assert score == 100  # Optimal range
    
    def test_short_time_horizon(self, scorer: EventScorer):
        """Test scoring for short time horizon (<7 days)."""
        event = {
            "endDate": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        }
        score = scorer._time_horizon_score(event)
        
        assert 70 <= score <= 90
    
    def test_very_short_time_horizon(self, scorer: EventScorer):
        """Test scoring for very short time horizon (<3 days)."""
        event = {
            "endDate": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        }
        score = scorer._time_horizon_score(event)
        
        assert score <= 50  # Too soon
    
    def test_long_time_horizon(self, scorer: EventScorer):
        """Test scoring for long time horizon (>90 days)."""
        event = {
            "endDate": (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
        }
        score = scorer._time_horizon_score(event)
        
        assert score <= 40  # Too far out
    
    def test_null_end_date(self, scorer: EventScorer):
        """Test handling of null end date."""
        event = {"endDate": None}
        score = scorer._time_horizon_score(event)
        
        assert score == 50  # Neutral score
    
    def test_invalid_date_format(self, scorer: EventScorer):
        """Test handling of invalid date format."""
        event = {"endDate": "not-a-date"}
        score = scorer._time_horizon_score(event)
        
        assert score == 50  # Neutral score


# Test EventScorer - Category Scoring

class TestCategoryScoring:
    """Tests for category scoring method."""
    
    def test_high_relevance_category(self, scorer: EventScorer):
        """Test scoring for high relevance categories."""
        for category in ["economy", "finance"]:
            event = {"category": category}
            score = scorer._category_score(event)
            assert score == 100  # Weight 1.0 * 100
    
    def test_medium_relevance_category(self, scorer: EventScorer):
        """Test scoring for medium relevance categories."""
        event = {"category": "politics"}
        score = scorer._category_score(event)
        assert score == 80  # Weight 0.8 * 100
    
    def test_low_relevance_category(self, scorer: EventScorer):
        """Test scoring for low relevance categories."""
        event = {"category": "sports"}
        score = scorer._category_score(event)
        assert score == 20  # Weight 0.2 * 100
    
    def test_unknown_category(self, scorer: EventScorer):
        """Test scoring for unknown category."""
        event = {"category": "unknown-category"}
        score = scorer._category_score(event)
        assert score == 30  # Default weight 0.3 * 100
    
    def test_null_category(self, scorer: EventScorer):
        """Test handling of null category."""
        event = {"category": None}
        score = scorer._category_score(event)
        assert score == 30  # Default weight
    
    def test_category_from_tags(self, scorer: EventScorer):
        """Test extracting category from tags array."""
        event = {
            "category": None,
            "tags": [{"label": "economy", "slug": "economy"}]
        }
        score = scorer._category_score(event)
        assert score == 100  # Should extract from tags
    
    def test_all_official_categories(self, scorer: EventScorer):
        """Test that all official categories have defined weights."""
        for category in OFFICIAL_CATEGORIES:
            event = {"category": category}
            score = scorer._category_score(event)
            assert 0 <= score <= 100


# Test EventScorer - Momentum Scoring

class TestMomentumScoring:
    """Tests for momentum scoring method."""
    
    def test_high_momentum(self, scorer: EventScorer):
        """Test scoring for high momentum."""
        event = {
            "markets": [{
                "oneDayPriceChange": 0.15,
                "oneWeekPriceChange": 0.20,
            }]
        }
        score = scorer._momentum_score(event, None)
        
        assert score >= 90
    
    def test_medium_momentum(self, scorer: EventScorer):
        """Test scoring for medium momentum."""
        event = {
            "markets": [{
                "oneDayPriceChange": 0.05,
                "oneWeekPriceChange": 0.08,
            }]
        }
        score = scorer._momentum_score(event, None)
        
        assert 50 <= score <= 80
    
    def test_low_momentum(self, scorer: EventScorer):
        """Test scoring for low momentum."""
        event = {
            "markets": [{
                "oneDayPriceChange": 0.01,
                "oneWeekPriceChange": 0.01,
            }]
        }
        score = scorer._momentum_score(event, None)
        
        assert score <= 50
    
    def test_consistent_direction_bonus(self, scorer: EventScorer):
        """Test bonus for consistent direction."""
        # Consistent positive
        event_consistent = {
            "markets": [{
                "oneDayPriceChange": 0.05,
                "oneWeekPriceChange": 0.05,
            }]
        }
        
        # Inconsistent direction
        event_inconsistent = {
            "markets": [{
                "oneDayPriceChange": 0.05,
                "oneWeekPriceChange": -0.05,
            }]
        }
        
        score_consistent = scorer._momentum_score(event_consistent, None)
        score_inconsistent = scorer._momentum_score(event_inconsistent, None)
        
        assert score_consistent > score_inconsistent
    
    def test_no_market_data(self, scorer: EventScorer):
        """Test handling of missing market data."""
        event = {"markets": []}
        score = scorer._momentum_score(event, None)
        
        assert score == 50  # Neutral score
    
    def test_separate_market_dict(self, scorer: EventScorer):
        """Test using separate market dict."""
        event = {"id": "test"}
        market = {
            "oneDayPriceChange": 0.10,
            "oneWeekPriceChange": 0.15,
        }
        score = scorer._momentum_score(event, market)
        
        assert score >= 70


# Test EventScorer - Volume Trend Scoring

class TestVolumeTrendScoring:
    """Tests for volume trend scoring method."""
    
    def test_high_acceleration(self, scorer: EventScorer):
        """Test scoring for high volume acceleration."""
        event = {
            "volume24hr": 100_000,
            "volume1wk": 100_000,  # Daily avg = ~14k, so 100k is ~7x
        }
        score = scorer._volume_trend_score(event)
        
        assert score >= 90
    
    def test_normal_activity(self, scorer: EventScorer):
        """Test scoring for normal volume activity."""
        event = {
            "volume24hr": 15_000,
            "volume1wk": 105_000,  # Daily avg = 15k, so 15k is ~1x
        }
        score = scorer._volume_trend_score(event)
        
        # 1x normal activity should score around 50
        assert 45 <= score <= 55
    
    def test_declining_activity(self, scorer: EventScorer):
        """Test scoring for declining volume."""
        event = {
            "volume24hr": 5_000,
            "volume1wk": 100_000,  # Daily avg = ~14k, so 5k is ~0.35x
        }
        score = scorer._volume_trend_score(event)
        
        assert score <= 40
    
    def test_no_weekly_volume(self, scorer: EventScorer):
        """Test handling of zero weekly volume."""
        event = {"volume24hr": 10_000, "volume1wk": 0}
        score = scorer._volume_trend_score(event)
        
        assert score == 50  # Neutral score


# Test EventScorer - Smart Money Scoring

class TestSmartMoneyScoring:
    """Tests for smart money scoring method."""
    
    def test_high_activity_ratio(self, scorer: EventScorer):
        """Test scoring for high volume/OI ratio."""
        event = {
            "volume24hr": 500_000,
            "openInterest": 1_000_000,  # 50% ratio
        }
        score = scorer._smart_money_score(event)
        
        assert score >= 90
    
    def test_moderate_activity(self, scorer: EventScorer):
        """Test scoring for moderate activity."""
        event = {
            "volume24hr": 100_000,
            "openInterest": 1_000_000,  # 10% ratio
        }
        score = scorer._smart_money_score(event)
        
        assert 50 <= score <= 70
    
    def test_low_activity(self, scorer: EventScorer):
        """Test scoring for low activity."""
        event = {
            "volume24hr": 10_000,
            "openInterest": 1_000_000,  # 1% ratio
        }
        score = scorer._smart_money_score(event)
        
        assert score <= 40
    
    def test_no_open_interest(self, scorer: EventScorer):
        """Test handling of zero open interest."""
        event = {"volume24hr": 100_000, "openInterest": 0}
        score = scorer._smart_money_score(event)
        
        assert score == 70  # Falls back to volume-based scoring


# Test EventScorer - Composite Scoring

class TestCompositeScoring:
    """Tests for composite event scoring."""
    
    def test_score_high_quality_event(
        self, 
        scorer: EventScorer, 
        high_volume_event: Dict[str, Any],
    ):
        """Test scoring a high-quality event."""
        score = scorer.score_event(high_volume_event)
        
        assert score.event_id == "event-001"
        assert score.total_score >= 70
        assert score.recommendation == "analyze"
        assert len(score.component_scores) == 7
    
    def test_score_low_quality_event(
        self, 
        scorer: EventScorer, 
        low_volume_event: Dict[str, Any],
    ):
        """Test scoring a low-quality event."""
        score = scorer.score_event(low_volume_event)
        
        assert score.event_id == "event-002"
        assert score.total_score < 50
        assert score.recommendation in ["skip", "low_priority"]
    
    def test_score_event_with_missing_fields(
        self, 
        scorer: EventScorer, 
        event_with_missing_fields: Dict[str, Any],
    ):
        """Test scoring handles missing fields gracefully."""
        score = scorer.score_event(event_with_missing_fields)
        
        assert score.event_id == "event-004"
        assert 0 <= score.total_score <= 100
        # Should not crash, should return valid score
    
    def test_all_component_scores_in_range(
        self, 
        scorer: EventScorer, 
        high_volume_event: Dict[str, Any],
    ):
        """Test that all component scores are in valid range."""
        score = scorer.score_event(high_volume_event)
        
        for component, value in score.component_scores.items():
            assert 0 <= value <= 100, f"{component} score out of range: {value}"


# Test EventScorer - Ranking

class TestEventRanking:
    """Tests for event ranking functionality."""
    
    def test_rank_events(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test ranking multiple events."""
        ranked = scorer.rank_events(sample_events)
        
        assert isinstance(ranked, RankedEventList)
        assert len(ranked.events) == 3
        assert ranked.total_events == 3
        
        # Check events are sorted by score (descending)
        scores = [e.total_score for e in ranked.events]
        assert scores == sorted(scores, reverse=True)
        
        # Check ranks are assigned
        for i, event in enumerate(ranked.events, start=1):
            assert event.rank == i
    
    def test_rank_with_min_score(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test ranking with minimum score filter."""
        ranked = scorer.rank_events(sample_events, min_score=50)
        
        for event in ranked.events:
            assert event.total_score >= 50
    
    def test_rank_with_category_filter(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test ranking with category filter."""
        ranked = scorer.rank_events(sample_events, categories=["economy", "crypto"])
        
        for event in ranked.events:
            assert event.category in ["economy", "crypto"]
    
    def test_rank_with_limit(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test ranking with result limit."""
        ranked = scorer.rank_events(sample_events, limit=2)
        
        assert len(ranked.events) <= 2
    
    def test_empty_event_list(self, scorer: EventScorer):
        """Test ranking empty event list."""
        ranked = scorer.rank_events([])
        
        assert len(ranked.events) == 0
        assert ranked.total_events == 0


# Test EventScorer - Category Filtering

class TestCategoryFiltering:
    """Tests for category filtering functionality."""
    
    def test_filter_by_single_category(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test filtering by single category."""
        filtered = scorer.filter_by_category(sample_events, ["economy"])
        
        assert len(filtered) == 1
        assert filtered[0]["category"] == "economy"
    
    def test_filter_by_multiple_categories(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test filtering by multiple categories."""
        filtered = scorer.filter_by_category(sample_events, ["economy", "crypto"])
        
        assert len(filtered) == 2
    
    def test_filter_case_insensitive(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test that category filtering is case-insensitive."""
        filtered = scorer.filter_by_category(sample_events, ["ECONOMY", "Crypto"])
        
        assert len(filtered) == 2
    
    def test_filter_no_matches(
        self, 
        scorer: EventScorer, 
        sample_events: list,
    ):
        """Test filtering with no matching categories."""
        filtered = scorer.filter_by_category(sample_events, ["nonexistent"])
        
        assert len(filtered) == 0


# Test Convenience Functions

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    def test_score_events_function(self, sample_events: list):
        """Test score_events convenience function."""
        scores = score_events(sample_events)
        
        assert len(scores) == 3
        assert all(isinstance(s, EventScore) for s in scores)
    
    def test_get_top_events_function(self, sample_events: list):
        """Test get_top_events convenience function."""
        top = get_top_events(sample_events, n=2)
        
        assert len(top) == 2
        assert top[0].total_score >= top[1].total_score
    
    def test_filter_stock_relevant_events_function(self, sample_events: list):
        """Test filter_stock_relevant_events convenience function."""
        relevant = filter_stock_relevant_events(sample_events, min_score=0)
        
        # Should only include high-relevance categories
        for event in relevant:
            assert event.category in ["economy", "finance", "politics", "tech"]
    
    def test_create_scorer_with_custom_weights(self):
        """Test create_scorer factory function."""
        scorer = create_scorer(
            weights={"volume": 0.4, "liquidity": 0.3},
            min_score_threshold=60,
        )
        
        assert scorer.config.min_score_threshold == 60
        # Weights should be normalized
        assert scorer.config.weights.is_normalized()


# Test RankedEventList

class TestRankedEventList:
    """Tests for RankedEventList model."""
    
    def test_top_events_property(self, scorer: EventScorer, sample_events: list):
        """Test top_events property."""
        ranked = scorer.rank_events(sample_events)
        
        top = ranked.top_events
        for event in top:
            assert event.recommendation == "analyze"
    
    def test_low_priority_events_property(self, scorer: EventScorer, sample_events: list):
        """Test low_priority_events property."""
        ranked = scorer.rank_events(sample_events)
        
        low_priority = ranked.low_priority_events
        for event in low_priority:
            assert event.recommendation == "low_priority"
    
    def test_skipped_events_property(self, scorer: EventScorer, sample_events: list):
        """Test skipped_events property."""
        ranked = scorer.rank_events(sample_events)
        
        skipped = ranked.skipped_events
        for event in skipped:
            assert event.recommendation == "skip"
    
    def test_get_by_category(self, scorer: EventScorer, sample_events: list):
        """Test get_by_category method."""
        ranked = scorer.rank_events(sample_events)
        
        economy_events = ranked.get_by_category("economy")
        assert all(e.category == "economy" for e in economy_events)
    
    def test_get_top_n(self, scorer: EventScorer, sample_events: list):
        """Test get_top_n method."""
        ranked = scorer.rank_events(sample_events)
        
        top_2 = ranked.get_top_n(2)
        assert len(top_2) == 2
    
    def test_to_summary(self, scorer: EventScorer, sample_events: list):
        """Test to_summary method."""
        ranked = scorer.rank_events(sample_events)
        
        summary = ranked.to_summary()
        assert "total_events" in summary
        assert "analyze_count" in summary
        assert "generated_at" in summary


# Test Edge Cases

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_negative_values(self, scorer: EventScorer):
        """Test handling of negative values."""
        event = {
            "id": "test",
            "title": "Test",
            "volume": -1000,
            "liquidity": -500,
        }
        score = scorer.score_event(event)
        
        # Should handle gracefully
        assert 0 <= score.total_score <= 100
    
    def test_extremely_large_values(self, scorer: EventScorer):
        """Test handling of extremely large values."""
        event = {
            "id": "test",
            "title": "Test",
            "volume": 10**15,
            "liquidity": 10**12,
        }
        score = scorer.score_event(event)
        
        assert 0 <= score.total_score <= 100
    
    def test_string_numeric_values(self, scorer: EventScorer):
        """Test handling of string numeric values."""
        event = {
            "id": "test",
            "title": "Test",
            "volume": "1000000",
            "liquidity": "50000",
        }
        score = scorer.score_event(event)
        
        # Should convert strings to numbers
        assert 0 <= score.total_score <= 100
    
    def test_empty_event(self, scorer: EventScorer):
        """Test handling of minimal event data."""
        event = {
            "id": "test",
            "title": "Test",
        }
        score = scorer.score_event(event)
        
        assert 0 <= score.total_score <= 100
    
    def test_date_with_z_suffix(self, scorer: EventScorer):
        """Test handling of ISO date with Z suffix."""
        event = {
            "id": "test",
            "title": "Test",
            "endDate": "2025-03-15T00:00:00Z",
        }
        score = scorer._time_horizon_score(event)
        
        assert 0 <= score <= 100
    
    def test_date_without_timezone(self, scorer: EventScorer):
        """Test handling of date without timezone."""
        event = {
            "id": "test",
            "title": "Test",
            "endDate": "2025-03-15",
        }
        score = scorer._time_horizon_score(event)
        
        assert 0 <= score <= 100


# Test Integration with PolymarketEvent

class TestPolymarketEventIntegration:
    """Tests for integration with PolymarketEvent model."""
    
    def test_score_polymarket_event_object(self, scorer: EventScorer):
        """Test scoring a PolymarketEvent object."""
        from src.data.polymarket_models import PolymarketEvent, PolymarketMarket
        
        market = PolymarketMarket(
            id="market-001",
            question="Test market",
            volume=100_000,
            volume_24hr=10_000,
            liquidity=50_000,
        )
        
        event = PolymarketEvent(
            id="event-001",
            title="Test Event",
            volume=500_000,
            volume_24hr=50_000,
            liquidity=100_000,
            markets=[market],
            tags=[{"label": "economy"}],
        )
        
        score = scorer.score_event(event)
        
        assert score.event_id == "event-001"
        assert score.event_title == "Test Event"
        assert 0 <= score.total_score <= 100
    
    def test_rank_polymarket_events(self, scorer: EventScorer):
        """Test ranking PolymarketEvent objects."""
        from src.data.polymarket_models import PolymarketEvent
        
        events = [
            PolymarketEvent(
                id="event-001",
                title="High Volume Event",
                volume=10_000_000,
                liquidity=500_000,
            ),
            PolymarketEvent(
                id="event-002",
                title="Low Volume Event",
                volume=1_000,
                liquidity=500,
            ),
        ]
        
        ranked = scorer.rank_events(events)
        
        assert len(ranked.events) == 2
        assert ranked.events[0].event_id == "event-001"  # Higher score first


# Test Enhanced Event Scorer - Options-Like Signals

class TestEnhancedScoringWeights:
    """Tests for EnhancedScoringWeights model."""
    
    def test_default_enhanced_weights(self):
        """Test default enhanced weight values."""
        from src.data.event_models import EnhancedScoringWeights
        
        weights = EnhancedScoringWeights()
        
        assert weights.unusual_volume == 0.10
        assert weights.delta_movement == 0.08
        assert weights.implied_volatility == 0.05
        assert weights.smart_money_signal == 0.07
    
    def test_enhanced_total_weight(self):
        """Test that enhanced weights include all components."""
        from src.data.event_models import EnhancedScoringWeights
        
        weights = EnhancedScoringWeights()
        # Base weights (1.0) + enhanced weights (0.30)
        assert weights.total_weight == pytest.approx(1.30, rel=0.01)
    
    def test_enhanced_normalize(self):
        """Test enhanced weight normalization."""
        from src.data.event_models import EnhancedScoringWeights
        
        weights = EnhancedScoringWeights()
        normalized = weights.normalize()
        
        assert normalized.is_normalized()
        assert abs(normalized.total_weight - 1.0) < 0.01
    
    def test_enhanced_to_dict(self):
        """Test conversion to dictionary includes enhanced weights."""
        from src.data.event_models import EnhancedScoringWeights
        
        weights = EnhancedScoringWeights()
        d = weights.to_dict()
        
        assert "unusual_volume" in d
        assert "delta_movement" in d
        assert "implied_volatility" in d
        assert "smart_money_signal" in d
        assert len(d) == 11  # 7 base + 4 enhanced


class TestSignalSummaryModels:
    """Tests for SignalSummary and EnhancedSignalSummary models."""
    
    def test_signal_summary_creation(self):
        """Test creating a SignalSummary."""
        from src.data.event_models import SignalSummary
        
        summary = SignalSummary(
            strength=0.75,
            interpretation="Strong unusual volume signal",
            raw_value=2.5,
        )
        
        assert summary.strength == 0.75
        assert "Strong" in summary.interpretation
        assert summary.raw_value == 2.5
    
    def test_signal_summary_to_dict(self):
        """Test SignalSummary to_dict method."""
        from src.data.event_models import SignalSummary
        
        summary = SignalSummary(
            strength=0.5,
            interpretation="Moderate signal",
        )
        
        d = summary.to_dict()
        assert d["strength"] == 0.5
        assert d["interpretation"] == "Moderate signal"
    
    def test_enhanced_signal_summary_creation(self):
        """Test creating an EnhancedSignalSummary."""
        from src.data.event_models import SignalSummary, EnhancedSignalSummary
        
        summary = EnhancedSignalSummary(
            unusual_volume=SignalSummary(strength=0.8, interpretation="High"),
            delta_movement=SignalSummary(strength=0.5, interpretation="Moderate"),
            implied_volatility=SignalSummary(strength=0.3, interpretation="Low"),
            smart_money=SignalSummary(strength=0.7, interpretation="Notable"),
            overall_signal_strength=0.575,
        )
        
        assert summary.unusual_volume.strength == 0.8
        assert summary.overall_signal_strength == 0.575


class TestEnhancedEventScorer:
    """Tests for EnhancedEventScorer class."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    @pytest.fixture
    def high_activity_event(self) -> Dict[str, Any]:
        """Create a high-activity event for testing."""
        return {
            "id": "enhanced-001",
            "title": "High Activity Event",
            "volume": 10_000_000,
            "volume24hr": 500_000,
            "volume1wk": 700_000,  # Daily avg = 100k, so 500k is 5x
            "liquidity": 500_000,
            "openInterest": 1_000_000,
            "category": "economy",
            "markets": [
                {
                    "id": "market-001",
                    "oneDayPriceChange": 0.12,
                    "oneWeekPriceChange": 0.18,
                    "spread": 0.08,
                }
            ],
        }
    
    @pytest.fixture
    def low_activity_event(self) -> Dict[str, Any]:
        """Create a low-activity event for testing."""
        return {
            "id": "enhanced-002",
            "title": "Low Activity Event",
            "volume": 50_000,
            "volume24hr": 5_000,
            "volume1wk": 70_000,  # Daily avg = 10k, so 5k is 0.5x
            "liquidity": 10_000,
            "openInterest": 200_000,
            "category": "sports",
            "markets": [
                {
                    "id": "market-002",
                    "oneDayPriceChange": 0.01,
                    "oneWeekPriceChange": -0.02,
                    "spread": 0.01,
                }
            ],
        }


class TestUnusualVolumeSignal:
    """Tests for _unusual_volume_signal method."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_unusual_volume_signal_high_ratio(self, enhanced_scorer):
        """Test unusual volume signal with high ratio (>3x)."""
        event = {
            "volume24hr": 300_000,
            "volume1wk": 350_000,  # Daily avg = 50k, so 300k is 6x
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        assert signal >= 0.9  # Very high signal
        assert signal <= 1.0
    
    def test_unusual_volume_signal_moderate_ratio(self, enhanced_scorer):
        """Test unusual volume signal with moderate ratio (2x)."""
        event = {
            "volume24hr": 100_000,
            "volume1wk": 350_000,  # Daily avg = 50k, so 100k is 2x
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        assert 0.7 <= signal < 0.9  # Notable signal
    
    def test_unusual_volume_signal_low_ratio(self, enhanced_scorer):
        """Test unusual volume signal with low ratio (<1x)."""
        event = {
            "volume24hr": 25_000,
            "volume1wk": 350_000,  # Daily avg = 50k, so 25k is 0.5x
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        assert signal < 0.3  # Weak signal
    
    def test_unusual_volume_signal_normal_ratio(self, enhanced_scorer):
        """Test unusual volume signal with normal ratio (~1x)."""
        event = {
            "volume24hr": 50_000,
            "volume1wk": 350_000,  # Daily avg = 50k, so 50k is 1x
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        assert 0.3 <= signal <= 0.5  # Normal activity
    
    def test_unusual_volume_signal_no_weekly_data(self, enhanced_scorer):
        """Test unusual volume signal with no weekly volume - uses volume24hr fallback."""
        event = {
            "volume24hr": 100_000,
            "volume1wk": 0,
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        # With no weekly data but volume24hr present, uses volume24hr as fallback
        # 100K volume24hr falls in the $100K+ tier = 0.35
        assert 0.30 <= signal <= 0.40  # Uses volume24hr fallback
    
    def test_unusual_volume_signal_null_values(self, enhanced_scorer):
        """Test unusual volume signal with null values."""
        event = {
            "volume24hr": None,
            "volume1wk": None,
        }
        signal = enhanced_scorer._unusual_volume_signal(event)
        
        assert 0 <= signal <= 1.0  # Should not crash


class TestDeltaMovementSignal:
    """Tests for _delta_movement_signal method."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_delta_movement_signal_large_move(self, enhanced_scorer):
        """Test delta movement signal with large price move (>10%)."""
        market = {
            "oneDayPriceChange": 0.15,
            "oneWeekPriceChange": 0.20,
        }
        signal = enhanced_scorer._delta_movement_signal(market)
        
        assert signal >= 0.7  # Strong signal
    
    def test_delta_movement_signal_moderate_move(self, enhanced_scorer):
        """Test delta movement signal with moderate price move (5-10%)."""
        market = {
            "oneDayPriceChange": 0.06,
            "oneWeekPriceChange": 0.08,
        }
        signal = enhanced_scorer._delta_movement_signal(market)
        
        assert 0.4 <= signal < 0.7  # Moderate signal
    
    def test_delta_movement_signal_small_move(self, enhanced_scorer):
        """Test delta movement signal with small price move (<5%)."""
        market = {
            "oneDayPriceChange": 0.02,
            "oneWeekPriceChange": 0.03,
        }
        signal = enhanced_scorer._delta_movement_signal(market)
        
        assert signal < 0.4  # Weak signal
    
    def test_delta_movement_signal_consistent_direction_bonus(self, enhanced_scorer):
        """Test that consistent direction gets a bonus."""
        # Consistent positive
        market_consistent = {
            "oneDayPriceChange": 0.05,
            "oneWeekPriceChange": 0.05,
        }
        
        # Inconsistent direction
        market_inconsistent = {
            "oneDayPriceChange": 0.05,
            "oneWeekPriceChange": -0.05,
        }
        
        signal_consistent = enhanced_scorer._delta_movement_signal(market_consistent)
        signal_inconsistent = enhanced_scorer._delta_movement_signal(market_inconsistent)
        
        assert signal_consistent > signal_inconsistent
    
    def test_delta_movement_signal_no_market_data(self, enhanced_scorer):
        """Test delta movement signal with no market data returns low signal."""
        signal = enhanced_scorer._delta_movement_signal(None)
        
        assert signal == 0.20  # Low signal when no data available
    
    def test_delta_movement_signal_empty_market(self, enhanced_scorer):
        """Test delta movement signal with empty market dict."""
        signal = enhanced_scorer._delta_movement_signal({})
        
        assert 0 <= signal <= 1.0


class TestImpliedVolatilityProxy:
    """Tests for _implied_volatility_proxy method."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_implied_volatility_proxy_wide_spread(self, enhanced_scorer):
        """Test IV proxy with wide spread (>10%)."""
        market = {"spread": 0.12}
        signal = enhanced_scorer._implied_volatility_proxy(market)
        
        assert signal >= 0.8  # High uncertainty
    
    def test_implied_volatility_proxy_moderate_spread(self, enhanced_scorer):
        """Test IV proxy with moderate spread (5-10%)."""
        market = {"spread": 0.07}
        signal = enhanced_scorer._implied_volatility_proxy(market)
        
        assert 0.5 <= signal < 0.8  # Moderate uncertainty
    
    def test_implied_volatility_proxy_tight_spread(self, enhanced_scorer):
        """Test IV proxy with tight spread (<2%)."""
        market = {"spread": 0.01}
        signal = enhanced_scorer._implied_volatility_proxy(market)
        
        assert signal < 0.3  # Low uncertainty
    
    def test_implied_volatility_proxy_from_bid_ask(self, enhanced_scorer):
        """Test IV proxy calculated from bid/ask when spread not available."""
        market = {
            "spread": 0,
            "bestBid": 0.45,
            "bestAsk": 0.55,  # Spread = 0.10
        }
        signal = enhanced_scorer._implied_volatility_proxy(market)
        
        assert signal >= 0.5  # Should calculate from bid/ask
    
    def test_implied_volatility_proxy_no_market_data(self, enhanced_scorer):
        """Test IV proxy with no market data."""
        signal = enhanced_scorer._implied_volatility_proxy(None)
        
        assert signal == 0.5  # Neutral fallback


class TestSmartMoneySignal:
    """Tests for _smart_money_signal method."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_smart_money_signal_high_oi(self, enhanced_scorer):
        """Test smart money signal with high volume/OI ratio (>50%)."""
        event = {
            "volume24hr": 600_000,
            "openInterest": 1_000_000,  # 60% ratio
        }
        signal = enhanced_scorer._smart_money_signal(event)
        
        assert signal >= 0.8  # Very active institutional
    
    def test_smart_money_signal_moderate_oi(self, enhanced_scorer):
        """Test smart money signal with moderate volume/OI ratio (10-20%)."""
        event = {
            "volume24hr": 150_000,
            "openInterest": 1_000_000,  # 15% ratio
        }
        signal = enhanced_scorer._smart_money_signal(event)
        
        assert 0.3 <= signal < 0.5  # Moderate activity
    
    def test_smart_money_signal_low_oi(self, enhanced_scorer):
        """Test smart money signal with low volume/OI ratio (<5%)."""
        event = {
            "volume24hr": 30_000,
            "openInterest": 1_000_000,  # 3% ratio
        }
        signal = enhanced_scorer._smart_money_signal(event)
        
        assert signal < 0.3  # Low activity
    
    def test_smart_money_signal_no_oi_high_volume(self, enhanced_scorer):
        """Test smart money signal with no OI but high volume."""
        event = {
            "volume24hr": 150_000,
            "openInterest": 0,
        }
        signal = enhanced_scorer._smart_money_signal(event)
        
        assert signal >= 0.45  # Falls back to volume-based
    
    def test_smart_money_signal_no_oi_low_volume(self, enhanced_scorer):
        """Test smart money signal with no OI and low volume."""
        event = {
            "volume24hr": 5_000,
            "openInterest": 0,
        }
        signal = enhanced_scorer._smart_money_signal(event)
        
        assert signal <= 0.3  # Low activity fallback


class TestGetSignalSummary:
    """Tests for get_signal_summary method."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_get_signal_summary(self, enhanced_scorer):
        """Test get_signal_summary returns complete summary."""
        event = {
            "id": "test-001",
            "volume24hr": 200_000,
            "volume1wk": 350_000,
            "openInterest": 500_000,
        }
        market = {
            "oneDayPriceChange": 0.08,
            "oneWeekPriceChange": 0.12,
            "spread": 0.05,
        }
        
        summary = enhanced_scorer.get_signal_summary(event, market)
        
        assert 0 <= summary.unusual_volume.strength <= 1.0
        assert 0 <= summary.delta_movement.strength <= 1.0
        assert 0 <= summary.implied_volatility.strength <= 1.0
        assert 0 <= summary.smart_money.strength <= 1.0
        assert 0 <= summary.overall_signal_strength <= 1.0
        
        # Check interpretations are present
        assert len(summary.unusual_volume.interpretation) > 0
        assert len(summary.delta_movement.interpretation) > 0
    
    def test_get_signal_summary_extracts_market_from_event(self, enhanced_scorer):
        """Test that get_signal_summary extracts market from event if not provided."""
        event = {
            "id": "test-002",
            "volume24hr": 100_000,
            "volume1wk": 200_000,
            "openInterest": 300_000,
            "markets": [
                {
                    "oneDayPriceChange": 0.05,
                    "oneWeekPriceChange": 0.08,
                    "spread": 0.03,
                }
            ],
        }
        
        summary = enhanced_scorer.get_signal_summary(event)
        
        # Should have calculated delta movement from embedded market
        assert summary.delta_movement.strength > 0.3
    
    def test_get_signal_summary_to_dict(self, enhanced_scorer):
        """Test get_signal_summary to_dict method."""
        event = {
            "volume24hr": 100_000,
            "volume1wk": 200_000,
            "openInterest": 300_000,
        }
        market = {
            "oneDayPriceChange": 0.05,
            "spread": 0.02,
        }
        
        summary = enhanced_scorer.get_signal_summary(event, market)
        d = summary.to_dict()
        
        assert "unusual_volume" in d
        assert "delta_movement" in d
        assert "implied_volatility" in d
        assert "smart_money" in d
        assert "overall_signal_strength" in d
        
        assert "strength" in d["unusual_volume"]
        assert "interpretation" in d["unusual_volume"]


class TestSignalInterpretationHelpers:
    """Tests for signal interpretation helper functions."""
    
    def test_interpret_signal_strong(self):
        """Test interpret_signal for strong signals."""
        from src.tools.event_scorer import interpret_signal
        
        result = interpret_signal("unusual_volume", 0.85)
        assert "Strong" in result
        assert "unusual volume" in result
    
    def test_interpret_signal_moderate(self):
        """Test interpret_signal for moderate signals."""
        from src.tools.event_scorer import interpret_signal
        
        result = interpret_signal("delta_movement", 0.55)
        assert "Moderate" in result
    
    def test_interpret_signal_weak(self):
        """Test interpret_signal for weak signals."""
        from src.tools.event_scorer import interpret_signal
        
        result = interpret_signal("smart_money", 0.25)
        assert "Weak" in result
    
    def test_interpret_unusual_volume(self):
        """Test interpret_unusual_volume function."""
        from src.tools.event_scorer import interpret_unusual_volume
        
        assert "Very high" in interpret_unusual_volume(3.5)
        assert "High" in interpret_unusual_volume(2.5)
        assert "Elevated" in interpret_unusual_volume(1.7)
        assert "Normal" in interpret_unusual_volume(1.0)
        assert "Below" in interpret_unusual_volume(0.6)
        assert "Low" in interpret_unusual_volume(0.3)
    
    def test_interpret_delta_movement(self):
        """Test interpret_delta_movement function."""
        from src.tools.event_scorer import interpret_delta_movement
        
        assert "Major" in interpret_delta_movement(0.18)
        assert "Large" in interpret_delta_movement(0.12)
        assert "Moderate" in interpret_delta_movement(0.07)
        assert "Minor" in interpret_delta_movement(0.03)
        assert "Minimal" in interpret_delta_movement(0.01)
    
    def test_interpret_implied_volatility(self):
        """Test interpret_implied_volatility function."""
        from src.tools.event_scorer import interpret_implied_volatility
        
        assert "Very high" in interpret_implied_volatility(0.12)
        assert "High" in interpret_implied_volatility(0.07)
        assert "Moderate" in interpret_implied_volatility(0.03)
        assert "Low" in interpret_implied_volatility(0.015)
        assert "Very low" in interpret_implied_volatility(0.005)
    
    def test_interpret_smart_money(self):
        """Test interpret_smart_money function."""
        from src.tools.event_scorer import interpret_smart_money
        
        assert "Very high" in interpret_smart_money(0.6)
        assert "High" in interpret_smart_money(0.3)
        assert "Moderate" in interpret_smart_money(0.15)
        assert "Low" in interpret_smart_money(0.07)
        assert "Minimal" in interpret_smart_money(0.02)


class TestEnhancedScorerIntegration:
    """Integration tests for EnhancedEventScorer."""
    
    @pytest.fixture
    def enhanced_scorer(self):
        """Create an EnhancedEventScorer instance."""
        from src.tools.event_scorer import EnhancedEventScorer
        return EnhancedEventScorer()
    
    def test_score_event_enhanced(self, enhanced_scorer):
        """Test score_event_enhanced includes enhanced signals."""
        event = {
            "id": "test-001",
            "title": "Test Event",
            "volume": 5_000_000,
            "volume24hr": 300_000,
            "volume1wk": 700_000,
            "liquidity": 200_000,
            "openInterest": 800_000,
            "category": "economy",
            "endDate": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "markets": [
                {
                    "oneDayPriceChange": 0.08,
                    "oneWeekPriceChange": 0.12,
                    "spread": 0.04,
                }
            ],
        }
        
        score = enhanced_scorer.score_event_enhanced(event)
        
        assert score.event_id == "test-001"
        assert 0 <= score.total_score <= 100
        
        # Check enhanced components are present
        assert "unusual_volume" in score.component_scores
        assert "delta_movement" in score.component_scores
        assert "implied_volatility" in score.component_scores
        assert "smart_money_signal" in score.component_scores
    
    def test_create_enhanced_scorer_factory(self):
        """Test create_enhanced_scorer factory function."""
        from src.tools.event_scorer import create_enhanced_scorer
        
        scorer = create_enhanced_scorer(
            enhanced_weights={"unusual_volume": 0.15, "smart_money_signal": 0.10},
            min_score_threshold=65,
        )
        
        assert scorer.config.min_score_threshold == 65
        assert scorer.enhanced_weights is not None
    
    def test_enhanced_scorer_inherits_base_methods(self, enhanced_scorer):
        """Test that EnhancedEventScorer inherits base EventScorer methods."""
        event = {
            "id": "test-001",
            "title": "Test Event",
            "volume": 1_000_000,
            "liquidity": 100_000,
            "category": "economy",
        }
        
        # Should be able to use base score_event method
        base_score = enhanced_scorer.score_event(event)
        assert base_score.event_id == "test-001"
        
        # Should be able to use rank_events
        events = [event, {"id": "test-002", "title": "Test 2", "volume": 500_000}]
        ranked = enhanced_scorer.rank_events(events)
        assert len(ranked.events) == 2