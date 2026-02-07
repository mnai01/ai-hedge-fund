import json
import time
import logging
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from typing import Dict

from src.graph.state import AgentState, show_agent_reasoning
from pydantic import BaseModel, Field
from typing_extensions import Literal
from src.utils.progress import progress
from src.utils.llm import call_llm

logger = logging.getLogger(__name__)


class PortfolioDecision(BaseModel):
    action: Literal["buy", "sell", "short", "cover", "hold"]
    quantity: int = Field(description="Number of shares to trade")
    confidence: int = Field(description="Confidence 0-100")
    reasoning: str = Field(description="Reasoning for the decision")


class PortfolioManagerOutput(BaseModel):
    """Portfolio manager output with trading decisions per ticker.
    
    Note: Gemini requires dict schemas to have at least one example property.
    We use default_factory to ensure the dict is never empty in the schema.
    """
    decisions: Dict[str, PortfolioDecision] = Field(
        default_factory=dict,
        description="Dictionary of ticker to trading decisions",
        json_schema_extra={
            "example": {
                "AAPL": {
                    "action": "hold",
                    "quantity": 0,
                    "confidence": 50,
                    "reasoning": "Neutral outlook"
                }
            }
        }
    )


##### Portfolio Management Agent #####
def portfolio_management_agent(state: AgentState, agent_id: str = "portfolio_manager"):
    """Makes final trading decisions and generates orders for multiple tickers"""

    portfolio = state["data"]["portfolio"]
    analyst_signals = state["data"]["analyst_signals"]
    tickers = state["data"]["tickers"]
    position_context = state["data"].get("position_context", {})

    position_limits = {}
    current_prices = {}
    max_shares = {}
    signals_by_ticker = {}
    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Processing analyst signals")

        # Find the corresponding risk manager for this portfolio manager
        if agent_id.startswith("portfolio_manager_"):
            suffix = agent_id.split('_')[-1]
            risk_manager_id = f"risk_management_agent_{suffix}"
        else:
            risk_manager_id = "risk_management_agent"  # Fallback for CLI

        risk_data = analyst_signals.get(risk_manager_id, {}).get(ticker, {})
        position_limits[ticker] = risk_data.get("remaining_position_limit", 0.0)
        current_prices[ticker] = float(risk_data.get("current_price", 0.0))

        # Calculate maximum shares allowed based on position limit and price
        if current_prices[ticker] > 0:
            max_shares[ticker] = int(position_limits[ticker] // current_prices[ticker])
        else:
            max_shares[ticker] = 0

        # Compress analyst signals to {sig, conf}
        ticker_signals = {}
        for agent, signals in analyst_signals.items():
            if not agent.startswith("risk_management_agent") and ticker in signals:
                sig = signals[ticker].get("signal")
                conf = signals[ticker].get("confidence")
                if sig is not None and conf is not None:
                    ticker_signals[agent] = {"sig": sig, "conf": conf}
        signals_by_ticker[ticker] = ticker_signals

    state["data"]["current_prices"] = current_prices

    progress.update_status(agent_id, None, "Generating trading decisions")

    # Get long_only flag from metadata (set by --no-short CLI flag)
    long_only = state["metadata"].get("long_only", False)

    result = generate_trading_decision(
        tickers=tickers,
        signals_by_ticker=signals_by_ticker,
        current_prices=current_prices,
        max_shares=max_shares,
        portfolio=portfolio,
        agent_id=agent_id,
        state=state,
        long_only=long_only,
        position_context=position_context,
    )
    message = HumanMessage(
        content=json.dumps({ticker: decision.model_dump() for ticker, decision in result.decisions.items()}),
        name=agent_id,
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning({ticker: decision.model_dump() for ticker, decision in result.decisions.items()},
                             "Portfolio Manager")

    # Create a brief summary of all decisions for display
    decision_summaries = []
    for ticker, decision in result.decisions.items():
        action = decision.action.upper()
        qty = decision.quantity
        price = current_prices.get(ticker, 0)
        if action != "HOLD" and qty > 0:
            decision_summaries.append(f"{action} {qty} {ticker} @${price:.2f}")
        elif action == "HOLD":
            decision_summaries.append(f"HOLD {ticker}")
    
    summary = ", ".join(decision_summaries[:3])  # Show first 3 decisions
    if len(decision_summaries) > 3:
        summary += f" +{len(decision_summaries) - 3} more"

    progress.update_status(agent_id, None, "Done", analysis=summary)

    return {
        "messages": state["messages"] + [message],
        "data": state["data"],
    }


def compute_allowed_actions(
        tickers: list[str],
        current_prices: dict[str, float],
        max_shares: dict[str, int],
        portfolio: dict[str, float],
        long_only: bool = False,
) -> dict[str, dict[str, int]]:
    """Compute allowed actions and max quantities for each ticker deterministically.
    
    This function determines what trading actions are available for each ticker
    based on current positions, cash, margin, and risk limits.
    
    Args:
        tickers: List of ticker symbols to compute actions for
        current_prices: Dict mapping ticker to current price
        max_shares: Dict mapping ticker to max shares allowed by risk manager
        portfolio: Portfolio dict with cash, positions, margin info
        long_only: If True, disable short selling entirely (--no-short flag)
    
    Debug logging is included to help diagnose "always HOLD" issues.
    """
    allowed = {}
    cash = float(portfolio.get("cash", 0.0))
    positions = portfolio.get("positions", {}) or {}
    margin_requirement = float(portfolio.get("margin_requirement", 0.5))
    margin_used = float(portfolio.get("margin_used", 0.0))
    equity = float(portfolio.get("equity", cash))

    # Log portfolio state for debugging
    logger.debug(f"[compute_allowed_actions] Portfolio state: cash={cash:.2f}, "
                 f"margin_req={margin_requirement:.2f}, margin_used={margin_used:.2f}, equity={equity:.2f}, "
                 f"long_only={long_only}")

    for ticker in tickers:
        price = float(current_prices.get(ticker, 0.0))
        pos = positions.get(
            ticker,
            {"long": 0, "long_cost_basis": 0.0, "short": 0, "short_cost_basis": 0.0},
        )
        long_shares = int(pos.get("long", 0) or 0)
        short_shares = int(pos.get("short", 0) or 0)
        max_qty = int(max_shares.get(ticker, 0) or 0)

        # Start with zeros
        actions = {"buy": 0, "sell": 0, "short": 0, "cover": 0, "hold": 0}

        # Long side
        if long_shares > 0:
            actions["sell"] = long_shares
        if cash > 0 and price > 0:
            max_buy_cash = int(cash // price)
            max_buy = max(0, min(max_qty, max_buy_cash))
            if max_buy > 0:
                actions["buy"] = max_buy

        # Short side
        if short_shares > 0:
            actions["cover"] = short_shares
        
        # Calculate max_short based on long_only flag
        if long_only:
            # Disable shorting entirely when --no-short is passed
            max_short = 0
        elif price > 0 and max_qty > 0:
            if margin_requirement <= 0.0:
                # If margin requirement is zero or unset, only cap by max_qty
                # This is intentional risk-managed shorting behavior
                max_short = max_qty
            else:
                available_margin = max(0.0, (equity / margin_requirement) - margin_used)
                max_short_margin = int(available_margin // price)
                max_short = max(0, min(max_qty, max_short_margin))
        else:
            max_short = 0
        
        if max_short > 0:
            actions["short"] = max_short

        # Hold always valid
        actions["hold"] = 0

        # Prune zero-capacity actions to reduce tokens, keep hold
        pruned = {"hold": 0}
        for k, v in actions.items():
            if k != "hold" and v > 0:
                pruned[k] = v

        # Log allowed actions for debugging
        logger.debug(f"[compute_allowed_actions] {ticker}: price={price:.2f}, max_qty={max_qty}, "
                     f"long={long_shares}, short={short_shares}, allowed={pruned}")
        
        # If only hold is available, log the reason
        if set(pruned.keys()) == {"hold"}:
            reasons = []
            if long_shares == 0:
                reasons.append("no long position to sell")
            if max_qty == 0:
                reasons.append("max_qty=0 from risk manager")
            elif price <= 0:
                reasons.append("invalid price")
            elif cash <= 0:
                reasons.append("no cash")
            elif int(cash // price) == 0:
                reasons.append("cash insufficient for 1 share")
            if margin_requirement > 0 and max_qty > 0:
                available_margin = max(0.0, (equity / margin_requirement) - margin_used)
                if int(available_margin // price) == 0:
                    reasons.append("insufficient margin for short")
            logger.debug(f"[compute_allowed_actions] {ticker}: HOLD only - reasons: {', '.join(reasons) or 'unknown'}")

        allowed[ticker] = pruned

    return allowed


def _compact_signals(signals_by_ticker: dict[str, dict]) -> dict[str, dict]:
    """Keep only {agent: {sig, conf}} and drop empty agents."""
    out = {}
    for t, agents in signals_by_ticker.items():
        if not agents:
            out[t] = {}
            continue
        compact = {}
        for agent, payload in agents.items():
            sig = payload.get("sig") or payload.get("signal")
            conf = payload.get("conf") if "conf" in payload else payload.get("confidence")
            if sig is not None and conf is not None:
                compact[agent] = {"sig": sig, "conf": conf}
        out[t] = compact
    return out


def generate_trading_decision(
        tickers: list[str],
        signals_by_ticker: dict[str, dict],
        current_prices: dict[str, float],
        max_shares: dict[str, int],
        portfolio: dict[str, float],
        agent_id: str,
        state: AgentState,
        long_only: bool = False,
        position_context: dict = None,
) -> PortfolioManagerOutput:
    """Get decisions from the LLM with deterministic constraints and a minimal prompt.

    Args:
        tickers: List of ticker symbols
        signals_by_ticker: Analyst signals per ticker
        current_prices: Current prices per ticker
        max_shares: Max shares allowed per ticker (from risk manager)
        portfolio: Portfolio state dict
        agent_id: Agent identifier for logging
        state: Agent state
        long_only: If True, disable short selling (--no-short flag)
        position_context: Optional dict of ticker -> Polymarket event context
    """

    # Deterministic constraints
    allowed_actions_full = compute_allowed_actions(tickers, current_prices, max_shares, portfolio, long_only=long_only)

    # Pre-fill pure holds to avoid sending them to the LLM at all
    prefilled_decisions: dict[str, PortfolioDecision] = {}
    tickers_for_llm: list[str] = []
    for t in tickers:
        aa = allowed_actions_full.get(t, {"hold": 0})
        # If only 'hold' key exists, there is no trade possible
        if set(aa.keys()) == {"hold"}:
            prefilled_decisions[t] = PortfolioDecision(
                action="hold", quantity=0, confidence=100.0, reasoning="No valid trade available"
            )
        else:
            tickers_for_llm.append(t)

    if not tickers_for_llm:
        return PortfolioManagerOutput(decisions=prefilled_decisions)

    # Build compact payloads only for tickers sent to LLM
    compact_signals = _compact_signals({t: signals_by_ticker.get(t, {}) for t in tickers_for_llm})
    compact_allowed = {t: allowed_actions_full[t] for t in tickers_for_llm}

    # Build event context string for tickers that have Polymarket context
    event_context_str = ""
    if position_context:
        event_context_parts = []
        for ticker in tickers_for_llm:
            ctx = position_context.get(ticker)
            if ctx:
                try:
                    if isinstance(ctx, dict):
                        from src.data.position_context import PositionContext as PC
                        pc = PC(**ctx)
                        summary = pc.get_context_summary()
                    else:
                        summary = ctx.get_context_summary()
                    if summary:
                        event_context_parts.append(summary)
                except Exception:
                    pass
        if event_context_parts:
            event_context_str = "\n".join(event_context_parts)

    # Minimal prompt template
    system_msg = (
        "You are a portfolio manager.\n"
        "Inputs per ticker: analyst signals and allowed actions with max qty (already validated).\n"
    )
    if long_only:
        system_msg += (
            "LONG-ONLY MODE: Short selling is disabled. Your actions are buy, sell, and hold.\n"
            "Tactical selling is encouraged: if you hold a position and expect a near-term pullback, "
            "sell now to lock in gains, then rebuy at a lower price on the next cycle. "
            "Selling is not just for exiting — it is your tool for capturing downside moves.\n"
        )
    if event_context_str:
        system_msg += (
            "POLYMARKET EVENT CONTEXT:\n"
            "Event context includes the thesis (why this stock was picked) and outcome landscape.\n"
            "- DOMINANT outcome (one outcome >60%, large gap): High confidence directional signal. Commit to the thesis.\n"
            "- CONCENTRATED (leader >50%): Thesis likely valid but not certain. Normal position sizing.\n"
            "- CONTESTED (top-2 >70%, leader <50%): Two-horse race. Consider reducing position or hedging.\n"
            "- DISTRIBUTED (no consensus): Thesis uncertain. Smaller position or hold.\n"
            "If the target outcome probability has DROPPED significantly since entry, consider selling.\n"
            "If target outcome has RISEN since entry, thesis is strengthening — consider adding.\n"
        )
    system_msg += (
        "Pick one allowed action per ticker and a quantity ≤ the max. "
        "Keep reasoning very concise (max 100 chars). No cash or margin math. Return JSON only."
    )

    human_msg = "{event_context}" \
        "Signals:\n{signals}\n\n" \
        "Allowed:\n{allowed}\n\n" \
        "Format:\n" \
        "{{\n" \
        '  "decisions": {{\n' \
        '    "TICKER": {{"action":"...","quantity":int,"confidence":int,"reasoning":"..."}}\n' \
        "  }}\n" \
        "}}"

    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            ("human", human_msg),
        ]
    )

    prompt_data = {
        "signals": json.dumps(compact_signals, separators=(",", ":"), ensure_ascii=False),
        "allowed": json.dumps(compact_allowed, separators=(",", ":"), ensure_ascii=False),
        "event_context": f"Event Context:\n{event_context_str}\n\n" if event_context_str else "",
    }
    prompt = template.invoke(prompt_data)

    # Default factory fills remaining tickers as hold if the LLM fails
    def create_default_portfolio_output():
        # start from prefilled
        decisions = dict(prefilled_decisions)
        for t in tickers_for_llm:
            decisions[t] = PortfolioDecision(
                action="hold", quantity=0, confidence=0.0, reasoning="Default decision: hold"
            )
        return PortfolioManagerOutput(decisions=decisions)

    llm_out = call_llm(
        prompt=prompt,
        pydantic_model=PortfolioManagerOutput,
        agent_name=agent_id,
        state=state,
        default_factory=create_default_portfolio_output,
    )

    # Merge prefilled holds with LLM results
    merged = dict(prefilled_decisions)
    merged.update(llm_out.decisions)
    return PortfolioManagerOutput(decisions=merged)
