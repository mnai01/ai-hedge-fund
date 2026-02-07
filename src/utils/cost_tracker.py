"""
LLM cost tracking system for monitoring token usage and expenses.

Tracks token usage and calculates costs across all LLM calls, providing
detailed breakdowns by agent, ticker, purpose, and model. Helps identify
cost optimization opportunities and measure ROI.

Expected to provide visibility into:
- Cost per ticker analyzed
- Cost per agent
- Most expensive operations
- Total daily/cycle costs
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal
from pydantic import BaseModel, Field


# Token pricing per 1M tokens (as of 2025)
# Update these as pricing changes
TOKEN_PRICING = {
    # Google models
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},

    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},

    # Anthropic models
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku-4": {"input": 0.80, "output": 4.00},

    # Fallback for unknown models
    "unknown": {"input": 1.00, "output": 3.00}
}


class LLMCallRecord(BaseModel):
    """Single LLM call record."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the call was made"
    )

    model: str = Field(description="LLM model used")
    provider: str = Field(description="LLM provider (Google, OpenAI, Anthropic, etc.)")

    # Token usage
    input_tokens: int = Field(description="Number of input tokens")
    output_tokens: int = Field(description="Number of output tokens")
    total_tokens: int = Field(description="Total tokens (input + output)")

    # Cost
    input_cost: float = Field(description="Cost of input tokens in USD")
    output_cost: float = Field(description="Cost of output tokens in USD")
    total_cost: float = Field(description="Total cost in USD")

    # Context
    purpose: str = Field(description="Purpose of this LLM call (e.g., 'relevance_check', 'stock_discovery', 'agent_analysis')")
    agent: Optional[str] = Field(default=None, description="Agent name if applicable")
    ticker: Optional[str] = Field(default=None, description="Ticker symbol if applicable")
    event_id: Optional[str] = Field(default=None, description="Polymarket event ID if applicable")

    # Additional metadata
    metadata: dict = Field(default_factory=dict, description="Additional call metadata")


