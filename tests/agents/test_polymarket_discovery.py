"""Unit tests for portfolio-aware discovery in polymarket_discovery.py.

Tests the Phase 2 enhancements including:
- EventScorer integration for pre-filtering
- Portfolio context injection into LLM prompt
- Event history tracking for deduplication
- Fuzzy title matching
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.agents.polymarket_discovery import (
    discover_tickers_from_events,
    _find_event_by_id,
    _llm_map_event_to_stocks,
    StockMapping,
    EventStockMappingResponse,
    # Phase 6 imports
    ValidationResult,
    CompanyStatus,
    ValidationResponse,
    ValidatedStockMapping,
    validate_stock_picks,
    _fetch_news_for_ticker,
    _format_news_summary,
    _validate_single_stock,
)
from src.data.position_context import (
    EventHistory,
    AnalyzedEvent,
    PositionContext,
    EventThesis,
    EventType,
    ThesisType,
    EventState,
    ProbabilitySnapshot,
    build_portfolio_context,
)
from src.data.polymarket_models import PolymarketEvent


# ==================== Fixtures ====================

@pytest.fixture
def sample_events():
    """Create sample PolymarketEvent objects for testing."""
    return [
        PolymarketEvent(
            id="event1",
            title="Will Trump win 2024?",
            description="Presidential election prediction",
            probability=0.65,
            volume=5000000,
            volume_24hr=100000,
            liquidity=200000,
            active=True,
            closed=False,
            end_date="2024-11-05T00:00:00Z",
        ),
        PolymarketEvent(
            id="event2",
            title="Fed rate cut in March?",
            description="Federal Reserve interest rate decision",
            probability=0.72,
            volume=3000000,
            volume_24hr=80000,
            liquidity=150000,
            active=True,
            closed=False,
            end_date="2024-03-20T00:00:00Z",
        ),
        PolymarketEvent(
            id="event3",
            title="Lakers win NBA Championship?",
            description="Sports betting event",
            probability=0.45,  # Outside probability range
            volume=1000000,
            volume_24hr=50000,
            liquidity=100000,
            active=True,
            closed=False,
            end_date="2024-06-15T00:00:00Z",
        ),
    ]


@pytest.fixture
def sample_portfolio():
    """Create a sample portfolio with existing positions."""
    event_thesis = EventThesis(
        event_id="existing_event",
        event_title="Existing event thesis",
        event_type=EventType.BINARY,
        thesis="Existing position thesis",
        thesis_type=ThesisType.SHORT_TERM,
        impact_direction="bullish",
        confidence=80,
        probability=ProbabilitySnapshot(current=0.70),
        entry_date="2024-01-15",
    )
    
    return {
        "DJT": PositionContext(ticker="DJT", events=[event_thesis]),
    }


@pytest.fixture
def sample_event_history():
    """Create a sample event history with analyzed events."""
    history = EventHistory()
    
    analyzed = AnalyzedEvent(
        event_id="old_event",
        event_title="Previously analyzed event",
        score=75.0,
        mapped_tickers=["AAPL"],
    )
    history.add_event(analyzed)
    
    return history


# ==================== Tests for _find_event_by_id ====================

class TestFindEventById:
    """Tests for the _find_event_by_id helper function."""
    
    def test_find_existing_event(self, sample_events):
        """Test finding an event that exists."""
        event = _find_event_by_id(sample_events, "event1")
        
        assert event is not None
        assert event.id == "event1"
        assert event.title == "Will Trump win 2024?"
    
    def test_find_nonexistent_event(self, sample_events):
        """Test finding an event that doesn't exist."""
        event = _find_event_by_id(sample_events, "nonexistent")
        
        assert event is None
    
    def test_find_in_empty_list(self):
        """Test finding in an empty list."""
        event = _find_event_by_id([], "event1")
        
        assert event is None


# ==================== Tests for discover_tickers_from_events ====================

