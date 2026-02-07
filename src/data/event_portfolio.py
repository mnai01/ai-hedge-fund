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

from src.data.polymarket_models import (
    PolymarketEvent,
    PriceHistory,
    ProbabilityConviction,
    OutcomeLandscape,
)


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


def get_probability_at_date(
    price_history: PriceHistory,
    target_date: str,
    max_staleness_days: int = 2,
) -> Optional[float]:
    """Get probability closest to target date.

    Scans price_history.history for the data point closest to target_date
    and returns its probability if within max_staleness_days, else None.

    Args:
        price_history: Historical probability data for the event
        target_date: Date string in YYYY-MM-DD format
        max_staleness_days: Maximum number of days between the closest
            data point and target_date before returning None

    Returns:
        Probability (0-1) at the closest data point, or None if no data
        exists within the staleness window.
    """
    if not price_history or not price_history.history:
        return None

    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return None

    target_ts = target_dt.timestamp()
    max_staleness_seconds = max_staleness_days * 86400

    closest_point = None
    closest_delta = float("inf")

    for point in price_history.history:
        delta = abs(point.timestamp - target_ts)
        if delta < closest_delta:
            closest_delta = delta
            closest_point = point

    if closest_point is None or closest_delta > max_staleness_seconds:
        return None

    return closest_point.probability


