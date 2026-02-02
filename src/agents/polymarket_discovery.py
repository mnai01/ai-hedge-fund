"""Polymarket Discovery Agent for Mode B (Polymarket-Driven) Trading.

This agent handles:
1. DISCOVERY MODE: Find high-conviction events and map them to stocks
2. UPDATE MODE: Update position context for existing Polymarket-linked positions

This is separate from polymarket_analyst.py which is used for Mode A/C
(traditional analysis with Polymarket as one signal among many).

Key differences from polymarket_analyst.py:
- Focuses on ticker DISCOVERY (finding new opportunities)
- Creates and updates PositionContext for thesis tracking
- Handles event lifecycle (resolution, successors)
- Designed for Mode B workflow where Polymarket drives ticker selection

Phase 2 Enhancements:
- Portfolio-aware discovery (injects portfolio context into LLM prompt)
- Event scoring with EventScorer for pre-filtering
- Event history tracking for deduplication
- Fuzzy title matching to avoid similar events

Phase 6 Enhancements:
- Financial news validation for stock picks
- LLM re-evaluation with company status assessment
- Replacement suggestions for better alternatives
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field
from typing_extensions import Literal
from rich.console import Console

if TYPE_CHECKING:
    from src.data.polymarket_models import PolymarketEvent

from src.graph.state import AgentState, show_agent_reasoning
from src.utils.llm import call_llm
from src.utils.progress import progress

# Rich console for enhanced logging
_console = Console()
from src.tools.polymarket_api import (
    get_active_events,
    get_event_by_id,
    get_price_history_for_event,
)
from src.tools.event_scorer import EventScorer, EventScore
from src.data.polymarket_models import PolymarketEvent, PriceHistory
from src.data.polymarket_cache import get_polymarket_cache, PolymarketCache
from src.data.position_context import (
    PositionContext,
    EventType,
    ThesisType,
    EventState,
    ProbabilitySnapshot,
    SequentialEventData,
    EventHistory,
    AnalyzedEvent,
    build_portfolio_context,
)
from src.utils.event_type import (
    detect_event_type,
    build_sequential_data,
    is_event_resolved,
    calculate_cumulative_probability,
)
from src.tools.api import get_company_news
from src.llm.models import get_model


# ==================== ETF Filter ====================
# ETFs don't have fundamental data (no earnings, P/E, balance sheets)
# Fundamental analysts (Buffett, Graham, etc.) cannot analyze them
# This list includes major US ETFs that might be suggested by the LLM

EXCLUDED_ETFS = {
    # Major Index ETFs
    "SPY", "QQQ", "DIA", "IWM", "IWF", "IWD", "IWB", "IWV",
    "VOO", "VTI", "VTV", "VUG", "VIG", "VYM", "VEA", "VWO",
    "IVV", "IJH", "IJR", "IVW", "IVE",
    # Sector ETFs
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE",
    "VGT", "VFH", "VHT", "VIS", "VCR", "VDC", "VAW", "VPU", "VNQ",
    # Bond ETFs
    "TLT", "TLH", "IEF", "SHY", "BND", "AGG", "LQD", "HYG", "JNK",
    "VCIT", "VCSH", "VGIT", "VGSH",
    # Commodity ETFs
    "GLD", "SLV", "IAU", "USO", "UNG", "DBA", "DBC",
    # Clean Energy / Thematic ETFs
    "ICLN", "TAN", "QCLN", "PBW", "FAN", "LIT", "ARKK", "ARKG", "ARKW", "ARKF",
    # International ETFs
    "EFA", "EEM", "IEFA", "IEMG", "VEU", "VXUS",
    # Leveraged/Inverse ETFs
    "TQQQ", "SQQQ", "SPXU", "SPXL", "UPRO", "SDS", "SSO",
    # Other common ETFs
    "XBI", "IBB", "SMH", "SOXX", "HACK", "SKYY", "CLOU",
}


def is_etf(ticker: str) -> bool:
    """Check if a ticker is an ETF (cannot be analyzed by fundamental analysts)."""
    return ticker.upper() in EXCLUDED_ETFS


# ==================== Console Logging Helpers ====================

def _safe_encode(text: str) -> str:
    """Safely encode text for Windows console (replace emojis with ASCII)."""
    # Map common emojis to ASCII equivalents
    emoji_map = {
        "\U0001f3af": "[TARGET]",  # 🎯
        "\U0001f4ca": "[CHART]",   # 📊
        "\u2705": "[OK]",          # ✅
        "\U0001f4cc": "[PIN]",     # 📌
        "\U0001f4c8": "[UP]",      # 📈
        "\U0001f4be": "[CACHE]",   # 💾
        "\U0001f389": "[DONE]",    # 🎉
        "\U0001f4cb": "[LIST]",    # 📋
        "\u26a0\ufe0f": "[!]",     # ⚠️
        "\u26a0": "[!]",           # ⚠
        "\u2714": "[v]",           # ✔
        "\u274c": "[X]",           # ❌
        "\U0001f50d": "[SEARCH]",  # 🔍
        "\U0001f4dd": "[NOTE]",    # 📝
        "\U0001f6a8": "[ALERT]",   # 🚨
    }
    for emoji, replacement in emoji_map.items():
        text = text.replace(emoji, replacement)
    # Fallback: encode with errors='replace' to handle any remaining unicode
    try:
        text.encode('cp1252')
        return text
    except UnicodeEncodeError:
        return text.encode('ascii', errors='replace').decode('ascii')


def _log_step(emoji: str, message: str, indent: int = 0) -> None:
    """Log a step in the discovery process with emoji indicator.
    
    Args:
        emoji: Emoji to prefix the message
        message: Message to display
        indent: Number of spaces to indent (for sub-steps)
    """
    prefix = "   " * indent
    safe_emoji = _safe_encode(emoji)
    safe_message = _safe_encode(message)
    _console.print(f"{prefix}{safe_emoji} {safe_message}")


def _log_stock_pick(
    ticker: str,
    direction: str,
    confidence: int,
    thesis: str = "",
    validation_result: str = "",
    indent: int = 1,
) -> None:
    """Log a stock pick with formatted details.
    
    Args:
        ticker: Stock ticker symbol
        direction: bullish or bearish
        confidence: Confidence score 0-100
        thesis: Optional thesis summary
        validation_result: Optional validation result (keep/adjust/replace/reject)
    """
    direction_indicator = "[UP]" if direction == "bullish" else "[DOWN]"
    prefix = "   " * indent
    
    # Build the main line
    main_line = f"{prefix}* {ticker} ({direction}) {direction_indicator} - Confidence: {confidence}%"
    
    # Add validation result if present
    if validation_result:
        result_indicator = {
            "keep": "[OK]",
            "adjust": "[ADJ]",
            "replace": "[REPL]",
            "reject": "[X]",
        }.get(validation_result.lower(), "")
        main_line += f" [{result_indicator} {validation_result}]"
    
    _console.print(main_line)
    
    # Print thesis on separate line if provided
    if thesis:
        _console.print(f"{prefix}  +-- {thesis[:80]}{'...' if len(thesis) > 80 else ''}")


def _log_validation_summary(
    kept: int,
    adjusted: int,
    replaced: int,
    rejected: int,
) -> None:
    """Log a summary of validation results."""
    _console.print("")
    _console.print("[CHART] [bold]Validation Summary:[/bold]")
    if kept > 0:
        _console.print(f"   [OK] Kept: {kept}")
    if adjusted > 0:
        _console.print(f"   [ADJ] Adjusted: {adjusted}")
    if replaced > 0:
        _console.print(f"   [REPL] Replaced: {replaced}")
    if rejected > 0:
        _console.print(f"   [X] Rejected: {rejected}")


# ==================== Pydantic Models for LLM Output ====================

class StockMapping(BaseModel):
    """LLM output for mapping an event to a single affected stock."""
    
    ticker: str = Field(description="US stock ticker symbol (e.g., TSLA, LMT)")
    direction: Literal["bullish", "bearish"] = Field(
        description="Expected impact direction if the event happens"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence in this stock mapping (0-100)"
    )
    thesis: str = Field(
        description="Brief thesis explaining WHY this stock is affected"
    )
    thesis_type: Literal["short_term", "long_term"] = Field(
        description="short_term = event-dependent, long_term = structural change"
    )
    reasoning: str = Field(
        description="Detailed reasoning for this analysis"
    )


class EventStockMappingResponse(BaseModel):
    """LLM response for event → stock mapping."""
    
    affected_stocks: List[StockMapping] = Field(
        default_factory=list,
        description="List of stocks directly affected by this event"
    )
    event_relevance: Literal["high", "medium", "low"] = Field(
        default="low",
        description="How relevant this event is to stock markets"
    )


# ==================== AI Stock Relevance Check ====================

class StockRelevanceResponse(BaseModel):
    """LLM response for stock market relevance assessment.
    
    Used to pre-filter events before expensive stock discovery.
    This is a quick check to determine if an event is likely to
    impact US stock prices before running full LLM stock mapping.
    """
    relevance: Literal["high", "medium", "low", "none"] = Field(
        description="How relevant is this event to US stock market movement"
    )
    reasoning: str = Field(
        description="Brief explanation of relevance assessment (1-2 sentences)"
    )
    potential_sectors: List[str] = Field(
        default_factory=list,
        description="Sectors that might be affected (e.g., 'energy', 'tech', 'financials', 'defense', 'healthcare')"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence in this assessment (0-100)"
    )


STOCK_RELEVANCE_PROMPT = """You are assessing whether a Polymarket prediction event will impact US stock prices.

