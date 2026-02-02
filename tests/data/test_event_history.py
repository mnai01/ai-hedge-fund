"""Unit tests for EventHistory and AnalyzedEvent models.

Tests the event history tracking functionality for deduplication
in the portfolio-aware discovery system.
"""

import pytest
from datetime import datetime, timedelta

from src.data.position_context import (
    AnalyzedEvent,
    EventHistory,
    PositionContext,
    EventThesis,
    EventType,
    ThesisType,
    EventState,
    ProbabilitySnapshot,
    build_portfolio_context,
)


class TestAnalyzedEvent:
    """Tests for the AnalyzedEvent model."""
    
    def test_create_analyzed_event(self):
        """Test creating an AnalyzedEvent with required fields."""
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=85.0,
            mapped_tickers=["DJT", "GEO"],
        )
        
        assert event.event_id == "event123"
        assert event.event_title == "Will Trump win 2024?"
        assert event.score == 85.0
        assert event.mapped_tickers == ["DJT", "GEO"]
        assert event.outcome is None
        # analyzed_at should be auto-generated
        assert event.analyzed_at is not None
    
    def test_analyzed_event_with_outcome(self):
        """Test creating an AnalyzedEvent with outcome."""
        event = AnalyzedEvent(
            event_id="event456",
            event_title="Fed rate cut in March?",
            score=72.5,
            mapped_tickers=["JPM", "BAC"],
            outcome="profitable",
        )
        
        assert event.outcome == "profitable"
    
    def test_analyzed_event_empty_tickers(self):
        """Test creating an AnalyzedEvent with no mapped tickers."""
        event = AnalyzedEvent(
            event_id="event789",
            event_title="Sports event with no stock impact",
            score=30.0,
            mapped_tickers=[],
        )
        
        assert event.mapped_tickers == []