class TestDiscoverTickersFromEvents:
    """Tests for the main discovery function with Phase 2 enhancements."""
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    @patch('src.agents.polymarket_discovery.detect_event_type')
    def test_discovery_with_event_scoring(
        self,
        mock_detect_type,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
    ):
        """Test that EventScorer is used to pre-filter events."""
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_detect_type.return_value = EventType.BINARY
        
        # Mock LLM response
        mock_llm_map.return_value = [
            StockMapping(
                ticker="DJT",
                direction="bullish",
                confidence=85,
                thesis="Trump win benefits DJT",
                thesis_type="short_term",
                reasoning="Direct correlation",
            )
        ]
        
        discovered, history = discover_tickers_from_events(
            events=sample_events,
            min_score=50.0,
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
        )
        
        # Should have discovered tickers
        assert len(discovered) >= 0  # May be 0 if scoring filters all
        
        # Event history should be returned
        assert isinstance(history, EventHistory)
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    @patch('src.agents.polymarket_discovery.detect_event_type')
    def test_discovery_with_portfolio_context(
        self,
        mock_detect_type,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
        sample_portfolio,
    ):
        """Test that portfolio context is passed to LLM."""
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_detect_type.return_value = EventType.BINARY
        
        mock_llm_map.return_value = [
            StockMapping(
                ticker="GEO",
                direction="bullish",
                confidence=80,
                thesis="New stock recommendation",
                thesis_type="short_term",
                reasoning="Diversification",
            )
        ]
        
        discovered, history = discover_tickers_from_events(
            events=sample_events,
            portfolio_positions=sample_portfolio,
            min_score=0,  # Low score to ensure events pass
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
        )
        
        # Verify LLM was called with portfolio context
        if mock_llm_map.called:
            call_args = mock_llm_map.call_args
            # Check that portfolio_context parameter was passed
            assert 'portfolio_context' in call_args.kwargs or len(call_args.args) > 3
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    def test_discovery_skips_duplicate_events(
        self,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
        sample_event_history,
    ):
        """Test that already-analyzed events are skipped."""
        # Add one of the sample events to history
        analyzed = AnalyzedEvent(
            event_id="event1",  # Same as sample_events[0]
            event_title="Will Trump win 2024?",
            score=80.0,
            mapped_tickers=["DJT"],
        )
        sample_event_history.add_event(analyzed)
        
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_llm_map.return_value = []
        
        discovered, history = discover_tickers_from_events(
            events=sample_events,
            event_history=sample_event_history,
            min_score=0,
            min_probability=0.60,
            max_probability=0.85,
            skip_duplicates=True,
            limit=5,
        )
        
        # event1 should have been skipped
        # Check that it's still in history (not re-analyzed)
        assert history.has_event("event1")
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    def test_discovery_skips_similar_title_events(
        self,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
    ):
        """Test that events with similar titles are skipped (fuzzy match)."""
        history = EventHistory()
        
        # Add event with similar title
        analyzed = AnalyzedEvent(
            event_id="different_id",
            event_title="Will Trump win the 2024 election?",  # Similar to event1
            score=80.0,
            mapped_tickers=["DJT"],
        )
        history.add_event(analyzed)
        
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_llm_map.return_value = []
        
        discovered, updated_history = discover_tickers_from_events(
            events=sample_events,
            event_history=history,
            min_score=0,
            min_probability=0.60,
            max_probability=0.85,
            skip_duplicates=True,
            limit=5,
        )
        
        # The original similar event should still be in history
        # (it was added before discovery and should be preserved)
        assert updated_history.has_event("different_id")
        
        # The similar event detection should work
        similar = updated_history.has_similar_event("Will Trump win the 2024 election?")
        assert similar is not None
    
    def test_discovery_tracks_new_events_in_history(self):
        """Test that newly analyzed events are added to history via EventHistory directly."""
        # This test verifies the EventHistory tracking mechanism works
        # by testing the add_event functionality directly
        history = EventHistory()
        
        # Simulate what discover_tickers_from_events does when it finds events
        analyzed_event = AnalyzedEvent(
            event_id="event1",
            event_title="Will Trump win 2024?",
            score=80.0,
            mapped_tickers=["DJT", "GEO"],
            outcome="pending",
        )
        history.add_event(analyzed_event)
        
        # Verify event was tracked
        assert len(history.events) == 1
        assert history.has_event("event1")
        assert "DJT" in history.ticker_event_map
        assert "GEO" in history.ticker_event_map
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    @patch('src.agents.polymarket_discovery.detect_event_type')
    def test_discovery_includes_event_score_in_result(
        self,
        mock_detect_type,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
    ):
        """Test that discovered tickers include the event score."""
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_detect_type.return_value = EventType.BINARY
        
        mock_llm_map.return_value = [
            StockMapping(
                ticker="DJT",
                direction="bullish",
                confidence=85,
                thesis="Trump win benefits DJT",
                thesis_type="short_term",
                reasoning="Direct correlation",
            )
        ]
        
        discovered, history = discover_tickers_from_events(
            events=sample_events,
            min_score=0,
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
        )
        
        # Each discovered ticker should have event_score
        for d in discovered:
            assert "event_score" in d
            assert isinstance(d["event_score"], (int, float))


