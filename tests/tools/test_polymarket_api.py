"""Unit tests for Polymarket API resolved events functionality.

Tests for:
- get_resolved_events() - Fetch resolved/closed events for backtesting
- get_event_outcome() - Determine event outcome from resolved markets
- get_market_outcome() - Determine market outcome
- get_resolved_events_with_outcomes() - Combined fetch and outcome determination
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.tools.polymarket_api import (
    get_resolved_events,
    get_event_outcome,
    get_market_outcome,
    get_resolved_events_with_outcomes,
)
from src.data.polymarket_models import (
    PolymarketEvent,
    PolymarketMarket,
)


# ==================== Test Fixtures ====================


@pytest.fixture
def mock_resolved_event_yes():
    """Create a mock resolved event where Yes won."""
    return PolymarketEvent(
        id="event-123",
        title="Will X happen by 2024?",
        slug="will-x-happen-by-2024",
        description="Test event description",
        volume=500000,
        liquidity=50000,
        closed=True,
        markets=[
            PolymarketMarket(
                id="market-123",
                question="Will X happen?",
                closed=True,
                outcomes=["Yes", "No"],
                outcome_prices=["1.0", "0.0"],  # Yes won
                volume=500000,
                liquidity=50000,
                clob_token_ids=["token-yes", "token-no"],
            )
        ],
    )


@pytest.fixture
def mock_resolved_event_no():
    """Create a mock resolved event where No won."""
    return PolymarketEvent(
        id="event-456",
        title="Will Y happen by 2024?",
        slug="will-y-happen-by-2024",
        description="Test event description",
        volume=300000,
        liquidity=30000,
        closed=True,
        markets=[
            PolymarketMarket(
                id="market-456",
                question="Will Y happen?",
                closed=True,
                outcomes=["Yes", "No"],
                outcome_prices=["0.0", "1.0"],  # No won
                volume=300000,
                liquidity=30000,
                clob_token_ids=["token-yes", "token-no"],
            )
        ],
    )


@pytest.fixture
def mock_unresolved_event():
    """Create a mock unresolved event."""
    return PolymarketEvent(
        id="event-789",
        title="Will Z happen by 2025?",
        slug="will-z-happen-by-2025",
        description="Test event description",
        volume=200000,
        liquidity=20000,
        closed=False,
        markets=[
            PolymarketMarket(
                id="market-789",
                question="Will Z happen?",
                closed=False,
                outcomes=["Yes", "No"],
                outcome_prices=["0.65", "0.35"],  # Not resolved
                volume=200000,
                liquidity=20000,
                clob_token_ids=["token-yes", "token-no"],
            )
        ],
    )


@pytest.fixture
def mock_api_response_resolved_events():
    """Mock API response for resolved events."""
    return [
        {
            "id": "event-123",
            "title": "Will X happen by 2024?",
            "slug": "will-x-happen-by-2024",
            "description": "Test event",
            "volume": 500000,
            "liquidity": 50000,
            "closed": True,
            "markets": [
                {
                    "id": "market-123",
                    "question": "Will X happen?",
                    "closed": True,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["1.0", "0.0"]',
                    "volume": 500000,
                    "liquidity": 50000,
                    "clobTokenIds": '["token-yes", "token-no"]',
                }
            ],
        },
        {
            "id": "event-456",
            "title": "Will Y happen by 2024?",
            "slug": "will-y-happen-by-2024",
            "description": "Test event 2",
            "volume": 300000,
            "liquidity": 30000,
            "closed": True,
            "markets": [
                {
                    "id": "market-456",
                    "question": "Will Y happen?",
                    "closed": True,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.0", "1.0"]',
                    "volume": 300000,
                    "liquidity": 30000,
                    "clobTokenIds": '["token-yes", "token-no"]',
                }
            ],
        },
    ]


# ==================== Tests for get_event_outcome ====================


class TestGetEventOutcome:
    """Tests for get_event_outcome function."""

    def test_get_event_outcome_yes_winner(self, mock_resolved_event_yes):
        """Test that Yes outcome is correctly identified."""
        outcome = get_event_outcome(mock_resolved_event_yes)
        assert outcome == "Yes"

    def test_get_event_outcome_no_winner(self, mock_resolved_event_no):
        """Test that No outcome is correctly identified."""
        outcome = get_event_outcome(mock_resolved_event_no)
        assert outcome == "No"

    def test_get_event_outcome_not_resolved(self, mock_unresolved_event):
        """Test that unresolved events return None."""
        outcome = get_event_outcome(mock_unresolved_event)
        assert outcome is None

    def test_get_event_outcome_no_markets(self):
        """Test event with no markets returns None."""
        event = PolymarketEvent(
            id="event-no-markets",
            title="Event without markets",
            closed=True,
            markets=[],
        )
        outcome = get_event_outcome(event)
        assert outcome is None

    def test_get_event_outcome_no_outcome_prices(self):
        """Test event with no outcome prices returns None."""
        event = PolymarketEvent(
            id="event-no-prices",
            title="Event without prices",
            closed=True,
            markets=[
                PolymarketMarket(
                    id="market-no-prices",
                    question="Test?",
                    closed=True,
                    outcomes=["Yes", "No"],
                    outcome_prices=None,
                )
            ],
        )
        outcome = get_event_outcome(event)
        assert outcome is None

    def test_get_event_outcome_partial_resolution(self):
        """Test event with partial resolution (not 0 or 1) returns None."""
        event = PolymarketEvent(
            id="event-partial",
            title="Partially resolved event",
            closed=True,
            markets=[
                PolymarketMarket(
                    id="market-partial",
                    question="Test?",
                    closed=True,
                    outcomes=["Yes", "No"],
                    outcome_prices=["0.75", "0.25"],  # Not fully resolved
                )
            ],
        )
        outcome = get_event_outcome(event)
        assert outcome is None

    def test_get_event_outcome_market_not_closed(self):
        """Test event where market is not closed returns None."""
        event = PolymarketEvent(
            id="event-market-open",
            title="Event with open market",
            closed=True,
            markets=[
                PolymarketMarket(
                    id="market-open",
                    question="Test?",
                    closed=False,  # Market not closed
                    outcomes=["Yes", "No"],
                    outcome_prices=["1.0", "0.0"],
                )
            ],
        )
        outcome = get_event_outcome(event)
        assert outcome is None


# ==================== Tests for get_market_outcome ====================


class TestGetMarketOutcome:
    """Tests for get_market_outcome function."""

    def test_get_market_outcome_yes_winner(self):
        """Test Yes outcome for market."""
        market = PolymarketMarket(
            id="market-yes",
            question="Test?",
            closed=True,
            outcomes=["Yes", "No"],
            outcome_prices=["1.0", "0.0"],
        )
        outcome = get_market_outcome(market)
        assert outcome == "Yes"

    def test_get_market_outcome_no_winner(self):
        """Test No outcome for market."""
        market = PolymarketMarket(
            id="market-no",
            question="Test?",
            closed=True,
            outcomes=["Yes", "No"],
            outcome_prices=["0.0", "1.0"],
        )
        outcome = get_market_outcome(market)
        assert outcome == "No"

    def test_get_market_outcome_not_closed(self):
        """Test market not closed returns None."""
        market = PolymarketMarket(
            id="market-open",
            question="Test?",
            closed=False,
            outcomes=["Yes", "No"],
            outcome_prices=["0.65", "0.35"],
        )
        outcome = get_market_outcome(market)
        assert outcome is None

    def test_get_market_outcome_threshold_yes(self):
        """Test Yes outcome at threshold (0.99)."""
        market = PolymarketMarket(
            id="market-threshold",
            question="Test?",
            closed=True,
            outcomes=["Yes", "No"],
            outcome_prices=["0.99", "0.01"],
        )
        outcome = get_market_outcome(market)
        assert outcome == "Yes"

    def test_get_market_outcome_threshold_no(self):
        """Test No outcome at threshold (0.01)."""
        market = PolymarketMarket(
            id="market-threshold",
            question="Test?",
            closed=True,
            outcomes=["Yes", "No"],
            outcome_prices=["0.01", "0.99"],
        )
        outcome = get_market_outcome(market)
        assert outcome == "No"


# ==================== Tests for get_resolved_events ====================


class TestGetResolvedEvents:
    """Tests for get_resolved_events function."""

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_date_range(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test fetching resolved events with date range filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        events = get_resolved_events(
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_volume=100000,
        )

        assert len(events) == 2
        assert events[0].id == "event-123"
        assert events[1].id == "event-456"

        # Verify API was called with correct params
        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", call_args[1].get("params", {}))
        assert params["closed"] == "true"
        assert params["end_date_min"] == "2024-01-01"
        assert params["end_date_max"] == "2024-12-31"
        assert params["volume_num_min"] == 100000

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_volume_filter(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test fetching resolved events with volume filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        events = get_resolved_events(
            min_volume=50000,
            min_liquidity=5000,
        )

        assert len(events) == 2

        # Verify API was called with correct params
        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", call_args[1].get("params", {}))
        assert params["volume_num_min"] == 50000
        assert params["liquidity_num_min"] == 5000

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_category_filter(
        self, mock_request
    ):
        """Test fetching resolved events with category filter."""
        # Create events with different categories
        mock_response_data = [
            {
                "id": "event-politics",
                "title": "Political event",
                "slug": "political-event",
                "volume": 500000,
                "liquidity": 50000,
                "closed": True,
                "tags": [{"label": "Politics"}],
                "markets": [
                    {
                        "id": "market-1",
                        "question": "Test?",
                        "closed": True,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["1.0", "0.0"]',
                    }
                ],
            },
            {
                "id": "event-crypto",
                "title": "Crypto event",
                "slug": "crypto-event",
                "volume": 300000,
                "liquidity": 30000,
                "closed": True,
                "tags": [{"label": "Crypto"}],
                "markets": [
                    {
                        "id": "market-2",
                        "question": "Test?",
                        "closed": True,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.0", "1.0"]',
                    }
                ],
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_request.return_value = mock_response

        # Filter by politics category
        events = get_resolved_events(
            categories=["Politics"],
            min_volume=100000,
        )

        assert len(events) == 1
        assert events[0].id == "event-politics"
        assert events[0].category == "Politics"

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_empty_response(self, mock_request):
        """Test handling empty response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        events = get_resolved_events(min_volume=1000000000)

        assert len(events) == 0

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_api_error(self, mock_request):
        """Test handling API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_request.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            get_resolved_events()

        assert "Error fetching resolved events" in str(exc_info.value)

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_cache(self, mock_request, mock_api_response_resolved_events):
        """Test caching of resolved events."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        # Create mock cache
        mock_cache = MagicMock()
        mock_cache.get_events.return_value = None  # Cache miss

        events = get_resolved_events(
            min_volume=100000,
            cache=mock_cache,
        )

        assert len(events) == 2
        # Verify cache was checked and set
        mock_cache.get_events.assert_called_once()
        mock_cache.set_events.assert_called_once()