class TestEventHistory:
    """Tests for the EventHistory model."""
    
    def test_create_empty_history(self):
        """Test creating an empty EventHistory."""
        history = EventHistory()
        
        assert len(history.events) == 0
        assert len(history.ticker_event_map) == 0
    
    def test_add_event(self):
        """Test adding an event to history."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=85.0,
            mapped_tickers=["DJT", "GEO"],
        )
        
        history.add_event(event)
        
        assert len(history.events) == 1
        assert "event123" in history.events
        assert history.events["event123"].event_title == "Will Trump win 2024?"
    
    def test_add_event_updates_ticker_map(self):
        """Test that adding an event updates the ticker_event_map."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=85.0,
            mapped_tickers=["DJT", "GEO"],
        )
        
        history.add_event(event)
        
        assert "DJT" in history.ticker_event_map
        assert "GEO" in history.ticker_event_map
        assert "event123" in history.ticker_event_map["DJT"]
        assert "event123" in history.ticker_event_map["GEO"]
    
    def test_has_event(self):
        """Test checking if an event exists in history."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Test event",
            score=50.0,
            mapped_tickers=[],
        )
        
        history.add_event(event)
        
        assert history.has_event("event123") is True
        assert history.has_event("nonexistent") is False
    
    def test_has_similar_event_exact_match(self):
        """Test fuzzy matching with exact title match."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=85.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # Exact match should return the event
        similar = history.has_similar_event("Will Trump win 2024?")
        assert similar is not None
        assert similar.event_id == "event123"
    
    def test_has_similar_event_fuzzy_match(self):
        """Test fuzzy matching with similar title."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win the 2024 election?",
            score=85.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # Similar title should match (above 0.85 threshold)
        similar = history.has_similar_event("Will Trump win 2024 election?")
        assert similar is not None
        assert similar.event_id == "event123"
    
    def test_has_similar_event_no_match(self):
        """Test fuzzy matching with dissimilar title."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=85.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # Very different title should not match
        similar = history.has_similar_event("Fed rate decision in March")
        assert similar is None
    
    def test_get_events_for_ticker(self):
        """Test getting all events for a specific ticker."""
        history = EventHistory()
        
        event1 = AnalyzedEvent(
            event_id="event1",
            event_title="Event 1",
            score=80.0,
            mapped_tickers=["TSLA", "NVDA"],
        )
        event2 = AnalyzedEvent(
            event_id="event2",
            event_title="Event 2",
            score=70.0,
            mapped_tickers=["TSLA", "AAPL"],
        )
        event3 = AnalyzedEvent(
            event_id="event3",
            event_title="Event 3",
            score=60.0,
            mapped_tickers=["MSFT"],
        )
        
        history.add_event(event1)
        history.add_event(event2)
        history.add_event(event3)
        
        # TSLA should have 2 events
        tsla_events = history.get_events_for_ticker("TSLA")
        assert len(tsla_events) == 2
        assert any(e.event_id == "event1" for e in tsla_events)
        assert any(e.event_id == "event2" for e in tsla_events)
        
        # MSFT should have 1 event
        msft_events = history.get_events_for_ticker("MSFT")
        assert len(msft_events) == 1
        assert msft_events[0].event_id == "event3"
        
        # Unknown ticker should return empty list
        unknown_events = history.get_events_for_ticker("UNKNOWN")
        assert len(unknown_events) == 0
    
    def test_get_recent_events(self):
        """Test getting events within a time window."""
        history = EventHistory()
        
        # Create event with current timestamp
        recent_event = AnalyzedEvent(
            event_id="recent",
            event_title="Recent event",
            score=80.0,
            mapped_tickers=["TSLA"],
        )
        
        # Create event with old timestamp
        old_event = AnalyzedEvent(
            event_id="old",
            event_title="Old event",
            analyzed_at=(datetime.now() - timedelta(hours=48)).isoformat(),
            score=70.0,
            mapped_tickers=["AAPL"],
        )
        
        history.add_event(recent_event)
        history.add_event(old_event)
        
        # Get events from last 24 hours
        recent = history.get_recent_events(hours=24)
        assert len(recent) == 1
        assert recent[0].event_id == "recent"
        
        # Get events from last 72 hours
        all_recent = history.get_recent_events(hours=72)
        assert len(all_recent) == 2
    
    def test_get_ticker_exposure_count(self):
        """Test counting events with exposure to a ticker."""
        history = EventHistory()
        
        event1 = AnalyzedEvent(
            event_id="event1",
            event_title="Event 1",
            score=80.0,
            mapped_tickers=["TSLA", "NVDA"],
        )
        event2 = AnalyzedEvent(
            event_id="event2",
            event_title="Event 2",
            score=70.0,
            mapped_tickers=["TSLA"],
        )
        
        history.add_event(event1)
        history.add_event(event2)
        
        assert history.get_ticker_exposure_count("TSLA") == 2
        assert history.get_ticker_exposure_count("NVDA") == 1
        assert history.get_ticker_exposure_count("UNKNOWN") == 0
    
    def test_should_skip_event_by_id(self):
        """Test deduplication check by event ID."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Test event",
            score=80.0,
            mapped_tickers=["TSLA"],
        )
        
        history.add_event(event)
        
        # Same event ID should be skipped
        should_skip, reason = history.should_skip_event("event123", "Different title")
        assert should_skip is True
        assert "already analyzed" in reason
        
        # New event ID should not be skipped
        should_skip, reason = history.should_skip_event("new_event", "New event title")
        assert should_skip is False
        assert reason is None
    
    def test_should_skip_event_by_fuzzy_title(self):
        """Test deduplication check by fuzzy title match."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win the 2024 presidential election?",
            score=80.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # Similar title should be skipped
        should_skip, reason = history.should_skip_event(
            "new_event_id",
            "Will Trump win 2024 presidential election?"
        )
        assert should_skip is True
        assert "Similar event" in reason
    
    def test_should_skip_event_fuzzy_disabled(self):
        """Test deduplication with fuzzy matching disabled."""
        history = EventHistory()
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win the 2024 presidential election?",
            score=80.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # Similar title should NOT be skipped when fuzzy is disabled
        should_skip, reason = history.should_skip_event(
            "new_event_id",
            "Will Trump win 2024 presidential election?",
            check_fuzzy=False,
        )
        assert should_skip is False
        assert reason is None
    
    def test_clear_old_events(self):
        """Test clearing old events from history."""
        history = EventHistory()
        
        # Create recent event
        recent_event = AnalyzedEvent(
            event_id="recent",
            event_title="Recent event",
            score=80.0,
            mapped_tickers=["TSLA"],
        )
        
        # Create old event (40 days ago)
        old_event = AnalyzedEvent(
            event_id="old",
            event_title="Old event",
            analyzed_at=(datetime.now() - timedelta(days=40)).isoformat(),
            score=70.0,
            mapped_tickers=["AAPL"],
        )
        
        history.add_event(recent_event)
        history.add_event(old_event)
        
        assert len(history.events) == 2
        
        # Clear events older than 30 days
        removed = history.clear_old_events(days=30)
        
        assert removed == 1
        assert len(history.events) == 1
        assert "recent" in history.events
        assert "old" not in history.events
        
        # Ticker map should also be cleaned
        assert "AAPL" not in history.ticker_event_map or len(history.ticker_event_map["AAPL"]) == 0
    
    def test_get_summary(self):
        """Test getting history summary statistics."""
        history = EventHistory()
        
        event1 = AnalyzedEvent(
            event_id="event1",
            event_title="Event 1",
            score=80.0,
            mapped_tickers=["TSLA", "NVDA"],
        )
        event2 = AnalyzedEvent(
            event_id="event2",
            event_title="Event 2",
            score=70.0,
            mapped_tickers=["AAPL"],
        )
        
        history.add_event(event1)
        history.add_event(event2)
        
        summary = history.get_summary()
        
        assert summary["total_events"] == 2
        assert summary["total_tickers"] == 3  # TSLA, NVDA, AAPL
        assert summary["recent_24h"] == 2
    
    def test_custom_fuzzy_threshold(self):
        """Test EventHistory with custom fuzzy match threshold."""
        history = EventHistory(fuzzy_match_threshold=0.95)
        
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Will Trump win 2024?",
            score=80.0,
            mapped_tickers=["DJT"],
        )
        
        history.add_event(event)
        
        # With higher threshold, similar but not exact should not match
        similar = history.has_similar_event("Will Trump win the 2024 election?")
        assert similar is None  # Should not match with 0.95 threshold
        
        # Exact match should still work
        exact = history.has_similar_event("Will Trump win 2024?")
        assert exact is not None