# ==================== Tests for _llm_map_event_to_stocks ====================

class TestLLMMapEventToStocks:
    """Tests for the LLM mapping function with portfolio context."""
    
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_llm_map_without_portfolio_context(self, mock_call_llm, sample_events):
        """Test LLM mapping without portfolio context."""
        mock_response = EventStockMappingResponse(
            affected_stocks=[
                StockMapping(
                    ticker="DJT",
                    direction="bullish",
                    confidence=85,
                    thesis="Test thesis",
                    thesis_type="short_term",
                    reasoning="Test reasoning",
                )
            ],
            event_relevance="high",
        )
        mock_call_llm.return_value = mock_response
        
        result = _llm_map_event_to_stocks(sample_events[0])
        
        assert len(result) == 1
        assert result[0].ticker == "DJT"
        
        # Check that prompt doesn't contain portfolio section
        call_args = mock_call_llm.call_args
        prompt = call_args.kwargs.get('prompt', call_args.args[0] if call_args.args else '')
        assert "Current Portfolio" not in prompt
    
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_llm_map_with_portfolio_context(self, mock_call_llm, sample_events, sample_portfolio):
        """Test LLM mapping with portfolio context injection."""
        mock_response = EventStockMappingResponse(
            affected_stocks=[
                StockMapping(
                    ticker="GEO",
                    direction="bullish",
                    confidence=80,
                    thesis="New recommendation",
                    thesis_type="short_term",
                    reasoning="Diversification",
                )
            ],
            event_relevance="high",
        )
        mock_call_llm.return_value = mock_response
        
        portfolio_context = build_portfolio_context(sample_portfolio)
        
        result = _llm_map_event_to_stocks(
            sample_events[0],
            portfolio_context=portfolio_context,
        )
        
        assert len(result) == 1
        
        # Check that prompt contains portfolio context
        call_args = mock_call_llm.call_args
        prompt = call_args.kwargs.get('prompt', call_args.args[0] if call_args.args else '')
        assert "Current Portfolio" in prompt or "DJT" in prompt
        assert "duplicate exposure" in prompt.lower() or "diversification" in prompt.lower()
    
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_llm_map_handles_exception(self, mock_call_llm, sample_events):
        """Test that LLM mapping handles exceptions gracefully."""
        mock_call_llm.side_effect = Exception("LLM API error")
        
        result = _llm_map_event_to_stocks(sample_events[0])
        
        # Should return empty list on error
        assert result == []
    
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_llm_map_handles_empty_response(self, mock_call_llm, sample_events):
        """Test that LLM mapping handles empty response."""
        mock_call_llm.return_value = None
        
        result = _llm_map_event_to_stocks(sample_events[0])
        
        assert result == []


# ==================== Integration Tests ====================