EVENT DETAILS:
- Title: {event_title}
- Description: {event_description}
- Current Probability: {probability}%
- Category: {event_category}

ASSESSMENT CRITERIA:

1. **HIGH RELEVANCE** - Clear, direct impact on US stocks:
   - US economic policy (Fed rates, taxes, regulations)
   - Trade policy affecting specific industries
   - Major political outcomes affecting sectors
   - Company-specific events (earnings, leadership, M&A)
   - Industry regulations (energy, tech, healthcare, finance)
   
2. **MEDIUM RELEVANCE** - Indirect but meaningful impact:
   - Geopolitical events affecting supply chains
   - Commodity prices affecting related stocks
   - Crypto events affecting crypto-related stocks (COIN, MSTR)
   - International events with US market spillover
   
3. **LOW RELEVANCE** - Weak or speculative connection:
   - Events with unclear market implications
   - Distant geopolitical events
   - Cultural/social events with minimal business impact
   
4. **NONE** - No stock market relevance:
   - Sports outcomes (unless betting stocks)
   - Weather events (unless insurance/agriculture)
   - Entertainment/celebrity events
   - Local/regional events with no market impact

RESPOND WITH:
- relevance: "high", "medium", "low", or "none"
- reasoning: Brief explanation (1-2 sentences)
- potential_sectors: List of affected sectors (empty if none)
- confidence: 0-100 how confident you are

Examples of potential_sectors: "energy", "tech", "financials", "defense", "healthcare",
"real_estate", "consumer", "industrials", "materials", "utilities", "crypto"
"""


def assess_stock_relevance(
    event: "PolymarketEvent",
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
) -> StockRelevanceResponse:
    """
    Use LLM to assess if an event will impact US stock prices.
    
    This is a quick pre-filter before running expensive stock discovery.
    Events with "high" or "medium" relevance proceed to full stock mapping.
    Events with "low" or "none" relevance are skipped.
    
    Args:
        event: The Polymarket event to assess
        model_name: LLM model name (default: gemini-2.0-flash)
        model_provider: LLM provider (default: Google)
    
    Returns:
        StockRelevanceResponse with relevance assessment
    
    Example:
        >>> event = get_event_by_slug("presidential-election-winner-2024")
        >>> relevance = assess_stock_relevance(event)
        >>> if relevance.relevance in ["high", "medium"]:
        ...     # Proceed with stock discovery
        ...     stocks = discover_affected_stocks(event)
    """
    # Build prompt
    prob_str = f"{event.probability * 100:.1f}" if event.probability else "Unknown"
    prompt = STOCK_RELEVANCE_PROMPT.format(
        event_title=event.title or "Unknown Event",
        event_description=event.description or "No description available",
        probability=prob_str,
        event_category=event.category or "Unknown",
    )
    
    # Try structured output first, fall back to JSON parsing
    try:
        llm = get_model(model_name, model_provider)
        
        # Try with_structured_output if available
        try:
            structured_llm = llm.with_structured_output(StockRelevanceResponse)
            response = structured_llm.invoke(prompt)
            if isinstance(response, StockRelevanceResponse):
                return response
        except (NotImplementedError, AttributeError, Exception):
            # Fall back to regular call_llm with JSON parsing
            pass
        
        # Fallback: Use call_llm with Pydantic model
        state = {
            "data": {},
            "metadata": {
                "model_name": model_name,
                "model_provider": model_provider,
            }
        }
        
        response = call_llm(
            prompt=prompt,
            pydantic_model=StockRelevanceResponse,
            agent_name="stock_relevance_check",
            state=state,
        )
        
        if isinstance(response, StockRelevanceResponse):
            return response
            
    except Exception as e:
        progress.update_status("polymarket_discovery", None, f"Relevance check failed: {e}")
    
    # Default: assume low relevance if check fails
    return StockRelevanceResponse(
        relevance="low",
        reasoning="Relevance check failed, defaulting to low",
        potential_sectors=[],
        confidence=0,
    )


def batch_assess_stock_relevance(
    events: List["PolymarketEvent"],
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    min_relevance: Literal["high", "medium", "low"] = "medium",
) -> List[Tuple["PolymarketEvent", StockRelevanceResponse]]:
    """
    Assess stock relevance for multiple events and filter by minimum relevance.
    
    Args:
        events: List of events to assess
        model_name: LLM model name
        model_provider: LLM provider
        min_relevance: Minimum relevance to include ("high", "medium", or "low")
    
    Returns:
        List of (event, relevance) tuples for events meeting minimum relevance
    """
    relevance_order = {"high": 3, "medium": 2, "low": 1, "none": 0}
    min_level = relevance_order.get(min_relevance, 2)
    
    results: List[Tuple["PolymarketEvent", StockRelevanceResponse]] = []
    
    _console.print("")
    _log_step("🤖", f"[bold]AI Stock Relevance Check[/bold]")
    _log_step("📊", f"Checking {len(events)} events for US stock market relevance...", indent=1)
    
    for event in events:
        relevance = assess_stock_relevance(
            event=event,
            model_name=model_name,
            model_provider=model_provider,
        )
        
        # Log the result
        relevance_emoji = {
            "high": "✅",
            "medium": "⚠️",
            "low": "❌",
            "none": "❌",
        }.get(relevance.relevance, "❓")
        
        relevance_label = relevance.relevance.upper()
        title_preview = (event.title or "Unknown")[:50]
        if len(event.title or "") > 50:
            title_preview += "..."
        
        _log_step(relevance_emoji, f"{relevance_label}: {title_preview}", indent=1)
        
        if relevance.potential_sectors:
            sectors_str = ", ".join(relevance.potential_sectors[:5])
            _console.print(f"      └─ Sectors: {sectors_str}")
        
        # Filter by minimum relevance
        event_level = relevance_order.get(relevance.relevance, 0)
        if event_level >= min_level:
            results.append((event, relevance))
    
    _console.print("")
    _log_step("📋", f"Stock-relevant events: {len(results)}/{len(events)}", indent=1)
    
    return results


# ==================== Phase 6: Validation Models ====================

class ValidationResult(str, Enum):
    """Result of validating a stock pick against news."""
    KEEP = "keep"           # Stock still makes sense
    REPLACE = "replace"     # Suggest replacement
    ADJUST = "adjust"       # Keep but adjust confidence
    REJECT = "reject"       # Remove from picks


class CompanyStatus(str, Enum):
    """Assessment of company health based on news."""
    HEALTHY = "healthy"       # Company in good shape
    CONCERNING = "concerning" # Red flags in news
    NEUTRAL = "neutral"       # No strong signal either way


class ValidationResponse(BaseModel):
    """LLM response for stock pick validation - uses with_structured_output()."""
    
    result: Literal["keep", "adjust", "replace", "reject"] = Field(
        description="Validation decision: keep, adjust confidence, replace with better stock, or reject"
    )
    adjusted_confidence: int = Field(
        ge=0, le=100,
        description="New confidence level after considering news (0-100)"
    )
    reasoning: str = Field(
        description="Brief explanation of the validation decision (2-3 sentences)"
    )
    company_status: Literal["healthy", "concerning", "neutral"] = Field(
        default="neutral",
        description="Assessment of company health based on news"
    )
    news_event_insight: Optional[str] = Field(
        default=None,
        description="What the news tells us about the event outcome (optional)"
    )
    replacement_ticker: Optional[str] = Field(
        default=None,
        description="Alternative stock ticker (only if result is 'replace')"
    )
    replacement_direction: Optional[Literal["bullish", "bearish"]] = Field(
        default=None,
        description="Direction for replacement stock (only if replacing)"
    )
    replacement_thesis: Optional[str] = Field(
        default=None,
        description="Why this replacement stock is better (only if replacing)"
    )


class ValidatedStockMapping(BaseModel):
    """Stock mapping with validation results from news analysis."""
    
    # Original mapping fields
    ticker: str = Field(description="US stock ticker symbol")
    direction: Literal["bullish", "bearish"] = Field(
        description="Expected impact direction if the event happens"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence in this stock mapping (0-100), may be adjusted"
    )
    thesis: str = Field(description="Brief thesis explaining WHY this stock is affected")
    thesis_type: Literal["short_term", "long_term"] = Field(
        description="short_term = event-dependent, long_term = structural change"
    )
    reasoning: str = Field(description="Detailed reasoning for this analysis")
    
    # Validation fields (Phase 6)
    validation_result: ValidationResult = Field(
        default=ValidationResult.KEEP,
        description="Result of news validation"
    )
    original_confidence: int = Field(
        default=0,
        description="Pre-validation confidence level"
    )
    news_summary: Optional[str] = Field(
        default=None,
        description="Summary of key news points used for validation"
    )
    validation_reasoning: Optional[str] = Field(
        default=None,
        description="Why the stock was kept/replaced/adjusted"
    )
    company_status: CompanyStatus = Field(
        default=CompanyStatus.NEUTRAL,
        description="Assessment of company health based on news"
    )
    news_event_insight: Optional[str] = Field(
        default=None,
        description="What news tells us about the event outcome"
    )
    
    # Replacement fields (only if validation_result == REPLACE)
    replacement_ticker: Optional[str] = Field(
        default=None,
        description="Alternative stock ticker if replacing"
    )
    replacement_direction: Optional[Literal["bullish", "bearish"]] = Field(
        default=None,
        description="Direction for replacement stock"
    )
    replacement_thesis: Optional[str] = Field(
        default=None,
        description="Why this replacement stock is better"
    )
    replacement_reasoning: Optional[str] = Field(
        default=None,
        description="Detailed reasoning for replacement"
    )


# ==================== Phase 6: Validation Prompt ====================

VALIDATION_PROMPT = """You are validating a stock pick for a Polymarket event trade.