def compute_probability_conviction(
    price_history: PriceHistory,
    event: PolymarketEvent,
    analysis_date: str,
    conviction_band_tolerance: float = 0.10,
    near_expiry_days: int = 7,
) -> Optional[ProbabilityConviction]:
    """Compute a conviction score measuring how firmly the market has settled on a probability level.

    The conviction score replaces a simple probability-band check by considering
    sustained level, trend, volatility, and lifecycle position.

    Args:
        price_history: Historical probability data for the event.
        event: The Polymarket event (used for end_date / duration).
        analysis_date: Date string (YYYY-MM-DD) – no data after this is used.
        conviction_band_tolerance: ± tolerance around current prob for sustained-days count.
        near_expiry_days: Days-to-resolution threshold for near-expiry flag.

    Returns:
        ProbabilityConviction or None if insufficient data.
    """
    import math

    # 1. Get probability at the analysis date
    prob_at_date = get_probability_at_date(price_history, analysis_date)
    if prob_at_date is None:
        return None

    # 2. Filter history to points on or before analysis_date (no look-ahead)
    try:
        analysis_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    except ValueError:
        return None
    analysis_ts = analysis_dt.timestamp()
    filtered = [p for p in price_history.history if p.timestamp <= analysis_ts + 86400]
    if len(filtered) < 2:
        # Not enough data to compute conviction
        return ProbabilityConviction(
            current_probability=prob_at_date,
            distance_from_uncertainty=abs(prob_at_date - 0.5),
            conviction_score=0.0,
            sustained_days=0,
            sustained_ratio=0.0,
            trend_direction="volatile",
            trend_slope_7d=None,
            volatility_30d=0.0,
            max_drawdown=0.0,
            event_duration_days=None,
            days_remaining=None,
            near_expiry=False,
            pick_strategy="skip",
            pick_strategy_reasoning="Fewer than 3 data points available",
        )

    # Sort ascending by timestamp
    filtered.sort(key=lambda p: p.timestamp)

    # 3. Distance from uncertainty
    distance = abs(prob_at_date - 0.5)

    # 4. Event duration & days remaining
    event_duration_days: Optional[int] = None
    days_remaining: Optional[int] = None
    near_expiry = False

    event_start_dt = filtered[0].datetime
    if event.end_date:
        try:
            end_dt = datetime.strptime(event.end_date[:10], "%Y-%m-%d")
            event_duration_days = max((end_dt - event_start_dt).days, 1)
            days_remaining = (end_dt - analysis_dt).days
            near_expiry = days_remaining is not None and days_remaining <= near_expiry_days
        except (ValueError, TypeError):
            pass

    # 5. Sustained days – walk backwards from analysis date
    sustained_days = 0
    for p in reversed(filtered):
        if abs(p.probability - prob_at_date) <= conviction_band_tolerance:
            sustained_days += 1
        else:
            break

    sustained_ratio = 0.0
    if event_duration_days and event_duration_days > 0:
        sustained_ratio = sustained_days / event_duration_days

    # 6. Trend (7-day) – linear regression slope
    last_7 = filtered[-7:] if len(filtered) >= 7 else filtered
    trend_slope_7d: Optional[float] = None
    trend_direction = "stable"

    if len(last_7) >= 2:
        n = len(last_7)
        xs = list(range(n))
        ys = [p.probability for p in last_7]
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        ss_xy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
        if ss_xx > 0:
            trend_slope_7d = ss_xy / ss_xx

        # Count sign changes for volatility detection
        diffs = [ys[i + 1] - ys[i] for i in range(n - 1)]
        sign_changes = sum(
            1 for i in range(len(diffs) - 1)
            if (diffs[i] > 0 and diffs[i + 1] < 0) or (diffs[i] < 0 and diffs[i + 1] > 0)
        )

        if sign_changes >= 3:
            trend_direction = "volatile"
        elif trend_slope_7d is not None and abs(trend_slope_7d) < 0.005:
            trend_direction = "stable"
        elif trend_slope_7d is not None:
            # Determine if slope pushes prob away from or toward 0.5
            current_side = 1 if prob_at_date > 0.5 else -1
            slope_sign = 1 if trend_slope_7d > 0 else -1
            if current_side == slope_sign:
                trend_direction = "rising_certainty"
            else:
                trend_direction = "falling_certainty"

    # 7. Volatility – stdev of last 30 data points
    last_30 = filtered[-30:] if len(filtered) >= 30 else filtered
    probs_30 = [p.probability for p in last_30]
    mean_30 = sum(probs_30) / len(probs_30)
    variance_30 = sum((p - mean_30) ** 2 for p in probs_30) / len(probs_30)
    volatility_30d = math.sqrt(variance_30)

    # 8. Max drawdown – largest move back toward 0.5 after establishing distance
    max_drawdown = 0.0
    peak_distance = 0.0
    for p in filtered:
        d = abs(p.probability - 0.5)
        if d > peak_distance:
            peak_distance = d
        reversal = peak_distance - d
        if reversal > max_drawdown:
            max_drawdown = reversal

    # 9. Conviction score formula (0-100)
    distance_score = min(distance / 0.35, 1.0) * 30
    sustain_score = min(sustained_ratio / 0.20, 1.0) * 25
    stability_score = max(0.0, 1.0 - volatility_30d / 0.15) * 20

    # Trend bonus
    trend_bonus = 0.0
    if trend_direction == "rising_certainty":
        trend_bonus = 1.0
    elif trend_direction == "stable":
        trend_bonus = 0.7
    elif trend_direction == "falling_certainty":
        trend_bonus = 0.2
    else:  # volatile
        trend_bonus = 0.0
    trend_score = trend_bonus * 15

    drawdown_penalty = max(0.0, 1.0 - max_drawdown / 0.20) * 10

    conviction_score = distance_score + sustain_score + stability_score + trend_score + drawdown_penalty

    # Near-expiry discount
    if days_remaining is not None:
        if days_remaining <= 3:
            conviction_score *= 0.5
        elif days_remaining <= near_expiry_days:
            conviction_score *= 0.75

    conviction_score = round(min(conviction_score, 100.0), 1)

    # 10. Pick strategy
    if near_expiry and days_remaining is not None and days_remaining <= 3:
        pick_strategy = "skip"
        pick_strategy_reasoning = f"Near expiry ({days_remaining}d remaining) — too risky to enter"
    elif len(filtered) < 3:
        pick_strategy = "skip"
        pick_strategy_reasoning = "Fewer than 3 data points available"
    elif conviction_score >= 60 and distance >= 0.15:
        pick_strategy = "directional"
        pick_strategy_reasoning = (
            f"Market has sustained conviction (score={conviction_score}, "
            f"distance={distance:.1%}, sustained {sustained_days}d). "
            f"Favor stocks aligned with the likely outcome."
        )
    elif conviction_score < 30 or distance < 0.10:
        pick_strategy = "bi_directional"
        pick_strategy_reasoning = (
            f"Outcome uncertain (score={conviction_score}, "
            f"distance={distance:.1%}). "
            f"Favor stocks affected by the event itself, regardless of outcome."
        )
    else:
        pick_strategy = "bi_directional"
        pick_strategy_reasoning = (
            f"Moderate conviction (score={conviction_score}, "
            f"distance={distance:.1%}). "
            f"Default to bi-directional for safety."
        )

    return ProbabilityConviction(
        current_probability=prob_at_date,
        distance_from_uncertainty=distance,
        conviction_score=conviction_score,
        sustained_days=sustained_days,
        sustained_ratio=round(sustained_ratio, 4),
        trend_direction=trend_direction,
        trend_slope_7d=round(trend_slope_7d, 6) if trend_slope_7d is not None else None,
        volatility_30d=round(volatility_30d, 4),
        max_drawdown=round(max_drawdown, 4),
        event_duration_days=event_duration_days,
        days_remaining=days_remaining,
        near_expiry=near_expiry,
        pick_strategy=pick_strategy,
        pick_strategy_reasoning=pick_strategy_reasoning,
    )