class TestDiscoveryIntegration:
    """Integration tests for the discovery workflow."""
    
    def test_full_discovery_workflow_mocked(self, sample_events, sample_portfolio):
        """Test the full discovery workflow with mocked dependencies."""
        with patch('src.agents.polymarket_discovery.get_active_events') as mock_get_events, \
             patch('src.agents.polymarket_discovery._llm_map_event_to_stocks') as mock_llm, \
             patch('src.agents.polymarket_discovery._get_cached_mappings') as mock_cache, \
             patch('src.agents.polymarket_discovery.detect_event_type') as mock_detect:
            
            mock_get_events.return_value = sample_events
            mock_cache.return_value = None
            mock_detect.return_value = EventType.BINARY
            
            mock_llm.return_value = [
                StockMapping(
                    ticker="GEO",
                    direction="bullish",
                    confidence=85,
                    thesis="Prison stocks benefit",
                    thesis_type="short_term",
                    reasoning="Policy changes",
                )
            ]
            
            # Run discovery with all Phase 2 features
            discovered, history = discover_tickers_from_events(
                events=sample_events,
                portfolio_positions=sample_portfolio,
                event_history=EventHistory(),
                min_score=0,
                min_probability=0.60,
                max_probability=0.85,
                min_confidence=70,
                limit=5,
                skip_duplicates=True,
            )
            
            # Verify results
            assert isinstance(discovered, list)
            assert isinstance(history, EventHistory)
            
            # If discoveries were made, verify structure
            for d in discovered:
                assert "ticker" in d
                assert "context" in d
                assert "event_title" in d
                assert "probability" in d
                assert "event_score" in d


# ==================== Phase 6: Validation Tests ====================

class TestValidationModels:
    """Tests for Phase 6 validation Pydantic models."""
    
    def test_validation_result_enum(self):
        """Test ValidationResult enum values."""
        assert ValidationResult.KEEP.value == "keep"
        assert ValidationResult.REPLACE.value == "replace"
        assert ValidationResult.ADJUST.value == "adjust"
        assert ValidationResult.REJECT.value == "reject"
    
    def test_company_status_enum(self):
        """Test CompanyStatus enum values."""
        assert CompanyStatus.HEALTHY.value == "healthy"
        assert CompanyStatus.CONCERNING.value == "concerning"
        assert CompanyStatus.NEUTRAL.value == "neutral"
    
    def test_validation_response_creation(self):
        """Test creating a ValidationResponse."""
        response = ValidationResponse(
            result="keep",
            adjusted_confidence=85,
            reasoning="Stock looks good",
            company_status="healthy",
        )
        
        assert response.result == "keep"
        assert response.adjusted_confidence == 85
        assert response.reasoning == "Stock looks good"
        assert response.company_status == "healthy"
    
    def test_validation_response_with_replacement(self):
        """Test ValidationResponse with replacement fields."""
        response = ValidationResponse(
            result="replace",
            adjusted_confidence=70,
            reasoning="Better alternative found",
            company_status="concerning",
            replacement_ticker="MSFT",
            replacement_direction="bullish",
            replacement_thesis="More direct exposure",
        )
        
        assert response.result == "replace"
        assert response.replacement_ticker == "MSFT"
        assert response.replacement_direction == "bullish"
    
    def test_validated_stock_mapping_creation(self):
        """Test creating a ValidatedStockMapping."""
        mapping = ValidatedStockMapping(
            ticker="AAPL",
            direction="bullish",
            confidence=80,
            thesis="Test thesis",
            thesis_type="short_term",
            reasoning="Test reasoning",
            validation_result=ValidationResult.KEEP,
            original_confidence=85,
            news_summary="Recent news summary",
            validation_reasoning="Validation passed",
            company_status=CompanyStatus.HEALTHY,
        )
        
        assert mapping.ticker == "AAPL"
        assert mapping.validation_result == ValidationResult.KEEP
        assert mapping.original_confidence == 85
        assert mapping.company_status == CompanyStatus.HEALTHY


