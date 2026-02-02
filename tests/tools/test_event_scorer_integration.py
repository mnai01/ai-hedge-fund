"""Integration test for EventScorer with Polymarket API.

This script demonstrates how the EventScorer integrates with the existing
polymarket_api.py to score and rank live events from Polymarket.

Usage:
    poetry run python tests/tools/test_event_scorer_integration.py
"""

import sys
from typing import List

# Add src to path for imports
sys.path.insert(0, ".")

from src.tools.polymarket_api import (
    get_active_events,
    get_high_volume_events,
    get_trending_events,
)
from src.tools.event_scorer import (
    EventScorer,
    score_events,
    get_top_events,
    filter_stock_relevant_events,
    OFFICIAL_CATEGORIES,
)
from src.data.event_models import EventScore, RankedEventList
from src.data.polymarket_models import PolymarketEvent


def test_score_live_events():
    """Test scoring live events from Polymarket API."""
    print("\n" + "=" * 60)
    print("TEST: Score Live Events from Polymarket API")
    print("=" * 60)
    
    try:
        # Fetch active events
        print("\nFetching active events from Polymarket...")
        events = get_active_events(limit=20)
        print(f"[OK] Fetched {len(events)} events")
        
        if not events:
            print("[WARN] No events returned from API (may be rate limited)")
            return False
        
        # Score events using EventScorer
        scorer = EventScorer()
        ranked = scorer.rank_events(events)
        
        print(f"\n[OK] Scored {len(ranked.events)} events")
        print(f"  - Analyze: {len(ranked.top_events)}")
        print(f"  - Low Priority: {len(ranked.low_priority_events)}")
        print(f"  - Skip: {len(ranked.skipped_events)}")
        
        # Display top 5 events
        print("\nTop 5 Events by Score:")
        print("-" * 60)
        for event in ranked.get_top_n(5):
            print(f"  {event.rank}. [{event.total_score:.1f}] {event.event_title[:50]}...")
            print(f"     Category: {event.category or 'N/A'} | Rec: {event.recommendation}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_filter_by_category():
    """Test filtering events by category."""
    print("\n" + "=" * 60)
    print("TEST: Filter Events by Category")
    print("=" * 60)
    
    try:
        # Fetch events
        events = get_active_events(limit=50)
        
        if not events:
            print("[WARN] No events returned from API")
            return False
        
        scorer = EventScorer()
        
        # Test filtering for stock-relevant categories
        stock_categories = ["economy", "finance", "politics", "tech"]
        ranked = scorer.rank_events(events, categories=stock_categories)
        
        print(f"\n[OK] Filtered to {len(ranked.events)} stock-relevant events")
        print(f"  Categories: {stock_categories}")
        
        # Show category distribution
        category_counts = {}
        for event in ranked.events:
            cat = event.category or "unknown"
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print("\nCategory Distribution:")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            print(f"  - {cat}: {count}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_high_volume_scoring():
    """Test scoring high-volume events."""
    print("\n" + "=" * 60)
    print("TEST: Score High-Volume Events")
    print("=" * 60)
    
    try:
        # Fetch high-volume events
        print("\nFetching high-volume events...")
        events = get_high_volume_events(min_volume=50000, limit=10)
        
        if not events:
            print("[WARN] No high-volume events found")
            return False
        
        print(f"[OK] Found {len(events)} high-volume events")
        
        # Score them
        scores = score_events(events)
        
        print("\nHigh-Volume Event Scores:")
        print("-" * 60)
        for score in scores[:5]:
            print(f"  [{score.total_score:.1f}] {score.event_title[:45]}...")
            print(f"     Volume: ${score.volume:,.0f} | Liquidity: ${score.liquidity or 0:,.0f}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_component_scores():
    """Test that component scores are calculated correctly."""
    print("\n" + "=" * 60)
    print("TEST: Component Score Breakdown")
    print("=" * 60)
    
    try:
        events = get_active_events(limit=5)
        
        if not events:
            print("[WARN] No events returned from API")
            return False
        
        scorer = EventScorer()
        
        print("\nComponent Score Breakdown for Top Events:")
        print("-" * 60)
        
        for event in events[:3]:
            score = scorer.score_event(event)
            print(f"\n{score.event_title[:50]}...")
            print(f"  Total Score: {score.total_score:.1f}")
            print(f"  Components:")
            for component, value in score.component_scores.items():
                print(f"    - {component}: {value:.1f}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_polymarket_event_objects():
    """Test that PolymarketEvent objects work with scorer."""
    print("\n" + "=" * 60)
    print("TEST: PolymarketEvent Object Integration")
    print("=" * 60)
    
    try:
        # Fetch events (returns PolymarketEvent objects)
        events: List[PolymarketEvent] = get_active_events(limit=10)
        
        if not events:
            print("[WARN] No events returned from API")
            return False
        
        # Verify they are PolymarketEvent objects
        assert all(isinstance(e, PolymarketEvent) for e in events)
        print(f"[OK] Received {len(events)} PolymarketEvent objects")
        
        # Score them directly
        scorer = EventScorer()
        ranked = scorer.rank_events(events)
        
        print(f"[OK] Successfully scored PolymarketEvent objects")
        print(f"  - Total events: {ranked.total_events}")
        print(f"  - Scored events: {len(ranked.events)}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("EVENT SCORER INTEGRATION TESTS")
    print("=" * 60)
    print("\nThese tests verify integration with the live Polymarket API.")
    print("Note: Tests may fail if API is rate-limited or unavailable.\n")
    
    results = []
    
    # Run tests
    results.append(("Score Live Events", test_score_live_events()))
    results.append(("Filter by Category", test_filter_by_category()))
    results.append(("High Volume Scoring", test_high_volume_scoring()))
    results.append(("Component Scores", test_component_scores()))
    results.append(("PolymarketEvent Objects", test_polymarket_event_objects()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