## EVENT CONTEXT
Event: {event_title}
Description: {event_description}
Current Probability: {probability}% chance of happening
Event Category: {event_category}

## STOCK PICK TO VALIDATE
Ticker: {ticker}
Direction: {direction}
Original Thesis: {thesis}
Original Confidence: {confidence}%
Thesis Type: {thesis_type}

## RECENT NEWS FOR {ticker}
{news_summary}

## YOUR TASK
Evaluate if this stock pick still makes sense by analyzing:

1. **News-Event Alignment**: Does the news give us better insight into how this event might affect the company?
   - Does news suggest the company is MORE or LESS exposed to this event?
   - Any news that directly relates to the event outcome?

2. **Company Status Check**: Is the company in good shape to trade?
   - Recent earnings: beat/miss expectations?
   - Leadership changes or scandals?
   - Major business pivots or announcements?
   - Financial health indicators?

3. **Thesis Validation**: Does the original thesis still hold?
   - Has anything changed that invalidates the reasoning?
   - Is the direction (bullish/bearish) still correct?

4. **Event Prediction Insight**: Does the news help predict the event outcome?
   - Any insider knowledge or early indicators?
   - Market positioning that suggests informed trading?

5. **Better Alternative**: Is there a more direct play on this event?
   - Another company more directly affected?
   - A company with cleaner exposure (less noise)?

IMPORTANT:
- KEEP if thesis is solid and company is healthy
- ADJUST if thesis is valid but confidence should change based on news
- REPLACE only if there's a clearly better alternative
- REJECT only if news completely invalidates the thesis