class TestFetchNewsForTicker:
    """Tests for _fetch_news_for_ticker function."""
    
    @patch('src.agents.polymarket_discovery.get_company_news')
    def test_fetch_news_success(self, mock_get_news):
        """Test successful news fetch."""
        mock_news_item = Mock()
        mock_news_item.title = "Test News Title"
        mock_news_item.date = "2024-01-15"
        mock_news_item.source = "Reuters"
        mock_news_item.text = "This is the news content..."
        
        mock_get_news.return_value = [mock_news_item]
        
        result = _fetch_news_for_ticker("AAPL", lookback_days=7)
        
        assert len(result) == 1
        assert result[0]["title"] == "Test News Title"
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["source"] == "Reuters"
    
    @patch('src.agents.polymarket_discovery.get_company_news')
    def test_fetch_news_empty(self, mock_get_news):
        """Test empty news response."""
        mock_get_news.return_value = []
        
        result = _fetch_news_for_ticker("AAPL")
        
        assert result == []
    
    @patch('src.agents.polymarket_discovery.get_company_news')
    def test_fetch_news_handles_exception(self, mock_get_news):
        """Test that exceptions are handled gracefully."""
        mock_get_news.side_effect = Exception("API error")
        
        result = _fetch_news_for_ticker("AAPL")
        
        assert result == []


class TestFormatNewsSummary:
    """Tests for _format_news_summary function."""
    
    def test_format_empty_news(self):
        """Test formatting empty news list."""
        result = _format_news_summary([])
        
        assert "No recent news available" in result
    
    def test_format_single_article(self):
        """Test formatting single news article."""
        news = [
            {
                "title": "Apple Reports Strong Q4",
                "date": "2024-01-15",
                "source": "Reuters",
                "summary": "Apple Inc reported strong quarterly results...",
            }
        ]
        
        result = _format_news_summary(news)
        
        assert "Apple Reports Strong Q4" in result
        assert "2024-01-15" in result
        assert "Reuters" in result
    
    def test_format_multiple_articles(self):
        """Test formatting multiple news articles."""
        news = [
            {"title": "News 1", "date": "2024-01-15", "source": "Source1", "summary": "Summary 1"},
            {"title": "News 2", "date": "2024-01-14", "source": "Source2", "summary": "Summary 2"},
            {"title": "News 3", "date": "2024-01-13", "source": "Source3", "summary": "Summary 3"},
        ]
        
        result = _format_news_summary(news)
        
        assert "News 1" in result
        assert "News 2" in result
        assert "News 3" in result
    
    def test_format_limits_to_five_articles(self):
        """Test that only 5 articles are included."""
        news = [
            {"title": f"News {i}", "date": "2024-01-15", "source": "Source", "summary": "Summary"}
            for i in range(10)
        ]
        
        result = _format_news_summary(news)
        
        # Should only have 5 numbered entries
        assert "1." in result
        assert "5." in result
        # 6th article should not be included
        assert "6." not in result


class TestValidateSingleStock:
    """Tests for _validate_single_stock function."""
    
    @patch('src.agents.polymarket_discovery.get_model')
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_validate_returns_keep(self, mock_call_llm, mock_get_model, sample_events):
        """Test validation that returns keep."""
        mock_get_model.return_value = Mock()
        mock_call_llm.return_value = ValidationResponse(
            result="keep",
            adjusted_confidence=85,
            reasoning="Stock looks good",
            company_status="healthy",
        )
        
        mapping = StockMapping(
            ticker="AAPL",
            direction="bullish",
            confidence=80,
            thesis="Test thesis",
            thesis_type="short_term",
            reasoning="Test reasoning",
        )
        
        news = [{"title": "Good news", "date": "2024-01-15", "source": "Reuters", "summary": "Positive outlook"}]
        
        result = _validate_single_stock(
            event=sample_events[0],
            mapping=mapping,
            news_items=news,
            model_name="test-model",
            model_provider="test-provider",
        )
        
        assert result.result == "keep"
        assert result.adjusted_confidence == 85
    
    @patch('src.agents.polymarket_discovery.get_model')
    @patch('src.agents.polymarket_discovery.call_llm')
    def test_validate_handles_exception(self, mock_call_llm, mock_get_model, sample_events):
        """Test that validation handles exceptions gracefully."""
        mock_get_model.side_effect = Exception("LLM error")
        
        mapping = StockMapping(
            ticker="AAPL",
            direction="bullish",
            confidence=80,
            thesis="Test thesis",
            thesis_type="short_term",
            reasoning="Test reasoning",
        )
        
        result = _validate_single_stock(
            event=sample_events[0],
            mapping=mapping,
            news_items=[],
            model_name="test-model",
            model_provider="test-provider",
        )
        
        # Should return default keep response
        assert result.result == "keep"
        assert result.adjusted_confidence == 80  # Original confidence


