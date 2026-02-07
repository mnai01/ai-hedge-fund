"""
AI-based event relevance checker for stock market impact.

This module provides a lightweight LLM-based check to determine if a Polymarket
event is likely to affect stock markets before running expensive stock discovery.

Expected to reduce discovery costs by 50-70% by filtering out sports, entertainment,
and other non-market events early in the pipeline.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from src.utils.llm import call_llm


class RelevanceResult(BaseModel):
    """Result of event relevance check."""

    relevance: Literal["high", "medium", "low"] = Field(
        description="Stock market relevance level"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the relevance assessment (0-1)"
    )

    reasoning: str = Field(
        description="Brief explanation of the relevance determination"
    )

    affected_sectors: list[str] = Field(
        default_factory=list,
        description="Potential affected stock sectors (if relevant)"
    )


class EventRelevanceChecker:
    """
    Lightweight LLM-based checker to determine if a Polymarket event
    could affect stock markets.

    Relevance Levels:
    - high: Direct impact on specific stocks/companies (e.g., "Tesla recall", "Apple earnings")
    - medium: Sector or industry-wide effects (e.g., "Fed rate decision", "Oil price shock")
    - low: Minimal or no stock market impact (e.g., "Sports game outcome", "Celebrity gossip")

    Usage:
        checker = EventRelevanceChecker(model="gemini-2.0-flash", provider="Google")
        result = checker.check_relevance(
            title="Federal Reserve Interest Rate Decision",
            description="Will the Fed raise rates in March 2025?",
            category="Economics"
        )
        if result.relevance in ["high", "medium"]:
            # Proceed with stock discovery
            pass
    """

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        provider: str = "Google",
        min_confidence: float = 0.6
    ):
        """
        Initialize the relevance checker.

        Args:
            model: LLM model to use (should be fast/cheap)
            provider: LLM provider
            min_confidence: Minimum confidence threshold for relevance determination
        """
        self.model = model
        self.provider = provider
        self.min_confidence = min_confidence

    def check_relevance(
        self,
        title: str,
        description: Optional[str] = None,
        category: Optional[str] = None
    ) -> RelevanceResult:
        """
        Check if a Polymarket event is relevant to stock markets.

        Args:
            title: Event title
            description: Optional event description
            category: Optional event category (e.g., "Politics", "Sports", "Economics")

        Returns:
            RelevanceResult with relevance level, confidence, and reasoning
        """
        # Fast-track obvious irrelevant categories
        irrelevant_categories = ["sports", "pop culture", "entertainment", "celebrity"]
        if category and category.lower() in irrelevant_categories:
            return RelevanceResult(
                relevance="low",
                confidence=0.95,
                reasoning=f"Category '{category}' typically has minimal stock market impact",
                affected_sectors=[]
            )

        # Fast-track likely relevant categories
        relevant_categories = ["economics", "business", "finance", "politics"]
        category_hint = ""
        if category and category.lower() in relevant_categories:
            category_hint = f" (Category: {category} suggests potential market relevance)"

        # Build prompt
        prompt = self._build_prompt(title, description, category)

        # Create minimal state for call_llm
        state = {
            "data": {},
            "metadata": {
                "model_name": self.model,
                "model_provider": self.provider,
            }
        }

        try:
            response = call_llm(
                prompt=prompt,
                pydantic_model=RelevanceResult,
                agent_name="event_relevance",
                state=state,
                purpose="relevance_check",
                event_id=None  # We don't have event ID yet
            )

            # Validate confidence threshold
            if response.confidence < self.min_confidence:
                # Low confidence - default to medium relevance to be safe
                response.relevance = "medium"
                response.reasoning = f"Low confidence ({response.confidence:.2f}) - defaulting to medium. Original: {response.reasoning}"

            return response

        except Exception as e:
            # On error, default to medium relevance (fail-safe: don't skip potentially valuable events)
            return RelevanceResult(
                relevance="medium",
                confidence=0.5,
                reasoning=f"Error during relevance check: {str(e)}. Defaulting to medium relevance.",
                affected_sectors=[]
            )

    def _build_prompt(
        self,
        title: str,
        description: Optional[str],
        category: Optional[str]
    ) -> str:
        """Build the LLM prompt for relevance checking."""
        prompt_parts = [
            "Analyze this prediction market event and determine its potential impact on stock markets.\n",
            f"\nTitle: {title}",
        ]

        if description:
            prompt_parts.append(f"\nDescription: {description}")

        if category:
            prompt_parts.append(f"\nCategory: {category}")

        prompt_parts.extend([
            "\n\nDetermine:",
            "1. Relevance level:",
            "   - HIGH: Direct impact on specific stocks/companies (e.g., company-specific events, major product launches, regulatory actions targeting firms)",
            "   - MEDIUM: Sector or industry-wide effects (e.g., Fed decisions, commodity prices, regulatory changes, geopolitical events)",
            "   - LOW: Minimal or no stock market impact (e.g., sports, entertainment, celebrity news, local politics)",
            "",
            "2. Your confidence in this assessment (0.0 to 1.0)",
            "",
            "3. Brief reasoning for your determination",
            "",
            "4. If relevant, list potential affected sectors (e.g., 'Technology', 'Energy', 'Financials')"
        ])

        return "\n".join(prompt_parts)

    def should_discover_stocks(self, result: RelevanceResult) -> bool:
        """
        Determine if we should proceed with stock discovery based on relevance result.

        Args:
            result: RelevanceResult from check_relevance()

        Returns:
            True if stock discovery should proceed, False otherwise
        """
        if result.relevance == "low":
            return False

        if result.relevance == "medium" and result.confidence < 0.7:
            # Medium relevance with low confidence - skip
            return False

        # High relevance or medium with good confidence - proceed
        return True


# Convenience function for quick checks
def check_event_relevance(
    title: str,
    description: Optional[str] = None,
    category: Optional[str] = None,
    model: str = "gemini-2.0-flash",
    provider: str = "Google"
) -> RelevanceResult:
    """
    Quick convenience function to check event relevance.

    Args:
        title: Event title
        description: Optional event description
        category: Optional event category
        model: LLM model to use
        provider: LLM provider

    Returns:
        RelevanceResult with relevance assessment

    Example:
        result = check_event_relevance(
            title="Apple announces new iPhone",
            category="Technology"
        )
        if result.relevance == "high":
            print(f"High relevance: {result.reasoning}")
    """
    checker = EventRelevanceChecker(model=model, provider=provider)
    return checker.check_relevance(title, description, category)