class CostTracker:
    """
    LLM cost tracking system.

    Tracks all LLM calls and provides detailed cost analysis by:
    - Agent (which agents cost the most?)
    - Ticker (which stocks are most expensive to analyze?)
    - Purpose (which operations cost the most?)
    - Time (daily/cycle costs)

    Usage:
        tracker = CostTracker()

        # Record an LLM call
        tracker.record_call(
            model="gemini-2.0-flash",
            provider="Google",
            input_tokens=500,
            output_tokens=150,
            purpose="relevance_check",
            event_id="event-123"
        )

        # Get cost summary
        summary = tracker.get_summary()
        print(f"Total cost today: ${summary['total_cost']:.4f}")

        # Get breakdown by purpose
        by_purpose = tracker.get_breakdown_by_purpose()
        print(f"Stock discovery: ${by_purpose['stock_discovery']:.4f}")

        # Persist to disk
        tracker.save()
    """

    def __init__(self, log_file: Optional[Path] = None):
        """
        Initialize cost tracker.

        Args:
            log_file: Path to JSON log file. Defaults to data/cost_tracking.json
        """
        if log_file is None:
            log_file = Path(__file__).parent.parent.parent / "data" / "cost_tracking.json"

        self.log_file = Path(log_file)
        self._calls: list[LLMCallRecord] = []

        # Ensure directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing logs
        self._load()

    def _load(self):
        """Load cost logs from disk."""
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, "r") as f:
                data = json.load(f)

            for call_data in data:
                try:
                    call = LLMCallRecord(**call_data)
                    self._calls.append(call)
                except Exception as e:
                    print(f"Warning: Could not load cost record: {e}")

        except Exception as e:
            print(f"Warning: Could not load cost tracking from {self.log_file}: {e}")

    def save(self):
        """Persist cost logs to disk."""
        try:
            data = [call.model_dump() for call in self._calls]

            with open(self.log_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"Warning: Could not save cost tracking to {self.log_file}: {e}")

    def record_call(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str,
        agent: Optional[str] = None,
        ticker: Optional[str] = None,
        event_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> LLMCallRecord:
        """
        Record an LLM call.

        Args:
            model: LLM model used
            provider: LLM provider
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            purpose: Purpose of the call (e.g., 'relevance_check', 'stock_discovery')
            agent: Optional agent name
            ticker: Optional ticker symbol
            event_id: Optional Polymarket event ID
            metadata: Optional additional metadata

        Returns:
            LLMCallRecord with calculated costs
        """
        # Calculate cost
        total_tokens = input_tokens + output_tokens
        input_cost, output_cost, total_cost = self._calculate_cost(
            model, input_tokens, output_tokens
        )

        # Create record
        record = LLMCallRecord(
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            purpose=purpose,
            agent=agent,
            ticker=ticker,
            event_id=event_id,
            metadata=metadata or {}
        )

        self._calls.append(record)
        return record

    def _calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> tuple[float, float, float]:
        """
        Calculate cost for an LLM call.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Tuple of (input_cost, output_cost, total_cost) in USD
        """
        # Normalize model name
        model_lower = model.lower()

        # Find pricing
        pricing = None
        for model_key, model_pricing in TOKEN_PRICING.items():
            if model_key in model_lower:
                pricing = model_pricing
                break

        if pricing is None:
            pricing = TOKEN_PRICING["unknown"]

        # Calculate costs (pricing is per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        return input_cost, output_cost, total_cost

    def get_summary(self, since: Optional[datetime] = None) -> dict:
        """
        Get cost summary.

        Args:
            since: Optional datetime to filter calls since

        Returns:
            Dictionary with cost summary statistics
        """
        calls = self._calls
        if since:
            calls = [
                call for call in calls
                if datetime.fromisoformat(call.timestamp) >= since
            ]

        if not calls:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "avg_cost_per_call": 0.0
            }

        total_calls = len(calls)
        total_tokens = sum(call.total_tokens for call in calls)
        total_cost = sum(call.total_cost for call in calls)

        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "avg_cost_per_call": total_cost / total_calls if total_calls > 0 else 0.0,
            "avg_tokens_per_call": total_tokens / total_calls if total_calls > 0 else 0
        }

    def get_breakdown_by_purpose(self, since: Optional[datetime] = None) -> dict[str, float]:
        """
        Get cost breakdown by purpose.

        Args:
            since: Optional datetime to filter calls since

        Returns:
            Dictionary mapping purpose to total cost
        """
        calls = self._calls
        if since:
            calls = [
                call for call in calls
                if datetime.fromisoformat(call.timestamp) >= since
            ]

        breakdown = {}
        for call in calls:
            purpose = call.purpose
            breakdown[purpose] = breakdown.get(purpose, 0.0) + call.total_cost

        return breakdown

    def get_breakdown_by_agent(self, since: Optional[datetime] = None) -> dict[str, float]:
        """
        Get cost breakdown by agent.

        Args:
            since: Optional datetime to filter calls since

        Returns:
            Dictionary mapping agent name to total cost
        """
        calls = self._calls
        if since:
            calls = [
                call for call in calls
                if datetime.fromisoformat(call.timestamp) >= since
            ]

        breakdown = {}
        for call in calls:
            if call.agent:
                breakdown[call.agent] = breakdown.get(call.agent, 0.0) + call.total_cost

        return breakdown

    def get_breakdown_by_ticker(self, since: Optional[datetime] = None) -> dict[str, float]:
        """
        Get cost breakdown by ticker.

        Args:
            since: Optional datetime to filter calls since

        Returns:
            Dictionary mapping ticker symbol to total cost
        """
        calls = self._calls
        if since:
            calls = [
                call for call in calls
                if datetime.fromisoformat(call.timestamp) >= since
            ]

        breakdown = {}
        for call in calls:
            if call.ticker:
                breakdown[call.ticker] = breakdown.get(call.ticker, 0.0) + call.total_cost

        return breakdown

    def get_breakdown_by_model(self, since: Optional[datetime] = None) -> dict[str, float]:
        """
        Get cost breakdown by model.

        Args:
            since: Optional datetime to filter calls since

        Returns:
            Dictionary mapping model name to total cost
        """
        calls = self._calls
        if since:
            calls = [
                call for call in calls
                if datetime.fromisoformat(call.timestamp) >= since
            ]

        breakdown = {}
        for call in calls:
            breakdown[call.model] = breakdown.get(call.model, 0.0) + call.total_cost

        return breakdown

    def get_daily_costs(self, days: int = 7) -> dict[str, float]:
        """
        Get daily costs for the last N days.

        Args:
            days: Number of days to include

        Returns:
            Dictionary mapping date string to total cost
        """
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_costs = {}

        for call in self._calls:
            call_date = datetime.fromisoformat(call.timestamp).date()
            date_str = call_date.isoformat()

            if (datetime.now().date() - call_date).days < days:
                daily_costs[date_str] = daily_costs.get(date_str, 0.0) + call.total_cost

        return daily_costs

    def get_cost_by_event(self, event_id: str) -> float:
        """
        Get total cost for analyzing a specific event.

        Args:
            event_id: Polymarket event ID

        Returns:
            Total cost in USD
        """
        total = 0.0
        for call in self._calls:
            if call.event_id == event_id:
                total += call.total_cost

        return total

    def print_summary(self, since: Optional[datetime] = None):
        """
        Print a formatted cost summary.

        Args:
            since: Optional datetime to filter calls since
        """
        summary = self.get_summary(since)

        print("\n" + "="*60)
        print("LLM COST SUMMARY")
        print("="*60)
        print(f"Total Calls:       {summary['total_calls']:,}")
        print(f"Total Tokens:      {summary['total_tokens']:,}")
        print(f"Total Cost:        ${summary['total_cost']:.4f}")
        print(f"Avg Cost/Call:     ${summary['avg_cost_per_call']:.4f}")
        print(f"Avg Tokens/Call:   {summary['avg_tokens_per_call']:,.0f}")

        print("\n" + "-"*60)
        print("BREAKDOWN BY PURPOSE")
        print("-"*60)
        by_purpose = self.get_breakdown_by_purpose(since)
        for purpose, cost in sorted(by_purpose.items(), key=lambda x: x[1], reverse=True):
            print(f"{purpose:30s} ${cost:.4f}")

        print("\n" + "-"*60)
        print("BREAKDOWN BY AGENT")
        print("-"*60)
        by_agent = self.get_breakdown_by_agent(since)
        if by_agent:
            for agent, cost in sorted(by_agent.items(), key=lambda x: x[1], reverse=True):
                print(f"{agent:30s} ${cost:.4f}")
        else:
            print("(No agent-specific calls)")

        print("\n" + "-"*60)
        print("BREAKDOWN BY MODEL")
        print("-"*60)
        by_model = self.get_breakdown_by_model(since)
        for model, cost in sorted(by_model.items(), key=lambda x: x[1], reverse=True):
            print(f"{model:30s} ${cost:.4f}")

        print("="*60 + "\n")

    def clear(self):
        """Clear all cost records."""
        self._calls.clear()


# Global cost tracker instance
_global_tracker: Optional[CostTracker] = None


def get_global_tracker() -> CostTracker:
    """
    Get the global cost tracker instance.

    Returns:
        Global CostTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker


def record_llm_call(
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    purpose: str,
    agent: Optional[str] = None,
    ticker: Optional[str] = None,
    event_id: Optional[str] = None,
    metadata: Optional[dict] = None
) -> LLMCallRecord:
    """
    Convenience function to record an LLM call to the global tracker.

    Args:
        model: LLM model used
        provider: LLM provider
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        purpose: Purpose of the call
        agent: Optional agent name
        ticker: Optional ticker symbol
        event_id: Optional Polymarket event ID
        metadata: Optional additional metadata

    Returns:
        LLMCallRecord with calculated costs
    """
    tracker = get_global_tracker()
    return tracker.record_call(
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        purpose=purpose,
        agent=agent,
        ticker=ticker,
        event_id=event_id,
        metadata=metadata
    )