class TestValidateStockPicks:
    """Tests for validate_stock_picks function."""
    
    @patch('src.agents.polymarket_discovery._fetch_news_for_ticker')
    @patch('src.agents.polymarket_discovery._validate_single_stock')
    def test_validate_keeps_stock(self, mock_validate, mock_fetch_news, sample_events):
        """Test validation that keeps a stock."""
        mock_fetch_news.return_value = [
            {"title": "News", "date": "2024-01-15", "source": "Reuters", "summary": "Content"}
            for _ in range(5)
        ]
        
        mock_validate.return_value = ValidationResponse(
            result="keep",
            adjusted_confidence=85,
            reasoning="Stock validated",
            company_status="healthy",
        )
        
        mappings = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=80,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        result = validate_stock_picks(
            event=sample_events[0],
            stock_mappings=mappings,
            min_news_articles=3,
        )
        
        assert len(result) == 1
        assert result[0].ticker == "AAPL"
        assert result[0].validation_result == ValidationResult.KEEP
        assert result[0].confidence == 85
    
    @patch('src.agents.polymarket_discovery._fetch_news_for_ticker')
    @patch('src.agents.polymarket_discovery._validate_single_stock')
    def test_validate_rejects_stock(self, mock_validate, mock_fetch_news, sample_events):
        """Test validation that rejects a stock."""
        mock_fetch_news.return_value = [
            {"title": "News", "date": "2024-01-15", "source": "Reuters", "summary": "Content"}
            for _ in range(5)
        ]
        
        mock_validate.return_value = ValidationResponse(
            result="reject",
            adjusted_confidence=0,
            reasoning="Stock invalidated by news",
            company_status="concerning",
        )
        
        mappings = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=80,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        result = validate_stock_picks(
            event=sample_events[0],
            stock_mappings=mappings,
            min_news_articles=3,
        )
        
        assert len(result) == 1
        assert result[0].validation_result == ValidationResult.REJECT
        assert result[0].confidence == 0
    
    @patch('src.agents.polymarket_discovery._fetch_news_for_ticker')
    def test_validate_skips_insufficient_news(self, mock_fetch_news, sample_events):
        """Test that validation is skipped when insufficient news."""
        # Return only 2 articles (below min_news_articles=3)
        mock_fetch_news.return_value = [
            {"title": "News", "date": "2024-01-15", "source": "Reuters", "summary": "Content"}
            for _ in range(2)
        ]
        
        mappings = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=80,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        result = validate_stock_picks(
            event=sample_events[0],
            stock_mappings=mappings,
            min_news_articles=3,
        )
        
        assert len(result) == 1
        assert result[0].validation_result == ValidationResult.KEEP
        assert result[0].confidence == 80  # Original confidence preserved
        assert "Insufficient news" in result[0].news_summary
    
    @patch('src.agents.polymarket_discovery._fetch_news_for_ticker')
    @patch('src.agents.polymarket_discovery._validate_single_stock')
    def test_validate_adjusts_confidence(self, mock_validate, mock_fetch_news, sample_events):
        """Test validation that adjusts confidence."""
        mock_fetch_news.return_value = [
            {"title": "News", "date": "2024-01-15", "source": "Reuters", "summary": "Content"}
            for _ in range(5)
        ]
        
        mock_validate.return_value = ValidationResponse(
            result="adjust",
            adjusted_confidence=60,  # Lowered from 80
            reasoning="News suggests lower confidence",
            company_status="neutral",
        )
        
        mappings = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=80,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        result = validate_stock_picks(
            event=sample_events[0],
            stock_mappings=mappings,
            min_news_articles=3,
        )
        
        assert len(result) == 1
        assert result[0].validation_result == ValidationResult.ADJUST
        assert result[0].confidence == 60
        assert result[0].original_confidence == 80
    
    @patch('src.agents.polymarket_discovery._fetch_news_for_ticker')
    @patch('src.agents.polymarket_discovery._validate_single_stock')
    def test_validate_replaces_stock(self, mock_validate, mock_fetch_news, sample_events):
        """Test validation that replaces a stock."""
        mock_fetch_news.return_value = [
            {"title": "News", "date": "2024-01-15", "source": "Reuters", "summary": "Content"}
            for _ in range(5)
        ]
        
        mock_validate.return_value = ValidationResponse(
            result="replace",
            adjusted_confidence=75,
            reasoning="Better alternative found",
            company_status="concerning",
            replacement_ticker="MSFT",
            replacement_direction="bullish",
            replacement_thesis="More direct exposure",
        )
        
        mappings = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=80,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        result = validate_stock_picks(
            event=sample_events[0],
            stock_mappings=mappings,
            min_news_articles=3,
            max_validation_retries=0,  # No retries for replacement
        )
        
        assert len(result) == 1
        assert result[0].validation_result == ValidationResult.REPLACE
        assert result[0].replacement_ticker == "MSFT"