class TestBuildPortfolioContext:
    """Tests for the build_portfolio_context function."""
    
    def test_empty_portfolio(self):
        """Test building context for empty portfolio."""
        context = build_portfolio_context({})
        
        assert "Empty" in context
        assert "no existing positions" in context
    
    def test_portfolio_with_positions(self):
        """Test building context for portfolio with positions."""
        # Create a position context
        event_thesis = EventThesis(
            event_id="event123",
            event_title="Will Trump win 2024?",
            event_type=EventType.BINARY,
            thesis="Trump win would benefit private prison stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=85,
            probability=ProbabilitySnapshot(current=0.65),
            entry_date="2024-01-15",
        )
        
        position = PositionContext(
            ticker="GEO",
            events=[event_thesis],
        )
        
        portfolio = {"GEO": position}
        context = build_portfolio_context(portfolio)
        
        assert "GEO" in context
        assert "bullish" in context
        assert "Active Theses: 1" in context
        assert "Trump" in context
        assert "diversification" in context.lower()
    
    def test_portfolio_with_multiple_positions(self):
        """Test building context for portfolio with multiple positions."""
        event1 = EventThesis(
            event_id="event1",
            event_title="Event 1",
            event_type=EventType.BINARY,
            thesis="Thesis 1",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=0.70),
            entry_date="2024-01-15",
        )
        
        event2 = EventThesis(
            event_id="event2",
            event_title="Event 2",
            event_type=EventType.BINARY,
            thesis="Thesis 2",
            thesis_type=ThesisType.LONG_TERM,
            impact_direction="bearish",
            confidence=75,
            probability=ProbabilitySnapshot(current=0.60),
            entry_date="2024-01-16",
        )
        
        position1 = PositionContext(ticker="TSLA", events=[event1])
        position2 = PositionContext(ticker="NVDA", events=[event2])
        
        portfolio = {"TSLA": position1, "NVDA": position2}
        context = build_portfolio_context(portfolio)
        
        assert "TSLA" in context
        assert "NVDA" in context
        assert "bullish" in context
        assert "bearish" in context