def format_conviction_for_prompt(conviction: ProbabilityConviction) -> str:
    """Format conviction analysis into a text block for LLM prompt injection.

    Returns a multi-line string summarising the conviction analysis and
    recommended pick strategy (directional vs bi-directional).
    """
    prob_pct = f"{conviction.current_probability:.1%}"
    dist_pct = f"{conviction.distance_from_uncertainty:.1%}"
    score = f"{conviction.conviction_score:.0f}"
    sustained = f"{conviction.sustained_days} days"
    if conviction.event_duration_days and conviction.event_duration_days > 0:
        ratio_pct = f"{conviction.sustained_ratio:.0%}"
        sustained += f" ({ratio_pct} of event)"

    # Volatility label
    if conviction.volatility_30d < 0.05:
        vol_label = "low"
    elif conviction.volatility_30d < 0.10:
        vol_label = "moderate"
    else:
        vol_label = "high"
    vol_str = f"{conviction.volatility_30d:.2f} ({vol_label})"

    lines = [
        "CONVICTION ANALYSIS:",
        f"  Probability: {prob_pct} | Distance from 50%: {dist_pct}",
        f"  Conviction: {score}/100 | Sustained: {sustained}",
        f"  Trend: {conviction.trend_direction} | Volatility: {vol_str}",
    ]
    if conviction.days_remaining is not None:
        lines.append(f"  Days to resolution: {conviction.days_remaining}")

    # Strategy recommendation
    strategy_upper = conviction.pick_strategy.upper().replace("_", "-")
    lines.append("")
    if conviction.pick_strategy == "directional":
        lines.append(f"  STRATEGY: {strategy_upper} — Market has sustained conviction.")
        lines.append("  Favor stocks aligned with the likely outcome.")
    elif conviction.pick_strategy == "bi_directional":
        lines.append(f"  STRATEGY: {strategy_upper} — Outcome uncertain.")
        lines.append("  Favor stocks affected by the event itself, regardless of outcome.")
    else:
        lines.append(f"  STRATEGY: SKIP — {conviction.pick_strategy_reasoning}")

    return "\n".join(lines)