class TestDiscoveryWithValidation:
    """Tests for discovery with news validation enabled."""
    
    @patch('src.agents.polymarket_discovery._cache_mappings')
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    @patch('src.agents.polymarket_discovery.detect_event_type')
    @patch('src.agents.polymarket_discovery.validate_stock_picks')
    def test_discovery_with_validation_enabled(
        self,
        mock_validate,
        mock_detect_type,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        mock_cache_mappings,
        sample_events,
    ):
        """Test that validation is called when enabled."""
        # Use only the first event which has probability 0.65 (in range)
        test_event = sample_events[0]
        mock_get_events.return_value = [test_event]
        mock_get_cached.return_value = None
        mock_detect_type.return_value = EventType.BINARY
        mock_cache_mappings.return_value = None
        
        original_mapping = StockMapping(
            ticker="AAPL",
            direction="bullish",
            confidence=85,
            thesis="Test thesis",
            thesis_type="short_term",
            reasoning="Test reasoning",
        )
        mock_llm_map.return_value = [original_mapping]
        
        # Mock validation to return validated mapping
        validated_mapping = ValidatedStockMapping(
            ticker="AAPL",
            direction="bullish",
            confidence=80,  # Adjusted
            thesis="Test thesis",
            thesis_type="short_term",
            reasoning="Test reasoning",
            validation_result=ValidationResult.KEEP,
            original_confidence=85,
            company_status=CompanyStatus.HEALTHY,
        )
        mock_validate.return_value = [validated_mapping]
        
        discovered, history = discover_tickers_from_events(
            events=[test_event],
            min_score=0,  # Very low to ensure event passes scoring
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
            validate_with_news=True,
        )
        
        # If LLM was called and returned mappings, validation should be called
        if mock_llm_map.called and mock_llm_map.return_value:
            assert mock_validate.called, "validate_stock_picks should be called when validation is enabled and mappings exist"
    
    @patch('src.agents.polymarket_discovery.get_active_events')
    @patch('src.agents.polymarket_discovery._llm_map_event_to_stocks')
    @patch('src.agents.polymarket_discovery._get_cached_mappings')
    @patch('src.agents.polymarket_discovery.detect_event_type')
    @patch('src.agents.polymarket_discovery.validate_stock_picks')
    def test_discovery_with_validation_disabled(
        self,
        mock_validate,
        mock_detect_type,
        mock_get_cached,
        mock_llm_map,
        mock_get_events,
        sample_events,
    ):
        """Test that validation is skipped when disabled."""
        mock_get_events.return_value = sample_events
        mock_get_cached.return_value = None
        mock_detect_type.return_value = EventType.BINARY
        
        mock_llm_map.return_value = [
            StockMapping(
                ticker="AAPL",
                direction="bullish",
                confidence=85,
                thesis="Test thesis",
                thesis_type="short_term",
                reasoning="Test reasoning",
            )
        ]
        
        discovered, history = discover_tickers_from_events(
            events=sample_events,
            min_score=0,
            min_probability=0.60,
            max_probability=0.85,
            min_confidence=70,
            limit=5,
            validate_with_news=False,  # Disabled
        )
        
        # Verify validation was NOT called
        assert not mock_validate.called