Respond with JSON:
{{
  "result": "keep" | "adjust" | "replace" | "reject",
  "adjusted_confidence": 0-100,
  "reasoning": "Brief explanation (2-3 sentences)",
  "company_status": "healthy" | "concerning" | "neutral",
  "news_event_insight": "What the news tells us about the event (1 sentence, optional)",
  "replacement_ticker": "TICKER (only if replacing)",
  "replacement_direction": "bullish" | "bearish (only if replacing)",
  "replacement_thesis": "Why this stock instead (only if replacing)"
}}
"""


# ==================== Phase 6: Validation Functions ====================

def _fetch_news_for_ticker(
    ticker: str,
    lookback_days: int = 7,
    limit: int = 10,
    as_of_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch news for a ticker, optionally as of a historical date.
    
    Args:
        ticker: Stock ticker symbol
        lookback_days: How many days back to fetch news
        limit: Maximum number of articles to return
        as_of_date: Optional date string (YYYY-MM-DD) to fetch news as of that date.
                   If None, uses current date. Used for backtesting to get historical news.
        
    Returns:
        List of news articles with title, date, and summary
    """
    if as_of_date:
        # Use the provided date for backtesting
        end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
        end_date = as_of_date
        start_date = (end_dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        # Use current date for live trading
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    try:
        news_items = get_company_news(
            ticker=ticker,
            end_date=end_date,
            start_date=start_date,
            limit=limit,
        )
        
        # Convert to simple dicts with key fields
        return [
            {
                "title": item.title,
                "date": item.date,
                "source": getattr(item, 'source', 'Unknown'),
                "summary": getattr(item, 'text', '')[:500] if hasattr(item, 'text') else '',
            }
            for item in news_items
        ]
    except Exception as e:
        progress.update_status("polymarket_discovery", None, f"News fetch failed for {ticker}: {e}")
        return []


def _format_news_summary(news_items: List[Dict[str, Any]]) -> str:
    """Format news items into a readable summary for the LLM prompt.
    
    Args:
        news_items: List of news article dicts
        
    Returns:
        Formatted string summary of news
    """
    if not news_items:
        return "No recent news available for this ticker."
    
    lines = []
    for i, item in enumerate(news_items[:5], 1):  # Limit to 5 articles
        date = item.get("date", "Unknown date")
        title = item.get("title", "No title")
        source = item.get("source", "Unknown")
        summary = item.get("summary", "")
        
        lines.append(f"{i}. [{date}] {title} ({source})")
        if summary:
            # Truncate summary to keep prompt size manageable
            lines.append(f"   {summary[:200]}...")
    
    return "\n".join(lines)


def _validate_single_stock(
    event: PolymarketEvent,
    mapping: StockMapping,
    news_items: List[Dict[str, Any]],
    model_name: str,
    model_provider: str,
) -> ValidationResponse:
    """Validate a single stock pick using LLM.
    
    Args:
        event: The Polymarket event
        mapping: The stock mapping to validate
        news_items: Recent news for the stock
        model_name: LLM model name
        model_provider: LLM provider
        
    Returns:
        ValidationResponse with validation decision
    """
    # Format news summary
    news_summary = _format_news_summary(news_items)
    
    # Build prompt
    prob_str = f"{event.probability * 100:.1f}" if event.probability else "Unknown"
    prompt = VALIDATION_PROMPT.format(
        event_title=event.title or "Unknown Event",
        event_description=event.description or "No description available",
        probability=prob_str,
        event_category=event.category or "Unknown",
        ticker=mapping.ticker,
        direction=mapping.direction,
        thesis=mapping.thesis,
        confidence=mapping.confidence,
        thesis_type=mapping.thesis_type,
        news_summary=news_summary,
    )
    
    # Try structured output first, fall back to JSON parsing
    try:
        llm = get_model(model_name, model_provider)
        
        # Try with_structured_output if available
        try:
            structured_llm = llm.with_structured_output(ValidationResponse)
            response = structured_llm.invoke(prompt)
            if isinstance(response, ValidationResponse):
                return response
        except (NotImplementedError, AttributeError, Exception):
            # Fall back to regular call_llm with JSON parsing
            pass
        
        # Fallback: Use call_llm with Pydantic model
        state = {
            "data": {},
            "metadata": {
                "model_name": model_name,
                "model_provider": model_provider,
            }
        }
        
        response = call_llm(
            prompt=prompt,
            pydantic_model=ValidationResponse,
            agent_name="polymarket_validation",
            state=state,
        )
        
        if isinstance(response, ValidationResponse):
            return response
            
    except Exception as e:
        progress.update_status("polymarket_discovery", None, f"Validation LLM failed: {e}")
    
    # Default: keep with original confidence
    return ValidationResponse(
        result="keep",
        adjusted_confidence=mapping.confidence,
        reasoning="Validation failed, keeping original pick",
        company_status="neutral",
    )


def validate_stock_picks(
    event: PolymarketEvent,
    stock_mappings: List[StockMapping],
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    max_validation_retries: int = 1,
    news_lookback_days: int = 7,
    min_news_articles: int = 3,
    as_of_date: Optional[str] = None,
) -> List[ValidatedStockMapping]:
    """Validate stock picks against recent financial news.
    
    This function fetches recent news for each stock and uses an LLM to
    re-evaluate whether the stock pick still makes sense given current
    market conditions.
    
    Args:
        event: The Polymarket event
        stock_mappings: Initial stock picks from LLM
        model_name: LLM model for validation (default: gemini-2.0-flash)
        model_provider: LLM provider (default: Google)
        max_validation_retries: Max replacement attempts per stock (default 1)
        news_lookback_days: How far back to fetch news (default 7 days)
        min_news_articles: Skip validation if fewer articles (default 3)
        as_of_date: Optional date string (YYYY-MM-DD) for historical news.
                   Used for backtesting to fetch news as of the entry date.
                   If None, uses current date (live trading mode).
        
    Returns:
        List of validated stock mappings with adjusted confidence/replacements
    """
    validated_mappings: List[ValidatedStockMapping] = []
    
    # Log validation start
    _console.print("")
    if as_of_date:
        _log_step("📰", f"[bold]Validating {len(stock_mappings)} stock picks against historical news (as of {as_of_date})...[/bold]")
    else:
        _log_step("📰", f"[bold]Validating {len(stock_mappings)} stock picks against financial news...[/bold]")
    
    for mapping in stock_mappings:
        date_suffix = f" (as of {as_of_date})" if as_of_date else ""
        _log_step("🔍", f"Fetching news for {mapping.ticker}{date_suffix}...", indent=1)
        progress.update_status(
            "polymarket_discovery", None,
            f"Validating {mapping.ticker} against news{date_suffix}..."
        )
        
        # Fetch news for this ticker (historical if as_of_date provided)
        news_items = _fetch_news_for_ticker(
            ticker=mapping.ticker,
            lookback_days=news_lookback_days,
            as_of_date=as_of_date,
        )
        
        # If not enough news, skip validation and keep original
        if len(news_items) < min_news_articles:
            _log_step("⏭️", f"Skipping {mapping.ticker}: only {len(news_items)} news articles (need {min_news_articles})", indent=1)
            progress.update_status(
                "polymarket_discovery", None,
                f"Skipping validation for {mapping.ticker}: only {len(news_items)} news articles"
            )
            validated_mappings.append(ValidatedStockMapping(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=mapping.confidence,
                thesis=mapping.thesis,
                thesis_type=mapping.thesis_type,
                reasoning=mapping.reasoning,
                validation_result=ValidationResult.KEEP,
                original_confidence=mapping.confidence,
                news_summary=f"Insufficient news ({len(news_items)} articles)",
                validation_reasoning="Skipped validation due to insufficient news",
                company_status=CompanyStatus.NEUTRAL,
            ))
            continue
        
        # Validate with LLM
        _log_step("🧠", f"Validating {mapping.ticker} with AI ({len(news_items)} articles)...", indent=1)
        validation = _validate_single_stock(
            event=event,
            mapping=mapping,
            news_items=news_items,
            model_name=model_name,
            model_provider=model_provider,
        )
        
        # Build validated mapping based on result
        news_summary = _format_news_summary(news_items)
        
        if validation.result == "reject":
            # Log rejection
            _log_stock_pick(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=0,
                thesis=validation.reasoning[:60] if validation.reasoning else "",
                validation_result="reject",
                indent=1,
            )
            # Create rejected mapping (will be filtered out later)
            validated_mappings.append(ValidatedStockMapping(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=0,  # Zero confidence for rejected
                thesis=mapping.thesis,
                thesis_type=mapping.thesis_type,
                reasoning=mapping.reasoning,
                validation_result=ValidationResult.REJECT,
                original_confidence=mapping.confidence,
                news_summary=news_summary,
                validation_reasoning=validation.reasoning,
                company_status=CompanyStatus(validation.company_status),
                news_event_insight=validation.news_event_insight,
            ))
            
        elif validation.result == "replace" and validation.replacement_ticker:
            # Log replacement suggestion
            _log_step("🔀", f"{mapping.ticker} → {validation.replacement_ticker} (replacement suggested)", indent=1)
            
            # Handle replacement with retry limit
            retries = 0
            current_replacement = validation
            
            while retries < max_validation_retries and current_replacement.result == "replace":
                replacement_ticker = current_replacement.replacement_ticker
                
                if not replacement_ticker:
                    break
                
                # Fetch news for replacement ticker (historical if as_of_date provided)
                replacement_news = _fetch_news_for_ticker(
                    ticker=replacement_ticker,
                    lookback_days=news_lookback_days,
                    as_of_date=as_of_date,
                )
                
                # Create a temporary mapping for the replacement
                replacement_mapping = StockMapping(
                    ticker=replacement_ticker,
                    direction=current_replacement.replacement_direction or mapping.direction,
                    confidence=current_replacement.adjusted_confidence,
                    thesis=current_replacement.replacement_thesis or mapping.thesis,
                    thesis_type=mapping.thesis_type,
                    reasoning=f"Replacement for {mapping.ticker}: {current_replacement.reasoning}",
                )
                
                # Validate the replacement
                if len(replacement_news) >= min_news_articles:
                    current_replacement = _validate_single_stock(
                        event=event,
                        mapping=replacement_mapping,
                        news_items=replacement_news,
                        model_name=model_name,
                        model_provider=model_provider,
                    )
                else:
                    # Not enough news for replacement, accept it
                    break
                
                retries += 1
            
            # Use the final replacement
            final_ticker = current_replacement.replacement_ticker if current_replacement.result == "replace" else (
                validation.replacement_ticker if validation.replacement_ticker else mapping.ticker
            )
            final_direction = current_replacement.replacement_direction or validation.replacement_direction or mapping.direction
            final_thesis = current_replacement.replacement_thesis or validation.replacement_thesis or mapping.thesis
            
            # Log the final replacement
            _log_stock_pick(
                ticker=final_ticker,
                direction=final_direction,
                confidence=current_replacement.adjusted_confidence,
                thesis=final_thesis[:60] if final_thesis else "",
                validation_result="replace",
                indent=1,
            )
            
            validated_mappings.append(ValidatedStockMapping(
                ticker=final_ticker,
                direction=final_direction,
                confidence=current_replacement.adjusted_confidence,
                thesis=final_thesis,
                thesis_type=mapping.thesis_type,
                reasoning=f"Replaced {mapping.ticker}: {validation.reasoning}",
                validation_result=ValidationResult.REPLACE,
                original_confidence=mapping.confidence,
                news_summary=news_summary,
                validation_reasoning=validation.reasoning,
                company_status=CompanyStatus(validation.company_status),
                news_event_insight=validation.news_event_insight,
                replacement_ticker=validation.replacement_ticker,
                replacement_direction=validation.replacement_direction,
                replacement_thesis=validation.replacement_thesis,
                replacement_reasoning=validation.reasoning,
            ))
            
        elif validation.result == "adjust":
            # Log adjustment
            confidence_change = validation.adjusted_confidence - mapping.confidence
            change_str = f"+{confidence_change}" if confidence_change > 0 else str(confidence_change)
            _log_stock_pick(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=validation.adjusted_confidence,
                thesis=f"Confidence {change_str}%: {validation.reasoning[:40] if validation.reasoning else ''}",
                validation_result="adjust",
                indent=1,
            )
            
            # Keep but adjust confidence
            validated_mappings.append(ValidatedStockMapping(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=validation.adjusted_confidence,
                thesis=mapping.thesis,
                thesis_type=mapping.thesis_type,
                reasoning=mapping.reasoning,
                validation_result=ValidationResult.ADJUST,
                original_confidence=mapping.confidence,
                news_summary=news_summary,
                validation_reasoning=validation.reasoning,
                company_status=CompanyStatus(validation.company_status),
                news_event_insight=validation.news_event_insight,
            ))
            
        else:  # "keep"
            # Log keep
            _log_stock_pick(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=validation.adjusted_confidence,
                thesis=mapping.thesis[:60] if mapping.thesis else "",
                validation_result="keep",
                indent=1,
            )
            
            # Keep with original or slightly adjusted confidence
            validated_mappings.append(ValidatedStockMapping(
                ticker=mapping.ticker,
                direction=mapping.direction,
                confidence=validation.adjusted_confidence,
                thesis=mapping.thesis,
                thesis_type=mapping.thesis_type,
                reasoning=mapping.reasoning,
                validation_result=ValidationResult.KEEP,
                original_confidence=mapping.confidence,
                news_summary=news_summary,
                validation_reasoning=validation.reasoning,
                company_status=CompanyStatus(validation.company_status),
                news_event_insight=validation.news_event_insight,
            ))
    
    # Log validation summary
    kept = sum(1 for m in validated_mappings if m.validation_result == ValidationResult.KEEP)
    adjusted = sum(1 for m in validated_mappings if m.validation_result == ValidationResult.ADJUST)
    replaced = sum(1 for m in validated_mappings if m.validation_result == ValidationResult.REPLACE)
    rejected = sum(1 for m in validated_mappings if m.validation_result == ValidationResult.REJECT)
    
    # Enhanced console logging
    _log_validation_summary(kept, adjusted, replaced, rejected)
    
    progress.update_status(
        "polymarket_discovery", None,
        f"Done - Validation: {kept} kept, {adjusted} adjusted, {replaced} replaced, {rejected} rejected"
    )
    
    return validated_mappings


# ==================== Discovery Mode Functions ====================

def discover_tickers_from_events(
    events: Optional[List[PolymarketEvent]] = None,
    portfolio_positions: Optional[Dict[str, PositionContext]] = None,
    event_history: Optional[EventHistory] = None,
    min_score: float = 50.0,
    min_probability: float = 0.60,
    max_probability: float = 0.85,
    min_confidence: int = 70,
    limit: int = 10,
    cache: Optional[PolymarketCache] = None,
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    skip_duplicates: bool = True,
    # Phase 6: News validation parameters
    validate_with_news: bool = True,
    max_validation_retries: int = 1,
    news_lookback_days: int = 7,
    min_news_articles: int = 3,
    # Phase 1 Backtesting: Date restriction to prevent future knowledge
    simulation_date: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], EventHistory]:
    """
    DISCOVERY MODE: Find high-conviction events and map them to stocks.
    
    This is the entry point for Mode B - finding NEW trading opportunities
    based on Polymarket events.
    
    Phase 2 Enhancements:
    - Uses EventScorer to pre-filter events before LLM analysis
    - Injects portfolio context into LLM prompt for better recommendations
    - Tracks analyzed events in EventHistory for deduplication
    - Skips already-analyzed events (exact ID or fuzzy title match)
    
    Phase 6 Enhancements:
    - Financial news validation for stock picks
    - LLM re-evaluation with company status assessment
    - Replacement suggestions for better alternatives
    
    Phase 1 Backtesting Enhancements:
    - simulation_date parameter to restrict LLM knowledge to that date
    - Uses price history API to get historical probability at simulation date
    - Prevents LLM from using future knowledge about event outcomes
    
    Args:
        events: Optional list of events to analyze (fetches if not provided)
        portfolio_positions: Current portfolio positions for context injection
        event_history: History of analyzed events for deduplication
        min_score: Minimum EventScorer score to analyze (default 50.0)
        min_probability: Minimum event probability (default 0.60 = 60%)
        max_probability: Maximum event probability (default 0.85 = 85%)
        min_confidence: Minimum confidence for stock mappings (0-100)
        limit: Maximum number of events to analyze
        cache: Optional cache instance (uses global if not provided)
        model_name: LLM model name for stock mapping (default: gemini-2.0-flash)
        model_provider: LLM provider (default: Google)
        skip_duplicates: Whether to skip already-analyzed events (default True)
        validate_with_news: Enable news validation for stock picks (default True)
        max_validation_retries: Max replacement attempts per stock (default 1)
        news_lookback_days: How far back to fetch news (default 7 days)
        min_news_articles: Skip validation if fewer articles (default 3)
        simulation_date: Date string (YYYY-MM-DD) for backtesting - restricts LLM
                        knowledge and uses historical probability from this date
        
    Returns:
        Tuple of (discovered_tickers, updated_event_history)
        - discovered_tickers: List of discovered ticker opportunities with context
        - updated_event_history: EventHistory with newly analyzed events
    """
    if cache is None:
        cache = get_polymarket_cache()
    
    if event_history is None:
        event_history = EventHistory()
    
    discovered = []
    scorer = EventScorer()
    
    # Get active events if not provided
    if events is None:
        events = get_active_events(
            limit=limit * 5,  # Fetch more, filter down after scoring
            order="volume",
            ascending=False,
            cache=cache,
        )
    
    # Step 1: Score events with EventScorer
    _console.print("")
    _log_step("🎯", f"[bold]Polymarket Event Discovery[/bold]")
    _log_step("📊", f"Scoring {len(events) if events else 0} events...", indent=1)
    
    scored_events = scorer.rank_events(
        events,
        min_score=min_score,
        limit=limit * 2,  # Keep more for probability filtering
    )
    
    _log_step("✅", f"Found {len(scored_events.events)} events above score threshold ({min_score})", indent=1)
    progress.update_status("polymarket_discovery", None, f"Scored {len(scored_events.events)} events (min_score={min_score})")
    
    # Step 2: Filter by probability range and deduplication
    # For backtesting, we need to get historical probability at simulation_date
    simulation_timestamp: Optional[int] = None
    if simulation_date:
        try:
            from datetime import datetime as dt
            sim_dt = dt.strptime(simulation_date, "%Y-%m-%d")
            simulation_timestamp = int(sim_dt.timestamp())
            _log_step("📅", f"Backtesting mode: Using probability as of {simulation_date}", indent=1)
        except ValueError:
            _log_step("⚠️", f"Invalid simulation_date format: {simulation_date}, using current probability", indent=1)
    
    filtered_events: List[Tuple[PolymarketEvent, EventScore, Optional[float]]] = []
    skipped_count = 0
    prob_filtered_count = 0
    
    for event_score in scored_events.events:
        # Find the original event object
        event = _find_event_by_id(events, event_score.event_id)
        if not event:
            continue
        
        # Get probability - use historical if simulation_date provided
        prob = event.probability
        historical_prob: Optional[float] = None
        
        if simulation_timestamp and event.primary_market and event.primary_market.primary_token_id:
            # Fetch historical probability at simulation date
            try:
                from src.tools.polymarket_api import get_price_history
                price_history = get_price_history(
                    token_id=event.primary_market.primary_token_id,
                    interval="max",
                    fidelity=1440,  # Daily data points
                    cache=cache,
                )
                if price_history and price_history.history:
                    historical_prob = price_history.get_probability_at(simulation_timestamp)
                    if historical_prob is not None:
                        prob = historical_prob
                        _log_step("📊", f"Historical prob at {simulation_date}: {prob:.1%} (current: {event.probability:.1%})", indent=2)
            except Exception as e:
                _log_step("⚠️", f"Could not fetch historical probability: {e}", indent=2)
        
        # Check probability range
        if prob is None or not (min_probability <= prob <= max_probability):
            prob_filtered_count += 1
            prob_str = f"{prob:.1%}" if prob is not None else "None"
            _log_step("[SKIP]", f"Prob filter: {event.title[:40]}... (prob={prob_str}, range={min_probability:.0%}-{max_probability:.0%})", indent=1)
            continue
        
        # Step 3: Deduplication check
        if skip_duplicates:
            should_skip, reason = event_history.should_skip_event(
                event_id=event.id,
                event_title=event.title or "",
            )
            if should_skip:
                progress.update_status("polymarket_discovery", None, f"Skipping: {reason}")
                skipped_count += 1
                continue
        
        # Store event, score, and historical probability (if available)
        filtered_events.append((event, event_score, historical_prob))
        
        if len(filtered_events) >= limit:
            break
    
    progress.update_status("polymarket_discovery", None, f"{len(filtered_events)} events after filtering, {skipped_count} skipped (duplicates)")
    
    # Step 4: Build portfolio context for LLM prompt
    portfolio_context = ""
    if portfolio_positions:
        portfolio_context = build_portfolio_context(portfolio_positions)
    
    # Step 5: Map each event to affected stocks using LLM
    for idx, (event, event_score, hist_prob) in enumerate(filtered_events, 1):
        # Log the event being analyzed - use historical prob if available
        display_prob = hist_prob if hist_prob is not None else event.probability
        prob_str = f"{display_prob:.1%}" if display_prob else "?"
        _console.print("")
        _log_step("📌", f"[bold]Event {idx}/{len(filtered_events)}:[/bold] {event.title[:60]}{'...' if len(event.title or '') > 60 else ''}")
        if hist_prob is not None:
            _log_step("📈", f"Probability (as of {simulation_date}): {prob_str} | Score: {event_score.total_score:.1f}", indent=1)
        else:
            _log_step("📈", f"Probability: {prob_str} | Score: {event_score.total_score:.1f}", indent=1)
        
        # Check cache first (24h TTL for stock mappings)
        # Skip cache in backtesting mode to ensure fresh LLM analysis with date restriction
        cached_mappings = None if simulation_date else _get_cached_mappings(cache, event.id)
        
        if cached_mappings:
            _log_step("💾", f"Using cached stock mappings ({len(cached_mappings)} stocks)", indent=1)
            mappings = cached_mappings
        else:
            # LLM call to map event to stocks (with portfolio context and date restriction)
            mappings = _llm_map_event_to_stocks(
                event,
                model_name,
                model_provider,
                portfolio_context=portfolio_context,
                simulation_date=simulation_date,
                historical_probability=hist_prob,
            )
            if mappings and not simulation_date:
                # Only cache in live mode, not backtesting
                _cache_mappings(cache, event.id, mappings)
        
        # Step 5b: Validate stock picks with news (Phase 6)
        if validate_with_news and mappings:
            validated_mappings = validate_stock_picks(
                event=event,
                stock_mappings=mappings,
                model_name=model_name,
                model_provider=model_provider,
                max_validation_retries=max_validation_retries,
                news_lookback_days=news_lookback_days,
                min_news_articles=min_news_articles,
                as_of_date=simulation_date,  # Use historical news for backtesting
            )
            
            # Filter out rejected mappings and convert to StockMapping for compatibility
            mappings = [
                StockMapping(
                    ticker=vm.ticker,
                    direction=vm.direction,
                    confidence=vm.confidence,
                    thesis=vm.thesis,
                    thesis_type=vm.thesis_type,
                    reasoning=vm.reasoning,
                )
                for vm in validated_mappings
                if vm.validation_result != ValidationResult.REJECT
            ]
        
        # Build context for each discovered ticker
        event_type = detect_event_type(event)
        mapped_tickers = []
        
        for mapping in mappings:
            # Filter out ETFs - fundamental analysts can't analyze them
            if is_etf(mapping.ticker):
                _log_step("⚠️", f"Skipping {mapping.ticker} (ETF - no fundamental data)", indent=1)
                continue
                
            if mapping.confidence >= min_confidence:
                context = _build_position_context(event, mapping, event_type)
                # Use historical probability if available (backtesting mode)
                prob_to_store = hist_prob if hist_prob is not None else event.probability
                discovered.append({
                    "ticker": mapping.ticker,
                    "context": context.model_dump(),
                    "event_title": event.title,
                    "probability": prob_to_store,
                    "event_score": event_score.total_score,
                    "direction": mapping.direction,  # Store direction for summary
                    "confidence": mapping.confidence,  # Store confidence for summary
                    "simulation_date": simulation_date,  # Track if this was backtesting
                })
                mapped_tickers.append(mapping.ticker)
        
        # Step 6: Track event in history
        analyzed_event = AnalyzedEvent(
            event_id=event.id,
            event_title=event.title or "",
            score=event_score.total_score,
            mapped_tickers=mapped_tickers,
            outcome="pending",
        )
        event_history.add_event(analyzed_event)
    
    # Final discovery summary
    if discovered:
        _console.print("")
        _log_step("🎉", f"[bold green]Discovery Complete![/bold green]")
        _log_step("📋", f"Found {len(discovered)} stock opportunities from {len(filtered_events)} events", indent=1)
        
        # Group by ticker for summary - use first occurrence's direction/confidence
        ticker_info: Dict[str, Dict[str, Any]] = {}
        for d in discovered:
            ticker = d["ticker"]
            if ticker not in ticker_info:
                ticker_info[ticker] = {
                    "direction": d.get("direction", "bearish"),
                    "confidence": d.get("confidence", 0),
                    "count": 1,
                }
            else:
                ticker_info[ticker]["count"] += 1
        
        _log_step("📊", "Final Stock Picks:", indent=1)
        for ticker, info in sorted(ticker_info.items()):
            _log_stock_pick(
                ticker=ticker,
                direction=info["direction"],
                confidence=info["confidence"],
                indent=2,
            )
    else:
        _console.print("")
        _log_step("⚠️", "[yellow]No stock opportunities discovered[/yellow]")
    
    return discovered, event_history