def format_landscape_for_prompt(landscape: OutcomeLandscape, max_outcomes: int = 10) -> str:
    """Format an OutcomeLandscape into a text block for LLM prompt injection.

    Produces a ranked table of outcomes with probabilities and 7-day changes,
    followed by an analysis section with concentration info and signal strength.

    Args:
        landscape: The OutcomeLandscape to format
        max_outcomes: Maximum outcomes to show in the table
    """
    if not landscape or not landscape.outcomes:
        return ""

    ranked = sorted(landscape.outcomes, key=lambda o: o.current_probability, reverse=True)
    shown = ranked[:max_outcomes]

    lines = [f"OUTCOME LANDSCAPE (neg-risk, {landscape.total_markets} markets):"]

    for i, o in enumerate(shown, 1):
        prob_pct = f"{o.current_probability * 100:.1f}%"
        change_str = ""
        if o.change_7d is not None:
            change_str = f"  ({o.change_7d * 100:+.1f}% 7d)"
        # Visual bar: one * per ~10%
        bar_len = max(0, int(o.current_probability * 10 + 0.5))
        bar = "*" * bar_len
        lines.append(f"   {i}. {o.outcome_label:<25s} {prob_pct:>6s}{change_str} {bar}")

    # Analysis section
    lines.append("")
    lines.append("LANDSCAPE ANALYSIS:")
    if landscape.leading_outcome:
        lines.append(f"  Leading: \"{landscape.leading_outcome}\" at {landscape.leading_probability * 100:.0f}%")
    if landscape.runner_up_outcome and landscape.dominance_gap is not None:
        lines.append(
            f"  Runner-up: \"{landscape.runner_up_outcome}\" at "
            f"{landscape.runner_up_probability * 100:.0f}% "
            f"(gap: {landscape.dominance_gap * 100:.0f}%)"
        )
    if landscape.top_2_combined and landscape.leading_outcome and landscape.runner_up_outcome:
        lines.append(
            f"  Top-2 combined: {landscape.top_2_combined * 100:.0f}% "
            f"(\"{landscape.leading_outcome}\", \"{landscape.runner_up_outcome}\")"
        )

    # Concentration interpretation
    conc = landscape.concentration or "distributed"
    if conc == "dominant":
        lines.append(
            f"  Market view: DOMINANT — \"{landscape.leading_outcome}\" leads by "
            f"{landscape.dominance_gap * 100:.0f}% over runner-up, near-certain outcome"
        )
        lines.append("  Signal strength: HIGH — dominant outcome with large gap is a strong directional signal")
    elif conc == "concentrated":
        lines.append(
            f"  Market view: CONCENTRATED — \"{landscape.leading_outcome}\" leads "
            f"but outcome not certain"
        )
    elif conc == "contested":
        lines.append(
            f"  Market view: CONTESTED — top 2 outcomes hold "
            f"{landscape.top_2_combined * 100:.0f}% but no clear winner"
        )
    else:
        lines.append("  Market view: DISTRIBUTED — no clear consensus among outcomes")

    # NO-signal section: outcomes being eliminated by the market
    if landscape.fading_outcomes:
        lines.append("")
        lines.append("FADING OUTCOMES (market says NO — probability collapsing):")
        for o in ranked:
            if o.outcome_label in landscape.fading_outcomes and o.change_7d is not None:
                lines.append(
                    f"  - \"{o.outcome_label}\" at {o.current_probability * 100:.1f}% "
                    f"({o.change_7d * 100:+.1f}% 7d) — market increasingly rules this out"
                )
        lines.append("  These NO signals are informative: eliminated outcomes free up probability")
        lines.append("  for remaining contenders and shift the expected policy/outcome regime.")

    # Probability redistribution flow
    if landscape.redistribution_summary:
        lines.append("")
        lines.append(f"PROBABILITY FLOW: {landscape.redistribution_summary}")
        lines.append("  Where probability moves FROM/TO reveals which scenario the market is pricing in.")

    return "\n".join(lines)


def print_binary_event_table(
    price_history: PriceHistory,
    event: PolymarketEvent,
    analysis_date: Optional[str] = None,
    indent: str = "      ",
) -> None:
    """Print YES/NO probability display for single-market events.

    Shows the same visual style as the multi-outcome landscape table
    but with just two rows: YES and NO with 7d change and visual bars.

    Args:
        price_history: The event's price history
        event: The PolymarketEvent
        analysis_date: Optional date string for historical lookups
        indent: Prefix for each line
    """
    if not price_history or not price_history.history:
        return

    # Get current probability (at analysis_date or latest)
    if analysis_date:
        prob = get_probability_at_date(price_history, analysis_date)
        if prob is None:
            prob = price_history.latest_probability
    else:
        prob = price_history.latest_probability

    if prob is None:
        return

    no_prob = 1.0 - prob

    # Compute 7d change
    change_7d = None
    if len(price_history.history) >= 2:
        from datetime import datetime as dt
        if analysis_date:
            try:
                analysis_ts = int(dt.strptime(analysis_date, "%Y-%m-%d").timestamp())
            except ValueError:
                analysis_ts = price_history.history[-1].timestamp
        else:
            analysis_ts = price_history.history[-1].timestamp

        ref_ts = analysis_ts - 7 * 86400
        ref_point = min(price_history.history, key=lambda p: abs(p.timestamp - ref_ts))
        cur_point = min(price_history.history, key=lambda p: abs(p.timestamp - analysis_ts))
        change_7d = cur_point.probability - ref_point.probability

    # Format YES row
    yes_pct = f"{prob * 100:5.1f}%"
    no_pct = f"{no_prob * 100:5.1f}%"

    yes_change_str = ""
    no_change_str = ""
    yes_flow = ""
    no_flow = ""
    if change_7d is not None:
        sign = "+" if change_7d >= 0 else ""
        yes_change_str = f"  ({sign}{change_7d * 100:.1f}% 7d)"
        no_sign = "+" if -change_7d >= 0 else ""
        no_change_str = f"  ({no_sign}{-change_7d * 100:.1f}% 7d)"
        # Flow labels
        if change_7d >= 0.05:
            yes_flow = "  <- gaining"
            no_flow = "  <- fading"
        elif change_7d <= -0.05:
            yes_flow = "  <- fading"
            no_flow = "  <- gaining"
        elif abs(change_7d) < 0.01:
            yes_flow = "  <- flat"
            no_flow = "  <- flat"

    # Visual bars
    yes_bar = "█" * max(0, int(prob * 20 + 0.5))
    no_bar = "█" * max(0, int(no_prob * 20 + 0.5))

    date_label = f" @ {analysis_date}" if analysis_date else ""
    print(f"{indent}│  YES: {yes_pct}{yes_change_str}  {yes_bar}{yes_flow}")
    print(f"{indent}│  NO:  {no_pct}{no_change_str}  {no_bar}{no_flow}")


