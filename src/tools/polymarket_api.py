"""Polymarket API client for fetching events and price history.

This module provides functions to interact with:
- Gamma API: Fetch events and markets
- CLOB API: Fetch historical price/probability data

Follows patterns from src/tools/api.py for retry logic and caching.
"""

import json
import time
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Literal

from src.data.polymarket_models import (
    PolymarketEvent,
    PolymarketMarket,
    PriceHistory,
    PricePoint,
    ProbabilityChange,
)


# API Base URLs
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Default request timeout
DEFAULT_TIMEOUT = 30


def _make_api_request(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
) -> requests.Response:
    """
    Make an API request with rate limiting handling and moderate backoff.
    
    Follows the pattern from src/tools/api.py.
    
    Args:
        url: The URL to request
        headers: Headers to include in the request
        params: Query parameters
        max_retries: Maximum number of retries (default: 3)
        timeout: Request timeout in seconds
    
    Returns:
        requests.Response: The response object
    
    Raises:
        Exception: If the request fails after all retries
    """
    headers = headers or {}
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            
            if response.status_code == 429 and attempt < max_retries:
                # Rate limited - use linear backoff: 60s, 90s, 120s
                delay = 60 + (30 * attempt)
                print(f"Rate limited (429). Attempt {attempt + 1}/{max_retries + 1}. Waiting {delay}s before retrying...")
                time.sleep(delay)
                continue
            
            return response
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                delay = 5 * (attempt + 1)
                print(f"Request timeout. Attempt {attempt + 1}/{max_retries + 1}. Waiting {delay}s before retrying...")
                time.sleep(delay)
                continue
            raise Exception(f"Request to {url} timed out after {max_retries + 1} attempts")
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                delay = 5 * (attempt + 1)
                print(f"Request error: {e}. Attempt {attempt + 1}/{max_retries + 1}. Waiting {delay}s before retrying...")
                time.sleep(delay)
                continue
            raise Exception(f"Request to {url} failed after {max_retries + 1} attempts: {e}")
    
    # Should not reach here, but return last response if we do
    return response