def _find_event_by_id(
    events: List[PolymarketEvent],
    event_id: str,
) -> Optional[PolymarketEvent]:
    """Find an event by ID in a list of events."""
    for event in events:
        if event.id == event_id:
            return event
    return None


def _get_cached_mappings(
    cache: PolymarketCache,
    event_id: str,
) -> Optional[List[StockMapping]]:
    """Get cached stock mappings for an event."""
    cached = cache.get_stock_mapping(event_id)
    
    if cached is None:
        return None
    
    # Cache returns list of dicts or single dict
    if isinstance(cached, dict) and "ticker" in cached:
        # Single mapping
        return [StockMapping(
            ticker=cached["ticker"],
            direction=cached["direction"],
            confidence=cached["confidence"],
            thesis=cached.get("reasoning", ""),
            thesis_type="short_term",  # Default
            reasoning=cached.get("reasoning", ""),
        )]
    elif isinstance(cached, list):
        # Multiple mappings
        mappings = []
        for item in cached:
            if isinstance(item, dict) and "ticker" in item:
                mappings.append(StockMapping(
                    ticker=item["ticker"],
                    direction=item["direction"],
                    confidence=item["confidence"],
                    thesis=item.get("reasoning", ""),
                    thesis_type="short_term",  # Default
                    reasoning=item.get("reasoning", ""),
                ))
        return mappings if mappings else None
    
    return None


