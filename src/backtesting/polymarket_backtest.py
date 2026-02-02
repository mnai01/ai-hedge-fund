"""Backtesting module for Polymarket-based trading strategies.

This module provides functionality to:
- Fetch historical probability data from Polymarket CLOB API
- Correlate probability changes with stock price movements
- Calculate strategy performance metrics
- Generate backtest reports

Follows patterns from src/backtesting/ modules.
"""

import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field

from src.tools.polymarket_api import (
    get_active_events,
    get_price_history,
    get_event_by_id,
)
from src.tools.api import get_prices, prices_to_df
from src.data.polymarket_models import (
    PolymarketEvent,
    PriceHistory,
    ProbabilityChange,
    PolymarketTradeDecision,
    BacktestResult,
)
from src.data.polymarket_cache import get_polymarket_cache


@dataclass
class BacktestConfig:
    """Configuration for Polymarket backtesting."""
    
    # Time period
    start_date: datetime
    end_date: datetime
    
    # Trading parameters
    initial_capital: float = 100000.0
    position_size_pct: float = 0.10  # 10% of capital per trade
    max_positions: int = 5
    
    # Signal thresholds
    probability_change_threshold: float = 0.05  # 5% change triggers signal
    confidence_threshold: float = 60  # Minimum confidence to trade
    
    # Risk management
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.10  # 10% take profit
    max_holding_days: int = 5  # Maximum days to hold a position
    
    # Data settings
    data_provider: str = "yfinance"


@dataclass
class Position:
    """Represents an open position."""
    
    ticker: str
    event_id: str
    event_title: str
    direction: str  # "long" or "short"
    entry_price: float
    entry_date: datetime
    shares: int
    probability_at_entry: float
    confidence: float
    reasoning: str


@dataclass
class ClosedPosition:
    """Represents a closed position with P&L."""
    
    ticker: str
    event_id: str
    event_title: str
    direction: str
    entry_price: float
    entry_date: datetime
    exit_price: float
    exit_date: datetime
    shares: int
    profit_loss: float
    profit_loss_pct: float
    exit_reason: str  # "stop_loss", "take_profit", "max_holding", "signal_change"


@dataclass
class BacktestState:
    """State during backtesting."""
    
    cash: float
    positions: List[Position] = field(default_factory=list)
    closed_positions: List[ClosedPosition] = field(default_factory=list)
    daily_values: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def total_value(self) -> float:
        """Calculate total portfolio value (not including position values)."""
        return self.cash