# ==================== Tests for get_resolved_events_with_outcomes ====================


class TestGetResolvedEventsWithOutcomes:
    """Tests for get_resolved_events_with_outcomes function."""

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_outcomes(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test fetching resolved events with outcomes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        results = get_resolved_events_with_outcomes(
            min_volume=100000,
            limit=10,
        )

        assert len(results) == 2
        assert results[0]["event"].id == "event-123"
        assert results[0]["outcome"] == "Yes"
        assert results[1]["event"].id == "event-456"
        assert results[1]["outcome"] == "No"

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_outcomes_filter_yes(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test filtering by Yes outcome."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        results = get_resolved_events_with_outcomes(
            outcome_filter="Yes",
            min_volume=100000,
        )

        assert len(results) == 1
        assert results[0]["outcome"] == "Yes"

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_outcomes_filter_no(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test filtering by No outcome."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        results = get_resolved_events_with_outcomes(
            outcome_filter="No",
            min_volume=100000,
        )

        assert len(results) == 1
        assert results[0]["outcome"] == "No"

    @patch("src.tools.polymarket_api._make_api_request")
    def test_get_resolved_events_with_outcomes_limit(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test limit parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        results = get_resolved_events_with_outcomes(
            min_volume=100000,
            limit=1,
        )

        assert len(results) == 1


# ==================== Integration-style Tests ====================


class TestResolvedEventsIntegration:
    """Integration-style tests for resolved events workflow."""

    @patch("src.tools.polymarket_api._make_api_request")
    def test_full_workflow_fetch_and_determine_outcomes(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test full workflow of fetching events and determining outcomes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        # Fetch resolved events
        events = get_resolved_events(
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_volume=100000,
        )

        # Determine outcomes for each event
        outcomes = {}
        for event in events:
            outcome = get_event_outcome(event)
            outcomes[event.id] = outcome

        assert outcomes["event-123"] == "Yes"
        assert outcomes["event-456"] == "No"

    @patch("src.tools.polymarket_api._make_api_request")
    def test_backtest_accuracy_calculation(
        self, mock_request, mock_api_response_resolved_events
    ):
        """Test calculating backtest accuracy against actual outcomes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response_resolved_events
        mock_request.return_value = mock_response

        # Simulate predictions
        predictions = {
            "event-123": "Yes",  # Correct
            "event-456": "Yes",  # Incorrect (actual is No)
        }

        # Fetch events and calculate accuracy
        events = get_resolved_events(min_volume=100000)
        
        correct = 0
        total = 0
        
        for event in events:
            actual = get_event_outcome(event)
            predicted = predictions.get(event.id)
            
            if actual and predicted:
                total += 1
                if actual == predicted:
                    correct += 1

        accuracy = correct / total if total > 0 else 0
        
        assert total == 2
        assert correct == 1
        assert accuracy == 0.5