def print_landscape_table(landscape: OutcomeLandscape, indent: str = "      ") -> None:
    """Print the outcome landscape to console for manual verification against Polymarket.

    Shows each outcome's YES probability, 7d change, flow label, and visual bar
    so the user can compare rates against the Polymarket website.

    Args:
        landscape: The OutcomeLandscape to display
        indent: Prefix for each line (default 6 spaces for nesting under event)
    """
    if not landscape or not landscape.outcomes:
        return

    ranked = sorted(landscape.outcomes, key=lambda o: o.current_probability, reverse=True)
    date_label = f" @ {landscape.analysis_date}" if landscape.analysis_date else ""
    conc = (landscape.concentration or "?").upper()

    print(f"{indent}┌─ Outcome Landscape ({landscape.total_markets} markets, neg-risk){date_label}")
    print(f"{indent}│  Tier: {conc}")
    for i, o in enumerate(ranked, 1):
        prob_pct = f"{o.current_probability * 100:5.1f}%"
        change_str = ""
        flow_label = ""
        if o.change_7d is not None:
            sign = "+" if o.change_7d >= 0 else ""
            change_str = f"  ({sign}{o.change_7d * 100:.1f}% 7d)"
            # Flow label based on 7d change magnitude
            if o.change_7d >= 0.05:
                flow_label = "  <- gaining"
            elif o.change_7d <= -0.05:
                flow_label = "  <- fading"
            elif abs(o.change_7d) < 0.01:
                flow_label = "  <- flat"
        # Visual bar: one block per ~5%
        bar_len = max(0, int(o.current_probability * 20 + 0.5))
        bar = "█" * bar_len
        print(f"{indent}│  {i:2d}. {o.outcome_label:<25s} {prob_pct}{change_str}  {bar}{flow_label}")

    # Flow summary
    if landscape.redistribution_summary:
        print(f"{indent}│  Flow: {landscape.redistribution_summary}")

    print(f"{indent}└─")


def compute_landscape_conviction(
    landscape: OutcomeLandscape,
    event: PolymarketEvent,
    analysis_date: str,
) -> Optional[ProbabilityConviction]:
    """Compute conviction for a multi-outcome event using the leading outcome.

    Finds the leading outcome that has price history and delegates to
    compute_probability_conviction(). Reuses all existing conviction logic.

    Args:
        landscape: The OutcomeLandscape with populated outcomes
        event: The PolymarketEvent
        analysis_date: Date string (YYYY-MM-DD)

    Returns:
        ProbabilityConviction for the leading outcome, or None if no history available.
    """
    if not landscape or not landscape.outcomes:
        return None

    # Find the leading outcome with price history
    ranked = sorted(landscape.outcomes, key=lambda o: o.current_probability, reverse=True)
    for outcome in ranked:
        if outcome.price_history and outcome.price_history.history:
            return compute_probability_conviction(
                outcome.price_history, event, analysis_date
            )

    return None


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