def _cache_mappings(
    cache: PolymarketCache,
    event_id: str,
    mappings: List[StockMapping],
) -> None:
    """Cache stock mappings for an event using the API cache."""
    # Use the generic API cache since set_stock_mapping expects EventStockImpact
    cache_key = f"discovery_mappings_{event_id}"
    cache._set_api_cache(
        cache_key,
        [m.model_dump() for m in mappings],
        ttl_hours=24,
    )


def _llm_map_event_to_stocks(
    event: PolymarketEvent,
    model_name: str = "gemini-2.0-flash",
    model_provider: str = "Google",
    portfolio_context: str = "",
    simulation_date: Optional[str] = None,
    historical_probability: Optional[float] = None,
) -> List[StockMapping]:
    """Use LLM to identify stocks affected by an event.
    
    Phase 2 Enhancement: Now accepts portfolio_context to inject current
    portfolio positions into the prompt, helping the LLM avoid recommending
    duplicate exposure and prioritize diversification.
    
    Phase 1 Backtesting Enhancement: Adds simulation_date parameter to restrict
    LLM knowledge to that date, preventing future knowledge leakage.
    
    Args:
        event: The Polymarket event to analyze
        model_name: LLM model name (default: gemini-2.0-flash)
        model_provider: LLM provider (default: Google)
        portfolio_context: Optional portfolio context string for prompt injection
        simulation_date: Date string (YYYY-MM-DD) for backtesting - restricts LLM knowledge
        historical_probability: Historical probability at simulation_date (if available)
    """
    
    # Build the base prompt
    # Use historical probability if provided (backtesting mode)
    prob = historical_probability if historical_probability is not None else event.probability
    prob_str = f"{prob:.1%}" if prob is not None else "Unknown"
    
    # Detect if this is a resolved event (prob is 0% or 100%)
    is_resolved = prob is not None and (prob >= 0.99 or prob <= 0.01)
    
    # Build date restriction section for backtesting
    date_restriction = ""
    if simulation_date:
        date_restriction = f"""
⚠️ CRITICAL BACKTESTING CONSTRAINT ⚠️
You are analyzing this event AS IF today's date is {simulation_date}.
You MUST NOT use any knowledge of events, news, or outcomes that occurred AFTER {simulation_date}.
Pretend you do not know what happened after this date.
Base your analysis ONLY on information that would have been available on {simulation_date}.

"""
    
    if is_resolved and not simulation_date:
        # Only use "resolved" framing if NOT in backtesting mode
        base_prompt = f"""Analyze this Polymarket prediction market event and identify US stocks
that would be DIRECTLY affected by this event outcome.

NOTE: This is a HISTORICAL ANALYSIS. The event has already resolved.
We want to identify stocks that WERE affected by this event for backtesting purposes.

Event: {event.title}
Description: {event.description or 'No description available'}
Event Status: RESOLVED (outcome: {'YES' if prob >= 0.99 else 'NO'})
"""
    else:
        # Standard prompt - event is active (or we're backtesting)
        base_prompt = f"""{date_restriction}Analyze this Polymarket prediction market event and identify US stocks
that would be DIRECTLY affected if this event occurs.

Event: {event.title}
Description: {event.description or 'No description available'}
Current Probability: {prob_str} chance of happening
"""
        if simulation_date:
            base_prompt += f"Analysis Date: {simulation_date}\n"

    # Inject portfolio context if provided
    if portfolio_context:
        portfolio_section = f"""
{portfolio_context}

IMPORTANT: Avoid recommending stocks that would create duplicate exposure
to the same event or highly correlated positions. Prioritize NEW stocks
not already in the portfolio for better diversification.
"""
    else:
        portfolio_section = ""
    
    # Build the instruction section
    instruction_section = """
For each affected stock, provide:
- ticker: US stock ticker symbol
- direction: "bullish" or "bearish" if the event happens
- confidence: 0-100 how confident you are in this mapping
- thesis: Brief explanation of WHY this stock is affected (1-2 sentences)
- thesis_type: "short_term" (immediate reaction, fades after event) or "long_term" (sustained structural impact)
- reasoning: Detailed reasoning for your analysis

IMPORTANT:
- Only include stocks with CLEAR, DIRECT relationships to the event
- Do NOT include speculative or weak connections
- Focus on companies that would see material business impact
- If no stocks are clearly affected, return an empty list
"""
    
    # Add backtesting reminder at the end
    if simulation_date:
        instruction_section += f"""
REMINDER: Your analysis must be based ONLY on information available as of {simulation_date}.
Do NOT reference any events, outcomes, or news from after this date.
"""
    
    # Combine all sections
    prompt = base_prompt + portfolio_section + instruction_section
    
    # Create minimal state for call_llm
    state = {
        "data": {},
        "metadata": {
            "model_name": model_name,
            "model_provider": model_provider,
        }
    }
    
    # Log the AI discovery step
    _log_step("🤖", f"Discovering affected stocks with AI ({model_name})...")
    
    try:
        response = call_llm(
            prompt=prompt,
            pydantic_model=EventStockMappingResponse,
            agent_name="polymarket_discovery",
            state=state,
        )
        
        if response and hasattr(response, 'affected_stocks'):
            stocks = response.affected_stocks
            
            # Log AI-identified stocks
            if stocks:
                _log_step("✅", f"AI-Identified Affected Stocks ({len(stocks)}):")
                for stock in stocks:
                    _log_stock_pick(
                        ticker=stock.ticker,
                        direction=stock.direction,
                        confidence=stock.confidence,
                        thesis=stock.thesis,
                    )
            else:
                _log_step("⚠️", "No stocks identified for this event")
            
            return stocks
    except Exception as e:
        _log_step("❌", f"LLM mapping failed: {e}")
        progress.update_status("polymarket_discovery", None, f"LLM mapping failed: {e}")
    
    return []