class PolymarketBacktester:
    """
    Backtester for Polymarket-based trading strategies.
    
    This class simulates trading based on Polymarket probability changes
    and their correlation with stock price movements.
    
    Example:
        >>> config = BacktestConfig(
        ...     start_date=datetime(2024, 1, 1),
        ...     end_date=datetime(2024, 6, 30),
        ... )
        >>> backtester = PolymarketBacktester(config)
        >>> results = backtester.run(
        ...     event_stock_mappings={
        ...         "event_123": [("AAPL", "bullish"), ("MSFT", "bearish")]
        ...     }
        ... )
        >>> print(f"Total return: {results.total_return_percent:.2f}%")
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize the backtester.
        
        Args:
            config: Backtesting configuration
        """
        self.config = config
        self.cache = get_polymarket_cache()
        self.state = BacktestState(cash=config.initial_capital)
    
    def run(
        self,
        event_stock_mappings: Dict[str, List[Tuple[str, str]]],
        verbose: bool = False,
    ) -> BacktestResult:
        """
        Run the backtest.
        
        Args:
            event_stock_mappings: Dict mapping event_id to list of (ticker, direction) tuples
            verbose: Print progress information
        
        Returns:
            BacktestResult with performance metrics
        """
        if verbose:
            print(f"Starting backtest from {self.config.start_date} to {self.config.end_date}")
            print(f"Initial capital: ${self.config.initial_capital:,.2f}")
            print(f"Events to track: {len(event_stock_mappings)}")
        
        # Reset state
        self.state = BacktestState(cash=self.config.initial_capital)
        
        # Fetch historical data for all events and stocks
        event_histories = self._fetch_event_histories(event_stock_mappings.keys())
        stock_prices = self._fetch_stock_prices(event_stock_mappings)
        
        if verbose:
            print(f"Fetched history for {len(event_histories)} events")
            print(f"Fetched prices for {len(stock_prices)} stocks")
        
        # Generate daily signals and simulate trading
        current_date = self.config.start_date
        
        while current_date <= self.config.end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Check for exit conditions on existing positions
            self._check_exits(current_date, stock_prices)
            
            # Generate signals for the day
            signals = self._generate_daily_signals(
                current_date,
                event_histories,
                event_stock_mappings,
            )
            
            # Execute trades based on signals
            self._execute_trades(current_date, signals, stock_prices)
            
            # Record daily portfolio value
            portfolio_value = self._calculate_portfolio_value(current_date, stock_prices)
            self.state.daily_values.append({
                "date": current_date.isoformat(),
                "cash": self.state.cash,
                "positions_value": portfolio_value - self.state.cash,
                "total_value": portfolio_value,
                "open_positions": len(self.state.positions),
            })
            
            current_date += timedelta(days=1)
        
        # Close any remaining positions at end
        self._close_all_positions(self.config.end_date, stock_prices, "backtest_end")
        
        # Calculate results
        return self._calculate_results()
    
    def _fetch_event_histories(
        self,
        event_ids: List[str],
    ) -> Dict[str, PriceHistory]:
        """Fetch historical probability data for events."""
        histories = {}
        
        for event_id in event_ids:
            try:
                # Get event to find token ID
                event = get_event_by_id(event_id, cache=self.cache)
                if not event or not event.primary_market:
                    continue
                
                token_id = event.primary_market.primary_token_id
                if not token_id:
                    continue
                
                # Fetch price history
                history = get_price_history(
                    token_id=token_id,
                    interval="max",
                    fidelity=1440,  # Daily data
                    cache=self.cache,
                )
                
                if history and history.history:
                    histories[event_id] = history
                    
            except Exception as e:
                print(f"Error fetching history for event {event_id}: {e}")
                continue
        
        return histories
    
    def _fetch_stock_prices(
        self,
        event_stock_mappings: Dict[str, List[Tuple[str, str]]],
    ) -> Dict[str, Any]:
        """Fetch historical stock prices for all tickers."""
        # Get unique tickers
        tickers = set()
        for mappings in event_stock_mappings.values():
            for ticker, _ in mappings:
                tickers.add(ticker)
        
        prices = {}
        
        for ticker in tickers:
            try:
                price_data = get_prices(
                    ticker=ticker,
                    start_date=self.config.start_date.strftime("%Y-%m-%d"),
                    end_date=self.config.end_date.strftime("%Y-%m-%d"),
                    data_provider=self.config.data_provider,
                )
                
                if price_data:
                    df = prices_to_df(price_data)
                    prices[ticker] = df
                    
            except Exception as e:
                print(f"Error fetching prices for {ticker}: {e}")
                continue
        
        return prices
    
    def _generate_daily_signals(
        self,
        date: datetime,
        event_histories: Dict[str, PriceHistory],
        event_stock_mappings: Dict[str, List[Tuple[str, str]]],
    ) -> List[Dict[str, Any]]:
        """Generate trading signals for a specific date."""
        signals = []
        date_ts = int(date.timestamp())
        
        for event_id, history in event_histories.items():
            if event_id not in event_stock_mappings:
                continue
            
            # Find probability at this date and previous day
            current_prob = self._get_probability_at_date(history, date_ts)
            prev_prob = self._get_probability_at_date(history, date_ts - 86400)
            
            if current_prob is None or prev_prob is None:
                continue
            
            # Calculate change
            prob_change = current_prob - prev_prob
            
            # Check if change exceeds threshold
            if abs(prob_change) < self.config.probability_change_threshold:
                continue
            
            # Generate signals for mapped stocks
            for ticker, direction in event_stock_mappings[event_id]:
                # Determine signal based on probability change and mapping direction
                if direction == "bullish":
                    # Probability up = bullish for stock
                    signal = "buy" if prob_change > 0 else "sell"
                elif direction == "bearish":
                    # Probability up = bearish for stock
                    signal = "sell" if prob_change > 0 else "buy"
                else:
                    continue
                
                signals.append({
                    "ticker": ticker,
                    "event_id": event_id,
                    "signal": signal,
                    "probability": current_prob,
                    "probability_change": prob_change,
                    "confidence": min(abs(prob_change) * 1000, 100),  # Scale change to confidence
                })
        
        return signals
    
    def _get_probability_at_date(
        self,
        history: PriceHistory,
        timestamp: int,
    ) -> Optional[float]:
        """Get probability closest to a given timestamp."""
        if not history.history:
            return None
        
        # Find closest point
        closest = min(history.history, key=lambda p: abs(p.timestamp - timestamp))
        
        # Only return if within 2 days
        if abs(closest.timestamp - timestamp) > 172800:
            return None
        
        return closest.probability
    
    def _execute_trades(
        self,
        date: datetime,
        signals: List[Dict[str, Any]],
        stock_prices: Dict[str, Any],
    ):
        """Execute trades based on signals."""
        for signal in signals:
            ticker = signal["ticker"]
            
            # Skip if we already have a position in this ticker
            if any(p.ticker == ticker for p in self.state.positions):
                continue
            
            # Skip if confidence below threshold
            if signal["confidence"] < self.config.confidence_threshold:
                continue
            
            # Skip if max positions reached
            if len(self.state.positions) >= self.config.max_positions:
                continue
            
            # Get current price
            price = self._get_price_at_date(stock_prices, ticker, date)
            if price is None:
                continue
            
            # Calculate position size
            position_value = self.state.cash * self.config.position_size_pct
            shares = int(position_value / price)
            
            if shares <= 0:
                continue
            
            # Check if we have enough cash
            cost = shares * price
            if cost > self.state.cash:
                continue
            
            # Open position
            direction = "long" if signal["signal"] == "buy" else "short"
            
            position = Position(
                ticker=ticker,
                event_id=signal["event_id"],
                event_title="",  # Would need to fetch
                direction=direction,
                entry_price=price,
                entry_date=date,
                shares=shares,
                probability_at_entry=signal["probability"],
                confidence=signal["confidence"],
                reasoning=f"Probability change: {signal['probability_change']:.2%}",
            )
            
            self.state.positions.append(position)
            self.state.cash -= cost
    
    def _check_exits(
        self,
        date: datetime,
        stock_prices: Dict[str, Any],
    ):
        """Check exit conditions for open positions."""
        positions_to_close = []
        
        for position in self.state.positions:
            current_price = self._get_price_at_date(stock_prices, position.ticker, date)
            if current_price is None:
                continue
            
            # Calculate P&L
            if position.direction == "long":
                pnl_pct = (current_price - position.entry_price) / position.entry_price
            else:
                pnl_pct = (position.entry_price - current_price) / position.entry_price
            
            exit_reason = None
            
            # Check stop loss
            if pnl_pct <= -self.config.stop_loss_pct:
                exit_reason = "stop_loss"
            
            # Check take profit
            elif pnl_pct >= self.config.take_profit_pct:
                exit_reason = "take_profit"
            
            # Check max holding period
            elif (date - position.entry_date).days >= self.config.max_holding_days:
                exit_reason = "max_holding"
            
            if exit_reason:
                positions_to_close.append((position, current_price, exit_reason))
        
        # Close positions
        for position, exit_price, exit_reason in positions_to_close:
            self._close_position(position, date, exit_price, exit_reason)
    
    def _close_position(
        self,
        position: Position,
        date: datetime,
        exit_price: float,
        exit_reason: str,
    ):
        """Close a position and record the result."""
        # Calculate P&L
        if position.direction == "long":
            profit_loss = (exit_price - position.entry_price) * position.shares
            profit_loss_pct = (exit_price - position.entry_price) / position.entry_price
        else:
            profit_loss = (position.entry_price - exit_price) * position.shares
            profit_loss_pct = (position.entry_price - exit_price) / position.entry_price
        
        # Create closed position record
        closed = ClosedPosition(
            ticker=position.ticker,
            event_id=position.event_id,
            event_title=position.event_title,
            direction=position.direction,
            entry_price=position.entry_price,
            entry_date=position.entry_date,
            exit_price=exit_price,
            exit_date=date,
            shares=position.shares,
            profit_loss=profit_loss,
            profit_loss_pct=profit_loss_pct,
            exit_reason=exit_reason,
        )
        
        self.state.closed_positions.append(closed)
        
        # Update cash
        self.state.cash += position.shares * exit_price
        
        # Remove from open positions
        self.state.positions.remove(position)
    
    def _close_all_positions(
        self,
        date: datetime,
        stock_prices: Dict[str, Any],
        exit_reason: str,
    ):
        """Close all open positions."""
        for position in list(self.state.positions):
            exit_price = self._get_price_at_date(stock_prices, position.ticker, date)
            if exit_price:
                self._close_position(position, date, exit_price, exit_reason)
    
    def _get_price_at_date(
        self,
        stock_prices: Dict[str, Any],
        ticker: str,
        date: datetime,
    ) -> Optional[float]:
        """Get stock price at a specific date."""
        if ticker not in stock_prices:
            return None
        
        df = stock_prices[ticker]
        date_str = date.strftime("%Y-%m-%d")
        
        try:
            # Try exact date
            if date_str in df.index.strftime("%Y-%m-%d"):
                return float(df.loc[date_str, "close"])
            
            # Find closest date
            df_filtered = df[df.index <= date]
            if not df_filtered.empty:
                return float(df_filtered.iloc[-1]["close"])
                
        except (KeyError, IndexError):
            pass
        
        return None
    
    def _calculate_portfolio_value(
        self,
        date: datetime,
        stock_prices: Dict[str, Any],
    ) -> float:
        """Calculate total portfolio value including positions."""
        total = self.state.cash
        
        for position in self.state.positions:
            price = self._get_price_at_date(stock_prices, position.ticker, date)
            if price:
                total += position.shares * price
        
        return total
    
    def _calculate_results(self) -> BacktestResult:
        """Calculate final backtest results."""
        # Calculate returns
        final_value = self.state.cash
        for position in self.state.positions:
            # Shouldn't have any open positions at end, but just in case
            final_value += position.shares * position.entry_price
        
        total_return = final_value - self.config.initial_capital
        total_return_pct = (total_return / self.config.initial_capital) * 100
        
        # Calculate trade statistics
        total_trades = len(self.state.closed_positions)
        winning_trades = sum(1 for p in self.state.closed_positions if p.profit_loss > 0)
        losing_trades = sum(1 for p in self.state.closed_positions if p.profit_loss < 0)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate average profit/loss
        profits = [p.profit_loss for p in self.state.closed_positions if p.profit_loss > 0]
        losses = [p.profit_loss for p in self.state.closed_positions if p.profit_loss < 0]
        
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        # Calculate max drawdown
        max_drawdown = self._calculate_max_drawdown()
        
        # Calculate Sharpe ratio (simplified)
        sharpe = self._calculate_sharpe_ratio()
        
        # Convert closed positions to trade decisions
        trades = [
            PolymarketTradeDecision(
                ticker=p.ticker,
                event_id=p.event_id,
                event_title=p.event_title,
                signal="bullish" if p.direction == "long" else "bearish",
                confidence=0,  # Not tracked in closed position
                probability_at_decision=0,  # Not tracked
                probability_change=0,  # Not tracked
                decision_timestamp=p.entry_date,
                reasoning=f"Exit: {p.exit_reason}",
                entry_price=p.entry_price,
                exit_price=p.exit_price,
                profit_loss=p.profit_loss,
                profit_loss_percent=p.profit_loss_pct * 100,
            )
            for p in self.state.closed_positions
        ]
        
        return BacktestResult(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=final_value,
            total_return=total_return,
            total_return_percent=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            average_profit=avg_profit,
            average_loss=avg_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            trades=trades,
        )
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from daily values."""
        if not self.state.daily_values:
            return 0
        
        peak = self.config.initial_capital
        max_dd = 0
        
        for day in self.state.daily_values:
            value = day["total_value"]
            if value > peak:
                peak = value
            
            drawdown = (peak - value) / peak
            if drawdown > max_dd:
                max_dd = drawdown
        
        return max_dd * 100  # Return as percentage
    
    def _calculate_sharpe_ratio(self) -> Optional[float]:
        """Calculate Sharpe ratio from daily returns."""
        if len(self.state.daily_values) < 2:
            return None
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(self.state.daily_values)):
            prev_value = self.state.daily_values[i - 1]["total_value"]
            curr_value = self.state.daily_values[i]["total_value"]
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(daily_return)
        
        if not returns:
            return None
        
        # Calculate mean and std
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_return = variance ** 0.5
        
        if std_return == 0:
            return None
        
        # Annualize (assuming 252 trading days)
        annualized_return = mean_return * 252
        annualized_std = std_return * (252 ** 0.5)
        
        # Assume risk-free rate of 4%
        risk_free_rate = 0.04
        
        sharpe = (annualized_return - risk_free_rate) / annualized_std
        
        return round(sharpe, 2)


def run_simple_backtest(
    event_id: str,
    ticker: str,
    direction: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 100000,
) -> BacktestResult:
    """
    Run a simple backtest for a single event-stock mapping.
    
    Args:
        event_id: Polymarket event ID
        ticker: Stock ticker
        direction: "bullish" or "bearish"
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Starting capital
    
    Returns:
        BacktestResult with performance metrics
    """
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    
    backtester = PolymarketBacktester(config)
    
    return backtester.run(
        event_stock_mappings={event_id: [(ticker, direction)]},
        verbose=True,
    )


def analyze_event_stock_correlation(
    event_id: str,
    ticker: str,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """
    Analyze the correlation between event probability changes and stock price changes.
    
    Args:
        event_id: Polymarket event ID
        ticker: Stock ticker to analyze
        lookback_days: Number of days to analyze
    
    Returns:
        Dict with correlation analysis
    """
    cache = get_polymarket_cache()
    
    # Get event and price history
    event = get_event_by_id(event_id, cache=cache)
    if not event or not event.primary_market:
        return {"error": "Event not found or has no markets"}
    
    token_id = event.primary_market.primary_token_id
    if not token_id:
        return {"error": "No token ID for event"}
    
    # Fetch probability history
    prob_history = get_price_history(
        token_id=token_id,
        interval="max",
        fidelity=1440,
        cache=cache,
    )
    
    if not prob_history or len(prob_history.history) < 2:
        return {"error": "Insufficient probability history"}
    
    # Fetch stock prices
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    try:
        stock_prices = get_prices(
            ticker=ticker,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            data_provider="yfinance",
        )
    except Exception as e:
        return {"error": f"Failed to fetch stock prices: {e}"}
    
    if not stock_prices:
        return {"error": "No stock price data available"}
    
    # Calculate daily changes
    prob_changes = []
    stock_changes = []
    
    stock_df = prices_to_df(stock_prices)
    
    for i in range(1, len(prob_history.history)):
        prev_prob = prob_history.history[i - 1]
        curr_prob = prob_history.history[i]
        
        prob_change = curr_prob.probability - prev_prob.probability
        
        # Find corresponding stock price change
        date = curr_prob.datetime.strftime("%Y-%m-%d")
        
        try:
            if date in stock_df.index.strftime("%Y-%m-%d"):
                idx = list(stock_df.index.strftime("%Y-%m-%d")).index(date)
                if idx > 0:
                    prev_price = stock_df.iloc[idx - 1]["close"]
                    curr_price = stock_df.iloc[idx]["close"]
                    stock_change = (curr_price - prev_price) / prev_price
                    
                    prob_changes.append(prob_change)
                    stock_changes.append(stock_change)
        except (KeyError, IndexError):
            continue
    
    if len(prob_changes) < 5:
        return {"error": "Insufficient data points for correlation"}
    
    # Calculate correlation
    n = len(prob_changes)
    mean_prob = sum(prob_changes) / n
    mean_stock = sum(stock_changes) / n
    
    numerator = sum(
        (prob_changes[i] - mean_prob) * (stock_changes[i] - mean_stock)
        for i in range(n)
    )
    
    denom_prob = sum((p - mean_prob) ** 2 for p in prob_changes) ** 0.5
    denom_stock = sum((s - mean_stock) ** 2 for s in stock_changes) ** 0.5
    
    if denom_prob == 0 or denom_stock == 0:
        correlation = 0
    else:
        correlation = numerator / (denom_prob * denom_stock)
    
    return {
        "event_id": event_id,
        "event_title": event.title,
        "ticker": ticker,
        "data_points": n,
        "correlation": round(correlation, 4),
        "interpretation": _interpret_correlation(correlation),
        "avg_prob_change": round(mean_prob * 100, 2),
        "avg_stock_change": round(mean_stock * 100, 2),
    }


def _interpret_correlation(correlation: float) -> str:
    """Interpret correlation coefficient."""
    abs_corr = abs(correlation)
    
    if abs_corr < 0.1:
        strength = "negligible"
    elif abs_corr < 0.3:
        strength = "weak"
    elif abs_corr < 0.5:
        strength = "moderate"
    elif abs_corr < 0.7:
        strength = "strong"
    else:
        strength = "very strong"
    
    direction = "positive" if correlation > 0 else "negative"
    
    return f"{strength} {direction} correlation"
