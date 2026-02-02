from __future__ import annotations

from datetime import datetime
from typing import Sequence, Dict, Optional, Union
import logging

import pandas as pd
from dateutil.relativedelta import relativedelta

from .controller import AgentController
from .trader import TradeExecutor
from .metrics import PerformanceMetricsCalculator
from .portfolio import Portfolio
from .types import PerformanceMetrics, PortfolioValuePoint
from .valuation import calculate_portfolio_value, compute_exposures
from .output import OutputBuilder
from .benchmarks import BenchmarkCalculator

from src.tools.api import (
    get_company_news,
    get_price_data,
    get_prices,
    get_financial_metrics,
    get_insider_trades,
)
from src.core import TradingCycle, TradingConfig, DailyCycleResult

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Coordinates the backtest loop using the unified TradingCycle.

    This implementation uses the unified core module (src/core/) to ensure
    backtest and live trading share the same logic. The TradingCycle handles:
    - Daily discovery of new events (autonomous mode)
    - Position context updates with latest probabilities
    - Event resolution detection
    - Agent workflow execution

    The engine is responsible for:
    - Date iteration
    - Trade execution
    - Portfolio valuation
    - Performance metrics
    """

    def __init__(
        self,
        *,
        agent,
        tickers: list[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        initial_margin_requirement: float,
        # New: Accept TradingConfig for unified architecture
        config: Optional[TradingConfig] = None,
        # Legacy parameters for backward compatibility
        model_name: Optional[str] = None,
        model_provider: Optional[str] = None,
        selected_analysts: Optional[list[str]] = None,
        position_context: Optional[dict] = None,
    ) -> None:
        """Initialize the BacktestEngine.
        
        Args:
            agent: The agent function (run_hedge_fund)
            tickers: Initial list of tickers to analyze
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            initial_capital: Starting capital
            initial_margin_requirement: Margin requirement for short positions
            config: TradingConfig for unified architecture (preferred)
            model_name: LLM model name (legacy, use config instead)
            model_provider: LLM provider (legacy, use config instead)
            selected_analysts: Analyst list (legacy, use config instead)
            position_context: Initial position contexts (legacy, use config instead)
        """
        self._agent = agent
        self._tickers = list(tickers)  # Make a copy to avoid mutation
        self._start_date = start_date
        self._end_date = end_date
        self._initial_capital = float(initial_capital)
        
        # Handle config vs legacy parameters
        if config is not None:
            self._config = config
            self._model_name = config.model_name
            self._model_provider = config.model_provider
            self._selected_analysts = config.selected_analysts
        else:
            # Legacy mode: build config from individual parameters
            self._model_name = model_name or "gpt-4.1"
            self._model_provider = model_provider or "OpenAI"
            self._selected_analysts = selected_analysts or []
            self._config = TradingConfig(
                model_name=self._model_name,
                model_provider=self._model_provider,
                selected_analysts=self._selected_analysts,
                autonomous_mode=False,  # Legacy mode defaults to manual
            )
        
        self._position_context = position_context or {}

        # Initialize portfolio with current tickers
        # Note: In autonomous mode, new tickers may be added dynamically
        self._portfolio = Portfolio(
            tickers=tickers,
            initial_cash=initial_capital,
            margin_requirement=initial_margin_requirement,
        )
        
        # Initialize the unified TradingCycle
        self._trading_cycle = TradingCycle(self._config)
        
        self._executor = TradeExecutor()
        self._agent_controller = AgentController()
        self._perf = PerformanceMetricsCalculator()
        self._results = OutputBuilder(initial_capital=self._initial_capital)

        # Benchmark calculator
        self._benchmark = BenchmarkCalculator()

        self._portfolio_values: list[PortfolioValuePoint] = []
        self._table_rows: list[list] = []
        self._performance_metrics: PerformanceMetrics = {
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": None,
            "long_short_ratio": None,
            "gross_exposure": None,
            "net_exposure": None,
        }

    def _prefetch_data(self, tickers: list[str]) -> None:
        """Prefetch financial data for the given tickers.
        
        Args:
            tickers: List of tickers to prefetch data for
        """
        end_date_dt = datetime.strptime(self._end_date, "%Y-%m-%d")
        start_date_dt = end_date_dt - relativedelta(years=1)
        start_date_str = start_date_dt.strftime("%Y-%m-%d")

        for ticker in tickers:
            try:
                get_prices(ticker, start_date_str, self._end_date)
                get_financial_metrics(ticker, self._end_date, limit=10)
                get_insider_trades(ticker, self._end_date, start_date=self._start_date, limit=1000)
                get_company_news(ticker, self._end_date, start_date=self._start_date, limit=1000)
            except Exception as e:
                logger.warning(f"Failed to prefetch data for {ticker}: {e}")
        
        # Preload data for SPY for benchmark comparison
        # Always extend date range to avoid yfinance single-day errors
        # Use a wider range (1 year back) to ensure we have data
        try:
            get_prices("SPY", start_date_str, self._end_date)
        except Exception:
            # Silently ignore SPY fetch errors - benchmark is optional
            pass

    def _add_ticker_to_portfolio(self, ticker: str) -> None:
        """Add a new ticker to the portfolio's position tracking.
        
        This is needed when discovery finds new tickers mid-backtest.
        
        Args:
            ticker: The ticker symbol to add
        """
        positions = self._portfolio._portfolio["positions"]
        realized_gains = self._portfolio._portfolio["realized_gains"]
        
        if ticker not in positions:
            positions[ticker] = {
                "long": 0,
                "short": 0,
                "long_cost_basis": 0.0,
                "short_cost_basis": 0.0,
                "short_margin_used": 0.0,
            }
        if ticker not in realized_gains:
            realized_gains[ticker] = {"long": 0.0, "short": 0.0}

    def _get_current_prices(
        self,
        tickers: list[str],
        current_date: datetime,
        prev_date: datetime
    ) -> tuple[Dict[str, float], list[str]]:
        """Fetch current prices for all tickers.
        
        Args:
            tickers: List of tickers to get prices for
            current_date: Current date
            prev_date: Previous business day
            
        Returns:
            Tuple of (prices dict, list of tickers with missing data)
        """
        current_date_str = current_date.strftime("%Y-%m-%d")
        previous_date_str = prev_date.strftime("%Y-%m-%d")
        
        current_prices: Dict[str, float] = {}
        missing_tickers: list[str] = []
        
        for ticker in tickers:
            try:
                # Use a wider date range to ensure we get data
                # yfinance sometimes needs a buffer for single-day queries
                price_data = get_price_data(ticker, previous_date_str, current_date_str)
                if price_data.empty:
                    # Try extending the lookback by a few more days
                    extended_prev = (prev_date - relativedelta(days=3)).strftime("%Y-%m-%d")
                    price_data = get_price_data(ticker, extended_prev, current_date_str)
                    if price_data.empty:
                        missing_tickers.append(ticker)
                        continue
                current_prices[ticker] = float(price_data.iloc[-1]["close"])
            except Exception as e:
                logger.warning(f"Failed to get price for {ticker}: {e}")
                missing_tickers.append(ticker)
        
        return current_prices, missing_tickers

    def run_backtest(self) -> PerformanceMetrics:
        """Run the backtest using the unified TradingCycle.
        
        This method iterates through each business day in the date range,
        executing the daily trading cycle which includes:
        - Discovery of new events (autonomous mode)
        - Position context updates
        - Agent analysis and decision making
        - Trade execution
        
        Returns:
            PerformanceMetrics with sharpe, sortino, max drawdown, etc.
        """
        # Prefetch data for initial tickers
        self._prefetch_data(self._tickers)

        dates = pd.date_range(self._start_date, self._end_date, freq="B")
        if len(dates) > 0:
            self._portfolio_values = [
                {"Date": dates[0], "Portfolio Value": self._initial_capital}
            ]
        else:
            self._portfolio_values = []

        # Track tickers that have been prefetched
        prefetched_tickers = set(self._tickers)

        for current_date in dates:
            current_date_str = current_date.strftime("%Y-%m-%d")
            
            # Calculate previous business day (not just previous calendar day)
            # This handles weekends: if current_date is Monday, previous business day is Friday
            prev_date = current_date - relativedelta(days=1)
            # Skip back over weekends (Saturday=5, Sunday=6)
            while prev_date.weekday() >= 5:
                prev_date = prev_date - relativedelta(days=1)
            
            lookback_start = (current_date - relativedelta(months=1)).strftime("%Y-%m-%d")
            if lookback_start == current_date_str:
                continue

            # ==================== EXECUTE DAILY CYCLE ====================
            # This is the key change: use TradingCycle instead of direct agent call
            # Discovery happens INSIDE this call, updating position contexts daily
            
            result: DailyCycleResult = self._trading_cycle.execute_daily_cycle(
                current_date=current_date_str,
                tickers=self._tickers,
                portfolio=self._portfolio.get_snapshot(),
                position_contexts=self._position_context,  # Mutable, updated in-place
                mode="backtest",
                lookback_days=30,
            )
            
            # Handle skip_day (no valid tickers found)
            if result.skip_day:
                logger.info(f"[{current_date_str}] Skipping day: {result.cycle_summary}")
                continue
            
            # Update tickers if new discoveries were made
            if result.discovered_tickers:
                logger.info(f"[{current_date_str}] New tickers discovered: {result.discovered_tickers}")
                for ticker in result.discovered_tickers:
                    if ticker not in self._tickers:
                        self._tickers.append(ticker)
                        self._add_ticker_to_portfolio(ticker)
                        
                        # Prefetch data for new tickers
                        if ticker not in prefetched_tickers:
                            self._prefetch_data([ticker])
                            prefetched_tickers.add(ticker)
            
            # Update position contexts from result
            self._position_context = result.updated_contexts
            
            # Get current prices for all tickers
            current_prices, missing_tickers = self._get_current_prices(
                self._tickers, current_date, prev_date
            )
            
            # Skip day if critical tickers have missing data
            if len(missing_tickers) == len(self._tickers):
                logger.warning(f"[{current_date_str}] All tickers missing price data, skipping")
                continue
            
            # Log any missing tickers
            if missing_tickers:
                logger.warning(f"[{current_date_str}] Missing price data for: {missing_tickers}")

            # Get decisions from the cycle result
            decisions = result.decisions

            # Execute trades based on decisions
            executed_trades: Dict[str, int] = {}
            for ticker in self._tickers:
                if ticker in missing_tickers:
                    executed_trades[ticker] = 0
                    continue
                    
                d = decisions.get(ticker, {"action": "hold", "quantity": 0})
                action = d.get("action", "hold")
                qty = d.get("quantity", 0)
                price = current_prices.get(ticker, 0.0)
                
                if price > 0:
                    executed_qty = self._executor.execute_trade(
                        ticker, action, qty, price, self._portfolio
                    )
                    executed_trades[ticker] = executed_qty
                else:
                    executed_trades[ticker] = 0

            # Calculate portfolio value and exposures
            total_value = calculate_portfolio_value(self._portfolio, current_prices)
            exposures = compute_exposures(self._portfolio, current_prices)

            point: PortfolioValuePoint = {
                "Date": current_date,
                "Portfolio Value": total_value,
                "Long Exposure": exposures["Long Exposure"],
                "Short Exposure": exposures["Short Exposure"],
                "Gross Exposure": exposures["Gross Exposure"],
                "Net Exposure": exposures["Net Exposure"],
                "Long/Short Ratio": exposures["Long/Short Ratio"],
            }
            self._portfolio_values.append(point)
            
            # Build agent_output dict for display compatibility
            agent_output = {
                "decisions": decisions,
                "analyst_signals": result.analyst_signals,
            }
            
            # Build daily rows (stateless usage)
            rows = self._results.build_day_rows(
                date_str=current_date_str,
                tickers=self._tickers,
                agent_output=agent_output,
                executed_trades=executed_trades,
                current_prices=current_prices,
                portfolio=self._portfolio,
                performance_metrics=self._performance_metrics,
                total_value=total_value,
                benchmark_return_pct=self._benchmark.get_return_pct("SPY", self._start_date, current_date_str),
            )
            # Prepend today's rows to historical rows so latest day is on top
            self._table_rows = rows + self._table_rows
            # Print full history with latest day first (matches backtester.py behavior)
            self._results.print_rows(self._table_rows)

            # Update performance metrics after printing (match original timing)
            if len(self._portfolio_values) > 3:
                computed = self._perf.compute_metrics(self._portfolio_values)
                if computed:
                    self._performance_metrics.update(computed)

        return self._performance_metrics

    def get_portfolio_values(self) -> Sequence[PortfolioValuePoint]:
        return list(self._portfolio_values)