class TestEventHistorySerialization:
    """Tests for EventHistory serialization/deserialization."""
    
    def test_model_dump_and_restore(self):
        """Test that EventHistory can be serialized and restored."""
        history = EventHistory()
        
        event = AnalyzedEvent(
            event_id="event123",
            event_title="Test event",
            score=80.0,
            mapped_tickers=["TSLA", "NVDA"],
        )
        
        history.add_event(event)
        
        # Serialize
        data = history.model_dump()
        
        # Restore
        restored = EventHistory(**data)
        
        assert len(restored.events) == 1
        assert "event123" in restored.events
        assert restored.events["event123"].event_title == "Test event"
        assert "TSLA" in restored.ticker_event_map
        assert "NVDA" in restored.ticker_event_map


class TestExitGuidance:
    """Tests for thesis-type-aware exit guidance functionality."""
    
    def test_active_event_no_guidance(self):
        """Test that active events return no exit guidance."""
        event = EventThesis(
            event_id="event123",
            event_title="Trump wins 2024",
            event_type=EventType.BINARY,
            event_state=EventState.ACTIVE,
            thesis="Trump win benefits private prison stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=0.65),
            entry_date="2024-01-15",
        )
        
        assert event.get_exit_guidance() is None
        assert event.get_thesis_with_guidance() == event.thesis
    
    def test_short_term_bullish_resolved_yes(self):
        """Test short-term bullish thesis with RESOLVED_YES (catalyst realized)."""
        event = EventThesis(
            event_id="event123",
            event_title="Trump wins 2024",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_YES,
            thesis="Trump win benefits private prison stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=1.0),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "SHORT-TERM CATALYST REALIZED" in guidance
        assert "taking profits" in guidance
        assert "Trump wins 2024" in guidance
    
    def test_short_term_bullish_resolved_no(self):
        """Test short-term bullish thesis with RESOLVED_NO (catalyst failed)."""
        event = EventThesis(
            event_id="event123",
            event_title="Trump wins 2024",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_NO,
            thesis="Trump win benefits private prison stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=0.0),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "SHORT-TERM CATALYST FAILED" in guidance
        assert "exiting position" in guidance
    
    def test_short_term_bearish_resolved_no(self):
        """Test short-term bearish thesis with RESOLVED_NO (catalyst realized for bearish)."""
        event = EventThesis(
            event_id="event123",
            event_title="Trump wins 2024",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_NO,
            thesis="Trump loss benefits solar stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bearish",  # Bearish if Trump wins, so NO is good
            confidence=80,
            probability=ProbabilitySnapshot(current=0.0),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        # For bearish thesis, RESOLVED_NO means thesis validated
        assert "SHORT-TERM CATALYST REALIZED" in guidance
        assert "taking profits" in guidance
    
    def test_long_term_bullish_resolved_yes(self):
        """Test long-term bullish thesis with RESOLVED_YES (structural thesis validated)."""
        event = EventThesis(
            event_id="event123",
            event_title="Fed cuts rates",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_YES,
            thesis="Rate cuts benefit growth stocks structurally",
            thesis_type=ThesisType.LONG_TERM,
            impact_direction="bullish",
            confidence=85,
            probability=ProbabilitySnapshot(current=1.0),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "STRUCTURAL THESIS VALIDATED" in guidance
        assert "holding" in guidance.lower()
    
    def test_long_term_bullish_resolved_no(self):
        """Test long-term bullish thesis with RESOLVED_NO (structural thesis challenged)."""
        event = EventThesis(
            event_id="event123",
            event_title="Fed cuts rates",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_NO,
            thesis="Rate cuts benefit growth stocks structurally",
            thesis_type=ThesisType.LONG_TERM,
            impact_direction="bullish",
            confidence=85,
            probability=ProbabilitySnapshot(current=0.0),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "STRUCTURAL THESIS CHALLENGED" in guidance
        assert "Reassess" in guidance
    
    def test_expired_short_term(self):
        """Test short-term thesis with EXPIRED event."""
        event = EventThesis(
            event_id="event123",
            event_title="BTC ATH by March",
            event_type=EventType.SEQUENTIAL,
            event_state=EventState.EXPIRED,
            thesis="BTC rally benefits crypto stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=70,
            probability=ProbabilitySnapshot(current=0.5),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "EVENT EXPIRED" in guidance
        assert "short-term catalyst is no longer valid" in guidance
    
    def test_expired_long_term(self):
        """Test long-term thesis with EXPIRED event."""
        event = EventThesis(
            event_id="event123",
            event_title="AI regulation by 2025",
            event_type=EventType.BINARY,
            event_state=EventState.EXPIRED,
            thesis="AI regulation benefits established players",
            thesis_type=ThesisType.LONG_TERM,
            impact_direction="bullish",
            confidence=75,
            probability=ProbabilitySnapshot(current=0.5),
            entry_date="2024-01-15",
        )
        
        guidance = event.get_exit_guidance()
        assert guidance is not None
        assert "EVENT EXPIRED" in guidance
        assert "Long-term thesis may still be valid" in guidance
    
    def test_get_thesis_with_guidance_includes_both(self):
        """Test that get_thesis_with_guidance includes both thesis and guidance."""
        event = EventThesis(
            event_id="event123",
            event_title="Trump wins 2024",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_YES,
            thesis="Trump win benefits private prison stocks",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=1.0),
            entry_date="2024-01-15",
        )
        
        full_thesis = event.get_thesis_with_guidance()
        
        # Should contain original thesis
        assert "Trump win benefits private prison stocks" in full_thesis
        # Should contain exit guidance
        assert "SHORT-TERM CATALYST REALIZED" in full_thesis
    
    def test_get_all_theses_includes_guidance(self):
        """Test that PositionContext.get_all_theses includes exit guidance."""
        active_event = EventThesis(
            event_id="event1",
            event_title="Active Event",
            event_type=EventType.BINARY,
            event_state=EventState.ACTIVE,
            thesis="Active thesis",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=0.65),
            entry_date="2024-01-15",
        )
        
        resolved_event = EventThesis(
            event_id="event2",
            event_title="Resolved Event",
            event_type=EventType.BINARY,
            event_state=EventState.RESOLVED_YES,
            thesis="Resolved thesis",
            thesis_type=ThesisType.SHORT_TERM,
            impact_direction="bullish",
            confidence=80,
            probability=ProbabilitySnapshot(current=1.0),
            entry_date="2024-01-15",
        )
        
        position = PositionContext(
            ticker="TSLA",
            events=[active_event, resolved_event],
        )
        
        theses = position.get_all_theses()
        
        assert len(theses) == 2
        # Active thesis should not have guidance
        assert "Active thesis" in theses[0]
        assert "CATALYST" not in theses[0]
        # Resolved thesis should have guidance
        assert "Resolved thesis" in theses[1]
        assert "SHORT-TERM CATALYST REALIZED" in theses[1]