def _build_position_context(
    event: PolymarketEvent,
    mapping: StockMapping,
    event_type: EventType,
) -> PositionContext:
    """Build PositionContext from event and stock mapping."""
    
    # Build probability snapshot
    prob_snapshot = ProbabilitySnapshot(
        current=event.probability or 0.0,
        change_24h=None,  # Will be populated on update
        change_7d=None,
        since_entry=None,
        at_entry=event.probability,
    )
    
    # Build sequential data if applicable
    sequential_data = None
    if event_type == EventType.SEQUENTIAL:
        sequential_data = build_sequential_data(event)
    
    return PositionContext(
        event_id=event.id,
        event_title=event.title or "Unknown Event",
        event_type=event_type,
        event_state=EventState.ACTIVE,
        thesis=mapping.thesis,
        thesis_type=ThesisType(mapping.thesis_type),
        ticker=mapping.ticker,
        impact_direction=mapping.direction,
        confidence=mapping.confidence,
        probability=prob_snapshot,
        entry_date=datetime.now().strftime("%Y-%m-%d"),
        entry_price=None,  # Set when position is opened
        sequential_data=sequential_data,
    )


# ==================== Update Mode Functions ====================

def update_position_contexts(
    existing_context: Dict[str, Dict],
    current_date: Optional[str] = None,
    cache: Optional[PolymarketCache] = None,
) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    UPDATE MODE: Update context for existing Polymarket-linked positions.
    
    This is called on each run to:
    1. Fetch current event state
    2. Update probability snapshots
    3. Detect event resolution
    4. Handle sequential event progression
    
    Args:
        existing_context: Current position_context dict (ticker -> context)
        current_date: Current date for backtesting (YYYY-MM-DD)
        cache: Optional cache instance (uses global if not provided)
        
    Returns:
        Tuple of (updated_context, event_status_changes)
        - updated_context: Updated position contexts
        - event_status_changes: Dict of ticker -> new status if changed
    """
    if cache is None:
        cache = get_polymarket_cache()
    
    updated = {}
    status_changes = {}
    
    for ticker, context in existing_context.items():
        # Skip non-Polymarket positions
        if context.get("source") == "user_selected":
            updated[ticker] = context
            continue
        
        event_id = context.get("event_id")
        if not event_id:
            updated[ticker] = context
            continue
        
        # Fetch current event state
        event = get_event_by_id(event_id, cache=cache)
        if not event:
            # Event not found - mark as expired
            context["event_state"] = EventState.EXPIRED.value
            updated[ticker] = context
            status_changes[ticker] = "expired"
            continue
        
        # Update probability snapshot
        old_prob = context.get("probability", {}).get("current", 0)
        new_prob = event.probability or 0
        
        context["probability"] = {
            "current": new_prob,
            "change_24h": _calculate_change(event, hours=24, cache=cache),
            "change_7d": _calculate_change(event, hours=168, cache=cache),
            "since_entry": new_prob - context.get("probability", {}).get("at_entry", new_prob),
            "at_entry": context.get("probability", {}).get("at_entry", new_prob),
        }
        
        # Check for event resolution
        is_resolved, outcome = is_event_resolved(event)
        if is_resolved:
            old_state = context.get("event_state")
            if outcome == "yes":
                context["event_state"] = EventState.RESOLVED_YES.value
            elif outcome == "no":
                context["event_state"] = EventState.RESOLVED_NO.value
            else:
                context["event_state"] = EventState.EXPIRED.value
            
            if old_state != context["event_state"]:
                status_changes[ticker] = context["event_state"]
        
        # Handle sequential events
        if context.get("event_type") == EventType.SEQUENTIAL.value:
            sequential_data = build_sequential_data(event)
            if sequential_data:
                context["sequential_data"] = sequential_data.model_dump()
                context["probability"]["cumulative"] = sequential_data.cumulative_probability
        
        context["last_updated"] = datetime.now().isoformat()
        updated[ticker] = context
    
    return updated, status_changes


def _calculate_change(
    event: PolymarketEvent,
    hours: int,
    cache: Optional[PolymarketCache] = None,
) -> Optional[float]:
    """Calculate probability change over specified hours."""
    try:
        history = get_price_history_for_event(event, cache=cache)
        if history:
            return history.get_probability_change(hours=hours)
    except Exception:
        pass
    return None


# ==================== Main Agent Function ====================

def polymarket_discovery_agent(
    state: AgentState,
    agent_id: str = "polymarket_discovery_agent",
) -> Dict[str, Any]:
    """
    Polymarket Discovery Agent - Discovery and Update modes.
    
    This agent is used in Mode B (Polymarket-Driven) workflow:
    1. DISCOVERY: Find new tickers from high-conviction events
    2. UPDATE: Update context for existing Polymarket-linked positions
    
    Unlike polymarket_analyst_agent which generates signals for given tickers,
    this agent DISCOVERS tickers and manages their lifecycle.
    
    Phase 2 Enhancements:
    - Portfolio-aware discovery (injects portfolio context into LLM prompt)
    - Event scoring with EventScorer for pre-filtering
    - Event history tracking for deduplication
    - Fuzzy title matching to avoid similar events
    
    Args:
        state: Current agent state
        agent_id: Agent identifier
        
    Returns:
        Dict with:
        - discovered_tickers: New tickers found (list of {ticker, context})
        - updated_context: Updated position_context for existing positions
        - status_changes: Event status changes (resolution, expiry)
        - event_history: Updated EventHistory for persistence
    """
    data = state.get("data", {})
    metadata = state.get("metadata", {})
    
    show_reasoning = metadata.get("show_reasoning", False)
    run_discovery = metadata.get("polymarket_discovery", False)
    
    existing_context = data.get("position_context", {})
    
    # Load or create event history for deduplication
    event_history_data = data.get("event_history", {})
    if event_history_data:
        event_history = EventHistory(**event_history_data)
    else:
        event_history = EventHistory()
    
    result = {
        "discovered_tickers": [],
        "updated_context": {},
        "status_changes": {},
        "event_history": {},
    }
    
    cache = get_polymarket_cache()
    
    # Get model config from state (use selected LLM)
    model_name = metadata.get("model_name", "gemini-2.0-flash")
    model_provider = metadata.get("model_provider", "Google")
    
    # Convert existing_context to PositionContext objects for portfolio awareness
    portfolio_positions: Dict[str, PositionContext] = {}
    for ticker, ctx_data in existing_context.items():
        if isinstance(ctx_data, dict):
            try:
                portfolio_positions[ticker] = PositionContext(**ctx_data)
            except Exception:
                # Skip invalid context data
                pass
    
    # MODE 1: DISCOVERY (if enabled)
    if run_discovery:
        progress.update_status("polymarket_discovery", None, "Discovering tickers from events")
        
        # Use the new portfolio-aware discovery function
        discovered, updated_history = discover_tickers_from_events(
            events=None,  # Will fetch events
            portfolio_positions=portfolio_positions if portfolio_positions else None,
            event_history=event_history,
            min_score=metadata.get("min_score", 50.0),
            min_probability=metadata.get("min_probability", 0.60),
            max_probability=metadata.get("max_probability", 0.85),
            min_confidence=metadata.get("min_confidence", 70),
            limit=metadata.get("discovery_limit", 10),
            cache=cache,
            model_name=model_name,
            model_provider=model_provider,
            skip_duplicates=metadata.get("skip_duplicates", True),
        )
        
        # Update event history
        event_history = updated_history
        
        # Filter out already-tracked tickers
        new_discoveries = [
            d for d in discovered
            if d["ticker"] not in existing_context
        ]
        
        result["discovered_tickers"] = new_discoveries
        result["event_history"] = event_history.model_dump()
        
        if show_reasoning:
            history_summary = event_history.get_summary()
            progress.update_status("polymarket_discovery", None, f"Discovered {len(new_discoveries)} new tickers, {history_summary['total_events']} events tracked")
    
    # MODE 2: UPDATE (always runs if there's existing context)
    if existing_context:
        progress.update_status("polymarket_discovery", None, "Updating position contexts")
        
        current_date = data.get("end_date")  # For backtesting
        updated, status_changes = update_position_contexts(
            existing_context,
            current_date=current_date,
            cache=cache,
        )
        
        result["updated_context"] = updated
        result["status_changes"] = status_changes
        
        if show_reasoning and status_changes:
            progress.update_status("polymarket_discovery", None, f"Status changes: {status_changes}")
    
    if show_reasoning:
        show_agent_reasoning(result, agent_id)
    
    return {
        "messages": [],
        "data": {
            "polymarket_discovery": result,
        },
    }