def get_active_events(
    limit: int = 100,
    offset: int = 0,
    order: str = "volume",
    ascending: bool = False,
    tag: Optional[str] = None,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch active events from the Gamma API.
    
    Args:
        limit: Maximum number of events to return (default: 100)
        offset: Offset for pagination
        order: Field to order by (volume, liquidity, startDate, endDate)
        ascending: Sort order
        tag: Filter by tag/category
        cache: Optional cache instance for storing results
    
    Returns:
        List of PolymarketEvent objects
    
    Example:
        >>> events = get_active_events(limit=10)
        >>> for e in events:
        ...     print(f"{e.title}: {e.probability:.1%}")
    """
    # Build cache key
    cache_key = f"events_{limit}_{offset}_{order}_{ascending}_{tag or 'all'}"
    
    # Check cache first
    if cache:
        cached_data = cache.get_events(cache_key)
        if cached_data:
            return [PolymarketEvent(**e) for e in cached_data]
    
    # Build request URL and params
    url = f"{GAMMA_API_BASE}/events"
    params = {
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "order": order,
        "ascending": str(ascending).lower(),
    }
    
    if tag:
        params["tag"] = tag
    
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching events: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        # The API returns a list of events directly
        if isinstance(data, list):
            events = [PolymarketEvent(**event_data) for event_data in data]
        else:
            # Handle case where API returns wrapped response
            events_data = data.get("events", data.get("data", []))
            events = [PolymarketEvent(**event_data) for event_data in events_data]
        
        # Cache the results
        if cache and events:
            cache.set_events(cache_key, [e.model_dump() for e in events])
        
        return events
        
    except Exception as e:
        raise Exception(f"Error parsing events response: {e}")


def get_event_by_id(event_id: str, cache: Optional[Any] = None) -> Optional[PolymarketEvent]:
    """
    Fetch a specific event by its ID.
    
    Args:
        event_id: The event ID
        cache: Optional cache instance
    
    Returns:
        PolymarketEvent or None if not found
    """
    cache_key = f"event_{event_id}"
    
    if cache:
        cached_data = cache.get_event(cache_key)
        if cached_data:
            return PolymarketEvent(**cached_data)
    
    url = f"{GAMMA_API_BASE}/events/{event_id}"
    response = _make_api_request(url)
    
    if response.status_code == 404:
        return None
    
    if response.status_code != 200:
        raise Exception(f"Error fetching event {event_id}: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        event = PolymarketEvent(**data)
        
        if cache:
            cache.set_event(cache_key, event.model_dump())
        
        return event
        
    except Exception as e:
        raise Exception(f"Error parsing event response: {e}")


def get_event_by_slug(slug: str, cache: Optional[Any] = None) -> Optional[PolymarketEvent]:
    """
    Fetch a specific event by its slug.
    
    Args:
        slug: The event slug (URL-friendly identifier)
        cache: Optional cache instance
    
    Returns:
        PolymarketEvent or None if not found
    """
    cache_key = f"event_slug_{slug}"
    
    if cache:
        cached_data = cache.get_event(cache_key)
        if cached_data:
            return PolymarketEvent(**cached_data)
    
    url = f"{GAMMA_API_BASE}/events"
    params = {"slug": slug}
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching event by slug {slug}: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            event = PolymarketEvent(**data[0])
        elif isinstance(data, dict):
            events_list = data.get("events", data.get("data", []))
            if events_list:
                event = PolymarketEvent(**events_list[0])
            else:
                return None
        else:
            return None
        
        if cache:
            cache.set_event(cache_key, event.model_dump())
        
        return event
        
    except Exception as e:
        raise Exception(f"Error parsing event response: {e}")


def search_events(
    query: str,
    limit: int = 50,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Search for events matching a query string.
    
    Args:
        query: Search query
        limit: Maximum results to return
        cache: Optional cache instance
    
    Returns:
        List of matching PolymarketEvent objects
    """
    url = f"{GAMMA_API_BASE}/events"
    params = {
        "closed": "false",
        "limit": limit,
        "_q": query,  # Search parameter
    }
    
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error searching events: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        if isinstance(data, list):
            events = [PolymarketEvent(**event_data) for event_data in data]
        else:
            events_data = data.get("events", data.get("data", []))
            events = [PolymarketEvent(**event_data) for event_data in events_data]
        
        return events
        
    except Exception as e:
        raise Exception(f"Error parsing search response: {e}")


def get_markets(
    limit: int = 100,
    offset: int = 0,
    active: bool = True,
    cache: Optional[Any] = None,
) -> List[PolymarketMarket]:
    """
    Fetch markets directly from the Gamma API.
    
    Args:
        limit: Maximum number of markets to return
        offset: Offset for pagination
        active: Only return active markets
        cache: Optional cache instance
    
    Returns:
        List of PolymarketMarket objects
    """
    url = f"{GAMMA_API_BASE}/markets"
    params = {
        "limit": limit,
        "offset": offset,
        "active": str(active).lower(),
    }
    
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching markets: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        if isinstance(data, list):
            markets = [PolymarketMarket(**market_data) for market_data in data]
        else:
            markets_data = data.get("markets", data.get("data", []))
            markets = [PolymarketMarket(**market_data) for market_data in markets_data]
        
        return markets
        
    except Exception as e:
        raise Exception(f"Error parsing markets response: {e}")


def get_price_history(
    token_id: str,
    interval: str = "max",
    fidelity: int = 60,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    cache: Optional[Any] = None,
) -> PriceHistory:
    """
    Fetch historical price/probability data from the CLOB API.
    
    Args:
        token_id: The CLOB token ID for the market outcome
        interval: Time interval ('max', '1d', '1w', '1m', '3m', '6m', '1y')
                  Mutually exclusive with start_ts/end_ts
        fidelity: Data point frequency in minutes (1, 5, 15, 60, 1440)
        start_ts: Start Unix timestamp (optional, use instead of interval)
        end_ts: End Unix timestamp (optional, use instead of interval)
        cache: Optional cache instance
    
    Returns:
        PriceHistory object with historical probability data
    
    Example:
        >>> history = get_price_history("12345678")
        >>> print(f"Current: {history.latest_probability:.1%}")
        >>> print(f"24h change: {history.get_probability_change(24):.1%}")
        
        # With specific date range:
        >>> history = get_price_history("12345678", start_ts=1704067200, end_ts=1735689600)
    """
    cache_key = f"price_history_{token_id}_{interval}_{fidelity}_{start_ts}_{end_ts}"
    
    if cache:
        cached_data = cache.get_price_history(cache_key)
        if cached_data:
            return PriceHistory(**cached_data)
    
    url = f"{CLOB_API_BASE}/prices-history"
    params = {
        "market": token_id,
        "fidelity": fidelity,
    }
    
    # Use startTs/endTs if provided, otherwise use interval
    if start_ts is not None and end_ts is not None:
        params["startTs"] = start_ts
        params["endTs"] = end_ts
    else:
        params["interval"] = interval
    
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching price history for {token_id}: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        # Parse the history array
        history_data = data.get("history", [])
        price_points = []
        
        for point in history_data:
            if isinstance(point, dict) and "t" in point and "p" in point:
                price_points.append(PricePoint(t=point["t"], p=point["p"]))
        
        price_history = PriceHistory(
            market_id=token_id,
            token_id=token_id,
            history=price_points,
        )
        
        if cache and price_points:
            cache.set_price_history(cache_key, price_history.model_dump())
        
        return price_history
        
    except Exception as e:
        raise Exception(f"Error parsing price history response: {e}")


def get_price_history_for_event(
    event: PolymarketEvent,
    interval: str = "max",
    fidelity: int = 60,
    cache: Optional[Any] = None,
) -> Optional[PriceHistory]:
    """
    Convenience function to get price history for an event's primary market.
    
    Args:
        event: PolymarketEvent object
        interval: Time interval
        fidelity: Data point frequency in minutes
        cache: Optional cache instance
    
    Returns:
        PriceHistory or None if no token ID available
    """
    market = event.primary_market
    if not market or not market.primary_token_id:
        return None
    
    return get_price_history(
        token_id=market.primary_token_id,
        interval=interval,
        fidelity=fidelity,
        cache=cache,
    )


def detect_probability_changes(
    current: float,
    previous: float,
    threshold: float = 0.05,
) -> Optional[Dict[str, Any]]:
    """
    Detect significant probability changes.
    
    Args:
        current: Current probability (0-1)
        previous: Previous probability (0-1)
        threshold: Minimum change to flag as significant (default: 5%)
    
    Returns:
        Dict with direction and magnitude if significant, None otherwise
    
    Example:
        >>> change = detect_probability_changes(0.75, 0.65)
        >>> if change:
        ...     print(f"Probability moved {change['direction']} by {change['magnitude']:.1%}")
    """
    change = current - previous
    
    if abs(change) > threshold:
        return {
            "direction": "up" if change > 0 else "down",
            "magnitude": abs(change),
            "change": change,
            "percent_change": (change / previous * 100) if previous > 0 else 0,
        }
    
    return None


def get_events_with_probability_changes(
    events: List[PolymarketEvent],
    hours: int = 24,
    threshold: float = 0.05,
    cache: Optional[Any] = None,
) -> List[ProbabilityChange]:
    """
    Find events with significant probability changes over a time period.
    
    Args:
        events: List of events to check
        hours: Time period to check for changes
        threshold: Minimum change to flag as significant
        cache: Optional cache instance
    
    Returns:
        List of ProbabilityChange objects for events with significant changes
    """
    changes = []
    
    for event in events:
        market = event.primary_market
        if not market or not market.primary_token_id:
            continue
        
        try:
            history = get_price_history(
                token_id=market.primary_token_id,
                interval="1w",  # Get a week of data for context
                fidelity=60,
                cache=cache,
            )
            
            if not history or len(history.history) < 2:
                continue
            
            prob_change = history.get_probability_change(hours)
            
            if prob_change and abs(prob_change) > threshold:
                current_prob = history.latest_probability
                previous_prob = current_prob - prob_change
                
                change = ProbabilityChange(
                    event_id=event.id,
                    event_title=event.title,
                    market_id=market.id,
                    market_question=market.question,
                    previous_probability=previous_prob,
                    current_probability=current_prob,
                    change=prob_change,
                    change_percent=(prob_change / previous_prob * 100) if previous_prob > 0 else 0,
                    direction="up" if prob_change > 0 else "down",
                )
                changes.append(change)
                
        except Exception as e:
            # Log but continue processing other events
            print(f"Error getting price history for event {event.id}: {e}")
            continue
    
    # Sort by magnitude of change (most significant first)
    changes.sort(key=lambda c: abs(c.change), reverse=True)
    
    return changes


def get_events_by_category(
    category: str,
    limit: int = 50,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch events filtered by category/tag.
    
    Common categories include:
    - Politics
    - Crypto
    - Sports
    - Pop Culture
    - Science
    - Business
    
    Args:
        category: Category name to filter by
        limit: Maximum events to return
        cache: Optional cache instance
    
    Returns:
        List of PolymarketEvent objects in the category
    """
    return get_active_events(
        limit=limit,
        tag=category,
        cache=cache,
    )


def get_high_volume_events(
    min_volume: float = 100000,
    limit: int = 50,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch events with high trading volume.
    
    Args:
        min_volume: Minimum volume threshold
        limit: Maximum events to return
        cache: Optional cache instance
    
    Returns:
        List of high-volume PolymarketEvent objects
    """
    events = get_active_events(
        limit=limit,
        order="volume",
        ascending=False,
        cache=cache,
    )
    
    # Filter by minimum volume
    return [e for e in events if e.volume and e.volume >= min_volume]


def get_trending_events(
    limit: int = 20,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch trending events based on 24-hour volume.
    
    Args:
        limit: Maximum events to return
        cache: Optional cache instance
    
    Returns:
        List of trending PolymarketEvent objects
    """
    events = get_active_events(
        limit=limit * 2,  # Fetch more to filter
        order="volume",
        ascending=False,
        cache=cache,
    )
    
    # Sort by 24h volume and return top events
    events_with_volume = [e for e in events if e.volume_24hr]
    events_with_volume.sort(key=lambda e: e.volume_24hr or 0, reverse=True)
    
    return events_with_volume[:limit]


def get_closing_soon_events(
    days: int = 7,
    limit: int = 50,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch events closing within the specified number of days.
    
    Args:
        days: Number of days to look ahead
        limit: Maximum events to return
        cache: Optional cache instance
    
    Returns:
        List of PolymarketEvent objects closing soon
    """
    events = get_active_events(
        limit=limit * 2,
        order="endDate",
        ascending=True,
        cache=cache,
    )
    
    cutoff_date = datetime.now() + timedelta(days=days)
    closing_soon = []
    
    for event in events:
        if event.end_date:
            try:
                # Parse the end date (handle various formats)
                end_date_str = event.end_date.split("T")[0]
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                
                if end_date <= cutoff_date:
                    closing_soon.append(event)
            except (ValueError, AttributeError):
                continue
    
    return closing_soon[:limit]


# Utility functions for working with events

def extract_market_token_ids(event: PolymarketEvent) -> List[str]:
    """
    Extract all CLOB token IDs from an event's markets.
    
    Args:
        event: PolymarketEvent object
    
    Returns:
        List of token IDs
    """
    token_ids = []
    
    if event.markets:
        for market in event.markets:
            if market.clob_token_ids:
                token_ids.extend(market.clob_token_ids)
    
    return token_ids


def get_event_summary(event: PolymarketEvent) -> Dict[str, Any]:
    """
    Get a summary of an event for display or logging.
    
    Args:
        event: PolymarketEvent object
    
    Returns:
        Dict with key event information
    """
    return {
        "id": event.id,
        "title": event.title,
        "category": event.category,
        "probability": event.probability,
        "volume": event.volume,
        "volume_24hr": event.volume_24hr,
        "liquidity": event.liquidity,
        "end_date": event.end_date,
        "markets_count": len(event.markets) if event.markets else 0,
    }


# ==================== Resolved Events for Backtesting ====================


def get_resolved_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_volume: float = 100000,
    min_liquidity: float = 10000,
    categories: Optional[List[str]] = None,
    limit: int = 100,
    cache: Optional[Any] = None,
) -> List[PolymarketEvent]:
    """
    Fetch resolved (closed) events for backtesting.
    
    Uses API query params:
    - closed=true
    - volume_num_min
    - liquidity_num_min
    - end_date_min, end_date_max
    
    Returns events with known outcomes for backtest validation.
    
    Args:
        start_date: Events resolved after this date (ISO format: "2024-01-01")
        end_date: Events resolved before this date (ISO format: "2024-12-31")
        min_volume: Minimum volume in USD (default: 100000)
        min_liquidity: Minimum liquidity (default: 10000)
        categories: Filter by category list (client-side filtering)
        limit: Maximum events to return (default: 100)
        cache: Optional cache instance for storing results
    
    Returns:
        List of resolved PolymarketEvent objects with known outcomes
    
    Example:
        >>> # Get resolved events from 2024
        >>> events = get_resolved_events(
        ...     start_date="2024-01-01",
        ...     end_date="2024-12-31",
        ...     min_volume=50000
        ... )
        >>> for e in events:
        ...     outcome = get_event_outcome(e)
        ...     print(f"{e.title}: {outcome}")
    """
    # Build cache key
    cache_key = f"resolved_events_{start_date}_{end_date}_{min_volume}_{min_liquidity}_{limit}"
    if categories:
        cache_key += f"_{'_'.join(sorted(categories))}"
    
    # Check cache first
    if cache:
        cached_data = cache.get_events(cache_key)
        if cached_data:
            return [PolymarketEvent(**e) for e in cached_data]
    
    # Build request URL and params using API query parameters
    url = f"{GAMMA_API_BASE}/events"
    params: Dict[str, Any] = {
        "closed": "true",  # API field: get resolved events only
        "volume_num_min": min_volume,
        "liquidity_num_min": min_liquidity,
        "order": "volume",  # Sort by volume descending
        "ascending": "false",
        "limit": limit,
    }
    
    # Add date range filters (ISO format dates)
    if start_date:
        params["end_date_min"] = start_date
    if end_date:
        params["end_date_max"] = end_date
    
    response = _make_api_request(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching resolved events: {response.status_code} - {response.text}")
    
    try:
        data = response.json()
        
        # The API returns a list of events directly
        if isinstance(data, list):
            events = [PolymarketEvent(**event_data) for event_data in data]
        else:
            # Handle case where API returns wrapped response
            events_data = data.get("events", data.get("data", []))
            events = [PolymarketEvent(**event_data) for event_data in events_data]
        
        # Filter by categories if specified (client-side filtering)
        if categories:
            categories_lower = [c.lower() for c in categories]
            events = [
                e for e in events
                if e.category and e.category.lower() in categories_lower
            ]
        
        # Cache the results
        if cache and events:
            cache.set_events(cache_key, [e.model_dump() for e in events])
        
        return events
        
    except Exception as e:
        raise Exception(f"Error parsing resolved events response: {e}")


def get_event_outcome(event: PolymarketEvent) -> Optional[Literal["Yes", "No"]]:
    """
    Get the resolved outcome for a closed event.
    
    Determines the outcome by checking outcomePrices from the primary market.
    Resolved events have 1.0 for the winning outcome and 0.0 for the losing outcome.
    
    Args:
        event: PolymarketEvent object (should be a closed/resolved event)
    
    Returns:
        "Yes" if the Yes outcome won (price ~= 1.0)
        "No" if the No outcome won (Yes price ~= 0.0)
        None if the event is not resolved or outcome cannot be determined
    
    Example:
        >>> event = get_event_by_slug("presidential-election-winner-2024")
        >>> outcome = get_event_outcome(event)
        >>> if outcome:
        ...     print(f"Event resolved to: {outcome}")
    """
    # Check if event is closed
    if not event.closed:
        return None
    
    # Get the primary market
    market = event.primary_market
    if not market:
        return None
    
    # Check if market is closed
    if not market.closed:
        return None
    
    # Get outcome prices
    outcome_prices = market.outcome_prices
    if not outcome_prices or len(outcome_prices) < 2:
        return None
    
    try:
        # Parse the first outcome price (typically "Yes")
        yes_price = float(outcome_prices[0])
        
        # Resolved events have 1.0 for winner, 0.0 for loser
        # Use threshold to handle floating point precision
        if yes_price >= 0.99:
            return "Yes"
        elif yes_price <= 0.01:
            return "No"
        
        # Event not fully resolved yet
        return None
        
    except (ValueError, TypeError, IndexError):
        return None


def get_market_outcome(market: PolymarketMarket) -> Optional[Literal["Yes", "No"]]:
    """
    Get the resolved outcome for a closed market.
    
    Similar to get_event_outcome but works directly on a market object.
    
    Args:
        market: PolymarketMarket object
    
    Returns:
        "Yes", "No", or None if not resolved
    """
    if not market.closed:
        return None
    
    outcome_prices = market.outcome_prices
    if not outcome_prices or len(outcome_prices) < 2:
        return None
    
    try:
        yes_price = float(outcome_prices[0])
        
        if yes_price >= 0.99:
            return "Yes"
        elif yes_price <= 0.01:
            return "No"
        
        return None
        
    except (ValueError, TypeError, IndexError):
        return None


def get_resolved_events_with_outcomes(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_volume: float = 100000,
    min_liquidity: float = 10000,
    outcome_filter: Optional[Literal["Yes", "No"]] = None,
    categories: Optional[List[str]] = None,
    limit: int = 100,
    cache: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch resolved events with their outcomes for backtesting.
    
    Convenience function that combines get_resolved_events and get_event_outcome.
    
    Args:
        start_date: Events resolved after this date (ISO format)
        end_date: Events resolved before this date (ISO format)
        min_volume: Minimum volume in USD
        min_liquidity: Minimum liquidity
        outcome_filter: Filter by outcome ("Yes" or "No")
        categories: Filter by category list
        limit: Maximum events to return
        cache: Optional cache instance
    
    Returns:
        List of dicts with event data and outcome:
        [{"event": PolymarketEvent, "outcome": "Yes"|"No"|None}, ...]
    
    Example:
        >>> # Get all resolved "Yes" events from 2024
        >>> results = get_resolved_events_with_outcomes(
        ...     start_date="2024-01-01",
        ...     end_date="2024-12-31",
        ...     outcome_filter="Yes"
        ... )
        >>> for r in results:
        ...     print(f"{r['event'].title}: {r['outcome']}")
    """
    events = get_resolved_events(
        start_date=start_date,
        end_date=end_date,
        min_volume=min_volume,
        min_liquidity=min_liquidity,
        categories=categories,
        limit=limit * 2 if outcome_filter else limit,  # Fetch more if filtering
        cache=cache,
    )
    
    results = []
    for event in events:
        outcome = get_event_outcome(event)
        
        # Apply outcome filter if specified
        if outcome_filter and outcome != outcome_filter:
            continue
        
        results.append({
            "event": event,
            "outcome": outcome,
        })
        
        # Stop if we have enough results
        if len(results) >= limit:
            break
    
    return results


def get_events_active_on_date(
    as_of_date: str,
    min_volume: float = 50000,
    min_liquidity: float = 10000,
    categories: Optional[List[str]] = None,
    limit: int = 100,
    cache: Optional[Any] = None,
    verbose: bool = False,
) -> List[PolymarketEvent]:
    """
    Fetch events that were ACTIVE on a specific historical date.
    
    An event was active on a date if:
    - creationDate <= as_of_date (event existed)
    - closedTime > as_of_date OR closedTime is null (not yet resolved)
    - endDate > as_of_date (not yet expired)
    
    This is used for historical backtesting to simulate what events
    would have been available to trade on a given date.
    
    Args:
        as_of_date: The historical date to check (ISO format: "2024-01-01")
        min_volume: Minimum volume in USD (default: 50000)
        min_liquidity: Minimum liquidity (default: 10000)
        categories: Filter by category list (client-side filtering)
        limit: Maximum events to return (default: 100)
        cache: Optional cache instance for storing results
        verbose: Print detailed debug information (default: False)
    
    Returns:
        List of PolymarketEvent objects that were active on the specified date
    
    Example:
        >>> # Get events that were active on Jan 1, 2024
        >>> events = get_events_active_on_date(
        ...     as_of_date="2024-01-01",
        ...     min_volume=50000
        ... )
        >>> for e in events:
        ...     print(f"{e.title}: prob={e.probability:.1%}")
    """
    # Parse the as_of_date
    try:
        target_date = datetime.strptime(as_of_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {as_of_date}. Use YYYY-MM-DD format.")
    
    if verbose:
        print(f"\n   [DEBUG] get_events_active_on_date()")
        print(f"   [DEBUG] Target date: {as_of_date}")
        print(f"   [DEBUG] Filters: min_volume=${min_volume:,.0f}, min_liquidity=${min_liquidity:,.0f}")
    
    # Build cache key
    cache_key = f"events_active_on_{as_of_date}_{min_volume}_{min_liquidity}_{limit}"
    if categories:
        cache_key += f"_{'_'.join(sorted(categories))}"
    
    # Check cache first
    if cache:
        cached_data = cache.get_events(cache_key)
        if cached_data:
            if verbose:
                print(f"   [DEBUG] Returning {len(cached_data)} events from cache")
            return [PolymarketEvent(**e) for e in cached_data]
    
    # We need to fetch BOTH active and closed events to find those that were
    # active on the target date. An event that is now closed may have been
    # active on the historical date.
    all_events: List[PolymarketEvent] = []
    
    # Fetch active events (still open)
    url = f"{GAMMA_API_BASE}/events"
    params_active: Dict[str, Any] = {
        "closed": "false",
        "volume_num_min": min_volume,
        "liquidity_num_min": min_liquidity,
        "order": "volume",
        "ascending": "false",
        "limit": limit * 2,  # Fetch more to filter
    }
    
    response = _make_api_request(url, params=params_active)
    active_count = 0
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            active_count = len(data)
            all_events.extend([PolymarketEvent(**e) for e in data])
        else:
            events_data = data.get("events", data.get("data", []))
            active_count = len(events_data)
            all_events.extend([PolymarketEvent(**e) for e in events_data])
    
    if verbose:
        print(f"   [DEBUG] API returned {active_count} active (open) events")
    
    # Fetch closed events (may have been active on target date)
    params_closed: Dict[str, Any] = {
        "closed": "true",
        "volume_num_min": min_volume,
        "liquidity_num_min": min_liquidity,
        "order": "volume",
        "ascending": "false",
        "limit": limit * 2,
    }
    
    response = _make_api_request(url, params=params_closed)
    closed_count = 0
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list):
            closed_count = len(data)
            all_events.extend([PolymarketEvent(**e) for e in data])
        else:
            events_data = data.get("events", data.get("data", []))
            closed_count = len(events_data)
            all_events.extend([PolymarketEvent(**e) for e in events_data])
    
    if verbose:
        print(f"   [DEBUG] API returned {closed_count} closed events")
        print(f"   [DEBUG] Total events from API: {len(all_events)}")
    
    # Filter events that were active on the target date
    active_on_date: List[PolymarketEvent] = []
    
    # Debug counters for filtering
    filter_stats = {
        "total": len(all_events),
        "filtered_not_started": 0,
        "filtered_already_closed": 0,
        "filtered_already_ended": 0,
        "passed": 0,
    }
    
    # Sample events for debugging (first 3 that fail each filter)
    sample_not_started: List[Dict[str, Any]] = []
    sample_already_closed: List[Dict[str, Any]] = []
    sample_already_ended: List[Dict[str, Any]] = []
    
    for event in all_events:
        # Check if event existed on target date (startDate <= as_of_date)
        # Note: The API returns startDate which is mapped to start_date in the model
        event_start_date = event.start_date
        if event_start_date:
            try:
                # Parse start date (handle various formats)
                if "T" in event_start_date:
                    started = datetime.fromisoformat(event_start_date.replace("Z", "+00:00"))
                    started = started.replace(tzinfo=None)  # Remove timezone for comparison
                else:
                    started = datetime.strptime(event_start_date.split("T")[0], "%Y-%m-%d")
                
                if started > target_date:
                    # Event didn't exist yet on target date
                    filter_stats["filtered_not_started"] += 1
                    if len(sample_not_started) < 3:
                        sample_not_started.append({
                            "title": event.title[:50] if event.title else "Unknown",
                            "start_date": event_start_date,
                            "target_date": as_of_date,
                        })
                    continue
            except (ValueError, AttributeError):
                # If we can't parse start date, skip this check
                pass
        
        # Check if event was not yet closed on target date
        # Note: The model uses 'closed' boolean, not a timestamp. We check end_date instead.
        # If the event is marked as closed and end_date <= target_date, it was already resolved.
        if event.closed and event.end_date:
            try:
                if "T" in event.end_date:
                    closed_dt = datetime.fromisoformat(event.end_date.replace("Z", "+00:00"))
                    closed_dt = closed_dt.replace(tzinfo=None)
                else:
                    closed_dt = datetime.strptime(event.end_date.split("T")[0], "%Y-%m-%d")
                
                if closed_dt <= target_date:
                    # Event was already closed on target date
                    filter_stats["filtered_already_closed"] += 1
                    if len(sample_already_closed) < 3:
                        sample_already_closed.append({
                            "title": event.title[:50] if event.title else "Unknown",
                            "end_date": event.end_date,
                            "target_date": as_of_date,
                        })
                    continue
            except (ValueError, AttributeError):
                pass
        
        # Check if event had not yet ended on target date
        end_date = event.end_date
        if end_date:
            try:
                if "T" in end_date:
                    ended = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    ended = ended.replace(tzinfo=None)
                else:
                    ended = datetime.strptime(end_date.split("T")[0], "%Y-%m-%d")
                
                if ended <= target_date:
                    # Event had already ended on target date
                    filter_stats["filtered_already_ended"] += 1
                    if len(sample_already_ended) < 3:
                        sample_already_ended.append({
                            "title": event.title[:50] if event.title else "Unknown",
                            "end_date": end_date,
                            "target_date": as_of_date,
                        })
                    continue
            except (ValueError, AttributeError):
                pass
        
        filter_stats["passed"] += 1
        active_on_date.append(event)
    
    if verbose:
        print(f"\n   [DEBUG] Date filtering results:")
        print(f"   [DEBUG]   Total events: {filter_stats['total']}")
        print(f"   [DEBUG]   Filtered (not started yet): {filter_stats['filtered_not_started']}")
        print(f"   [DEBUG]   Filtered (already closed): {filter_stats['filtered_already_closed']}")
        print(f"   [DEBUG]   Filtered (already ended): {filter_stats['filtered_already_ended']}")
        print(f"   [DEBUG]   Passed date filters: {filter_stats['passed']}")
        
        if sample_not_started:
            print(f"\n   [DEBUG] Sample events filtered (not started yet):")
            for s in sample_not_started:
                print(f"   [DEBUG]   - '{s['title']}' started {s['start_date']} > target {s['target_date']}")
        
        if sample_already_closed:
            print(f"\n   [DEBUG] Sample events filtered (already closed):")
            for s in sample_already_closed:
                print(f"   [DEBUG]   - '{s['title']}' ended {s['end_date']} <= target {s['target_date']}")
        
        if sample_already_ended:
            print(f"\n   [DEBUG] Sample events filtered (already ended):")
            for s in sample_already_ended:
                print(f"   [DEBUG]   - '{s['title']}' ended {s['end_date']} <= target {s['target_date']}")
    
    # Remove duplicates (same event might appear in both active and closed)
    seen_ids = set()
    unique_events: List[PolymarketEvent] = []
    for event in active_on_date:
        if event.id not in seen_ids:
            seen_ids.add(event.id)
            unique_events.append(event)
    
    if verbose:
        print(f"\n   [DEBUG] After deduplication: {len(unique_events)} unique events")
    
    # Filter by categories if specified
    pre_category_count = len(unique_events)
    if categories:
        categories_lower = [c.lower() for c in categories]
        unique_events = [
            e for e in unique_events
            if e.category and e.category.lower() in categories_lower
        ]
        if verbose:
            print(f"   [DEBUG] After category filter ({categories}): {len(unique_events)} events (was {pre_category_count})")
    
    # Sort by volume (descending) and limit
    unique_events.sort(key=lambda e: e.volume or 0, reverse=True)
    result = unique_events[:limit]
    
    if verbose:
        print(f"   [DEBUG] Final result: {len(result)} events (limit={limit})")
        if result:
            print(f"\n   [DEBUG] Sample events returned:")
            for i, e in enumerate(result[:5]):
                print(f"   [DEBUG]   {i+1}. '{e.title[:50] if e.title else 'Unknown'}...'")
                print(f"   [DEBUG]      start={e.start_date}, end={e.end_date}, vol=${e.volume or 0:,.0f}")
    
    # Cache the results
    if cache and result:
        cache.set_events(cache_key, [e.model_dump() for e in result])
    
    return result
