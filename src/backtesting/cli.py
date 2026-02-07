from __future__ import annotations

import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
import argparse
from typing import List, Dict, Any, Optional

from colorama import Fore, Style, init
import questionary

from .engine import BacktestEngine
from src.llm.models import LLM_ORDER, OLLAMA_LLM_ORDER, get_model_info, ModelProvider, AVAILABLE_MODELS, OLLAMA_MODELS
from src.utils.analysts import ANALYST_ORDER, ANALYST_CONFIG
from src.main import run_hedge_fund
from src.utils.ollama import ensure_ollama_and_model
from src.core import TradingConfig


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run backtesting engine with Autonomous or Manual mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Manual Mode (default) - user provides tickers
  python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL

  # Autonomous Mode - AI discovers and manages positions
  python -m src.backtesting.cli --autonomous --max-positions 10

  # Autonomous with exclusions (protect certain tickers from AI management)
  python -m src.backtesting.cli --autonomous --exclude AAPL,TSLA

  # Autonomous with specific event focus
  python -m src.backtesting.cli --autonomous --polymarket-event presidential-election-winner-2024
"""
    )
    
    # Mode selection
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Enable Autonomous Mode: AI discovers tickers via Polymarket and manages positions"
    )
    
    # Ticker management
    parser.add_argument(
        "--tickers",
        type=str,
        required=False,
        help="Comma-separated tickers for Manual Mode"
    )
    parser.add_argument(
        "--exclude",
        type=str,
        required=False,
        help="Comma-separated tickers to exclude from AI management (Autonomous Mode)"
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=10,
        help="Maximum number of positions in Autonomous Mode (default: 10, prevents LLM cost explosion)"
    )
    
    # Polymarket options
    parser.add_argument(
        "--polymarket-event",
        type=str,
        required=False,
        help="Specific Polymarket event slug to focus on (e.g., 'presidential-election-winner-2024')"
    )
    
    # Date range
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=(datetime.now() - relativedelta(months=1)).strftime("%Y-%m-%d"),
        help="Start date YYYY-MM-DD (default: 1 month ago)",
    )
    
    # Capital and margin
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000,
        help="Initial capital (default: 100000)"
    )
    parser.add_argument(
        "--margin-requirement",
        type=float,
        default=0.0,
        help="Margin requirement (default: 0.0)"
    )
    
    # Short selling control
    parser.add_argument(
        "--no-short",
        action="store_true",
        default=False,
        help="Disable short selling (long positions only)"
    )
    
    # Analyst selection
    parser.add_argument(
        "--analysts",
        type=str,
        required=False,
        help="Comma-separated analyst names"
    )
    parser.add_argument(
        "--analysts-all",
        action="store_true",
        help="Use all available analysts"
    )
    
    # LLM options
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Use Ollama for local LLM inference"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=False,
        help="LLM model name (e.g., 'gemini-2.0-flash', 'gpt-4o'). Skips interactive prompt."
    )
    parser.add_argument(
        "--provider",
        type=str,
        required=False,
        help="LLM provider (e.g., 'Google', 'OpenAI', 'Anthropic'). Required if --model is set."
    )

    args = parser.parse_args()
    init(autoreset=True)

    # ==================== VALIDATION ====================
    # Validate CLI arguments before proceeding
    validation_errors = []
    
    # 1. Validate date format and logic
    try:
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
    except ValueError:
        validation_errors.append(f"Invalid start-date format: '{args.start_date}'. Use YYYY-MM-DD.")
        start_dt = None

    try:
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
    except ValueError:
        validation_errors.append(f"Invalid end-date format: '{args.end_date}'. Use YYYY-MM-DD.")
        end_dt = None

    # Adjust non-trading dates (weekends + NYSE holidays) to nearest trading day
    from src.utils.trading_calendar import adjust_to_trading_day
    if start_dt:
        adjusted_start_str = adjust_to_trading_day(args.start_date, forward=True)
        if adjusted_start_str != args.start_date:
            print(f"{Fore.YELLOW}Note: start-date {args.start_date} is not a trading day. "
                  f"Adjusted to {adjusted_start_str} (next trading day).{Style.RESET_ALL}")
            args.start_date = adjusted_start_str
            start_dt = datetime.strptime(adjusted_start_str, "%Y-%m-%d")

    if end_dt:
        adjusted_end_str = adjust_to_trading_day(args.end_date, forward=False)
        if adjusted_end_str != args.end_date:
            print(f"{Fore.YELLOW}Note: end-date {args.end_date} is not a trading day. "
                  f"Adjusted to {adjusted_end_str} (previous trading day).{Style.RESET_ALL}")
            args.end_date = adjusted_end_str
            end_dt = datetime.strptime(adjusted_end_str, "%Y-%m-%d")
    
    if start_dt and end_dt and start_dt > end_dt:
        validation_errors.append(f"start-date ({args.start_date}) must be before or equal to end-date ({args.end_date}).")
    
    # 2. Validate analysts if provided via CLI
    if args.analysts:
        provided_analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]
        valid_analyst_keys = set(ANALYST_CONFIG.keys())
        invalid_analysts = [a for a in provided_analysts if a not in valid_analyst_keys]
        if invalid_analysts:
            validation_errors.append(
                f"Invalid analyst(s): {', '.join(invalid_analysts)}. "
                f"Valid options: {', '.join(sorted(valid_analyst_keys))}"
            )
    
    # 3. Validate model and provider if provided via CLI
    if args.model and args.provider:
        # Build list of valid (model_name, provider) combinations
        all_models = AVAILABLE_MODELS + OLLAMA_MODELS
        valid_combinations = {(m.model_name, m.provider.value) for m in all_models}
        valid_model_names = {m.model_name for m in all_models}
        valid_providers = {m.provider.value for m in all_models}
        
        # Check if provider is valid
        if args.provider not in valid_providers:
            validation_errors.append(
                f"Invalid provider: '{args.provider}'. "
                f"Valid options: {', '.join(sorted(valid_providers))}"
            )
        # Check if model exists (allow custom models with "-")
        elif args.model != "-" and args.model not in valid_model_names:
            # Check if it might be a typo - suggest similar models
            similar = [m for m in valid_model_names if args.model.lower() in m.lower() or m.lower() in args.model.lower()]
            error_msg = f"Invalid model: '{args.model}'."
            if similar:
                error_msg += f" Did you mean: {', '.join(similar[:3])}?"
            else:
                # Show models for the given provider
                provider_models = [m.model_name for m in all_models if m.provider.value == args.provider]
                if provider_models:
                    error_msg += f" Available {args.provider} models: {', '.join(provider_models[:5])}"
            validation_errors.append(error_msg)
    
    # Print validation errors and exit if any
    if validation_errors:
        print(f"\n{Fore.RED}{'='*60}")
        print(f"VALIDATION ERRORS")
        print(f"{'='*60}{Style.RESET_ALL}")
        for error in validation_errors:
            print(f"{Fore.RED}  [X] {error}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Tip: Use --help to see available options{Style.RESET_ALL}")
        return 1

    # Parse tickers and exclusions
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else []
    excluded_tickers = [t.strip() for t in args.exclude.split(",")] if args.exclude else []

    # Determine mode and validate
    is_autonomous = args.autonomous
    
    if is_autonomous:
        # Autonomous Mode validation
        if tickers:
            print(f"{Fore.YELLOW}Warning: --tickers ignored in Autonomous Mode. "
                  f"AI will discover tickers via Polymarket.{Style.RESET_ALL}")
            tickers = []  # Clear user-provided tickers
        
        if args.max_positions < 1:
            print(f"{Fore.RED}Error: --max-positions must be at least 1{Style.RESET_ALL}")
            return 1
        
        if args.max_positions > 20:
            print(f"{Fore.YELLOW}Warning: --max-positions > 20 may cause high LLM costs. "
                  f"Consider using a lower value.{Style.RESET_ALL}")
    else:
        # Manual Mode validation
        if not tickers:
            print(f"{Fore.RED}Error: Manual Mode requires --tickers argument{Style.RESET_ALL}")
            print(f"\nUsage examples:")
            print(f"  Manual Mode:     python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL")
            print(f"  Autonomous Mode: python -m src.backtesting.cli --autonomous")
            return 1
        
        if excluded_tickers:
            print(f"{Fore.YELLOW}Warning: --exclude is only used in Autonomous Mode. "
                  f"Ignoring exclusions.{Style.RESET_ALL}")
            excluded_tickers = []

    # Print mode info
    print(f"\n{'='*60}")
    if is_autonomous:
        print(f"Operating Mode: {Fore.MAGENTA}Autonomous{Style.RESET_ALL}")
        print(f"  AI discovers tickers via Polymarket and manages all positions")
        print(f"  Max positions: {Fore.CYAN}{args.max_positions}{Style.RESET_ALL}")
        if excluded_tickers:
            print(f"  Excluded tickers: {Fore.YELLOW}{', '.join(excluded_tickers)}{Style.RESET_ALL}")
        if args.polymarket_event:
            print(f"  Event focus: {Fore.GREEN}{args.polymarket_event}{Style.RESET_ALL}")
    else:
        print(f"Operating Mode: {Fore.BLUE}Manual{Style.RESET_ALL}")
        print(f"  User provides tickers, AI analyzes and trades what's given")
        print(f"  Tickers: {Fore.GREEN}{', '.join(tickers)}{Style.RESET_ALL}")
    print(f"{'='*60}\n")

    # Analysts selection
    # polymarket_analyst is available in both modes but must be manually selected
    # In Manual Mode, it will warn that it's designed for Autonomous Mode
    available_analysts = ANALYST_ORDER
    
    if args.analysts_all:
        selected_analysts = [a[1] for a in available_analysts]
    elif args.analysts:
        selected_analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]
        # Note: polymarket_analyst is an ANALYST, not the discovery agent
        # Discovery is handled by discover_tickers_from_events() BEFORE the backtest
        # polymarket_analyst can optionally be included to analyze event probabilities for given tickers
        if not is_autonomous and "polymarket_analyst" in selected_analysts:
            print(f"{Fore.YELLOW}Warning: polymarket_analyst analyzes Polymarket event probabilities. "
                  f"In Manual Mode, it will look for events related to your tickers.{Style.RESET_ALL}")
    else:
        # Interactive analyst selection
        choices = questionary.checkbox(
            "Use the Space bar to select/unselect analysts.",
            choices=[questionary.Choice(display, value=value) for display, value in available_analysts],
            instruction="\n\nPress 'a' to toggle all.\n\nPress Enter when done to run the hedge fund.",
            validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
            style=questionary.Style(
                [
                    ("checkbox-selected", "fg:green"),
                    ("selected", "fg:green noinherit"),
                    ("highlighted", "noinherit"),
                    ("pointer", "noinherit"),
                ]
            ),
        ).ask()
        if not choices:
            print("\n\nInterrupt received. Exiting...")
            return 1
        selected_analysts = choices
        # Warn if polymarket_analyst selected in Manual Mode
        if not is_autonomous and "polymarket_analyst" in selected_analysts:
            print(f"{Fore.YELLOW}Warning: polymarket_analyst is designed for Autonomous Mode. "
                  f"In Manual Mode, it will likely return neutral signals for all tickers.{Style.RESET_ALL}")
        print(
            f"\nSelected analysts: "
            f"{', '.join(Fore.GREEN + choice.title().replace('_', ' ') + Style.RESET_ALL for choice in selected_analysts)}\n"
        )

    # Model selection
    if args.model and args.provider:
        # Use CLI-provided model (skip interactive prompt)
        model_name = args.model
        model_provider = args.provider
        print(f"\nUsing {Fore.CYAN}{model_provider}{Style.RESET_ALL} model: {Fore.GREEN + Style.BRIGHT}{model_name}{Style.RESET_ALL}\n")
    elif args.model:
        print(f"{Fore.RED}Error: --provider is required when using --model{Style.RESET_ALL}")
        return 1
    elif args.ollama:
        print(f"{Fore.CYAN}Using Ollama for local LLM inference.{Style.RESET_ALL}")
        model_name = questionary.select(
            "Select your Ollama model:",
            choices=[questionary.Choice(display, value=value) for display, value, _ in OLLAMA_LLM_ORDER],
            style=questionary.Style(
                [
                    ("selected", "fg:green bold"),
                    ("pointer", "fg:green bold"),
                    ("highlighted", "fg:green"),
                    ("answer", "fg:green bold"),
                ]
            ),
        ).ask()
        if not model_name:
            print("\n\nInterrupt received. Exiting...")
            return 1
        if model_name == "-":
            model_name = questionary.text("Enter the custom model name:").ask()
            if not model_name:
                print("\n\nInterrupt received. Exiting...")
                return 1
        if not ensure_ollama_and_model(model_name):
            print(f"{Fore.RED}Cannot proceed without Ollama and the selected model.{Style.RESET_ALL}")
            return 1
        model_provider = ModelProvider.OLLAMA.value
        print(
            f"\nSelected {Fore.CYAN}Ollama{Style.RESET_ALL} model: {Fore.GREEN + Style.BRIGHT}{model_name}{Style.RESET_ALL}\n"
        )
    else:
        model_choice = questionary.select(
            "Select your LLM model:",
            choices=[questionary.Choice(display, value=(name, provider)) for display, name, provider in LLM_ORDER],
            style=questionary.Style(
                [
                    ("selected", "fg:green bold"),
                    ("pointer", "fg:green bold"),
                    ("highlighted", "fg:green"),
                    ("answer", "fg:green bold"),
                ]
            ),
        ).ask()
        if not model_choice:
            print("\n\nInterrupt received. Exiting...")
            return 1
        model_name, model_provider = model_choice
        model_info = get_model_info(model_name, model_provider)
        if model_info and model_info.is_custom():
            model_name = questionary.text("Enter the custom model name:").ask()
            if not model_name:
                print("\n\nInterrupt received. Exiting...")
                return 1
        print(
            f"\nSelected {Fore.CYAN}{model_provider}{Style.RESET_ALL} model: {Fore.GREEN + Style.BRIGHT}{model_name}{Style.RESET_ALL}\n"
        )

    # ==================== CREATE TRADING CONFIG ====================
    # Build TradingConfig for the unified architecture
    # Discovery now happens INSIDE the engine's daily loop, not here
    
    config = TradingConfig(
        model_name=model_name,
        model_provider=model_provider,
        selected_analysts=selected_analysts,
        autonomous_mode=is_autonomous,
        max_positions=args.max_positions,
        min_probability=0.25,  # Loose band to filter noise, not signal
        max_probability=0.75,  # Lowered from 0.85 to avoid near-certainties
        min_confidence=70,
        min_score=40.0,
        validate_with_news=True,
        news_lookback_days=7,
        min_news_articles=2,
        long_only=args.no_short,  # --no-short flag disables short selling
    )
    
    # In autonomous mode, we start with empty tickers - discovery happens daily
    # In manual mode, we use the user-provided tickers
    if is_autonomous:
        print(f"\n{'='*60}")
        print(f"{Fore.MAGENTA}[AUTONOMOUS MODE] Discovery will run DAILY{Style.RESET_ALL}")
        print(f"{'='*60}")
        print(f"   Discovery happens inside the backtest loop each day")
        print(f"   Position contexts update with latest probabilities")
        print(f"   Max positions: {args.max_positions}")
        print(f"{'='*60}")
        print(f"\n{Fore.CYAN}[BACKTEST] Starting backtest engine...{Style.RESET_ALL}\n")

        # Start with empty ticker list in autonomous mode
        # The engine will discover tickers from Polymarket events
        # Days with no discoveries will be skipped (no forced trading on SPY)
        initial_tickers = []  # Empty - discoveries will populate this
    else:
        initial_tickers = tickers

    engine = BacktestEngine(
        agent=run_hedge_fund,
        tickers=initial_tickers,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        initial_margin_requirement=args.margin_requirement,
        config=config,  # Pass TradingConfig instead of individual params
    )

    metrics = engine.run_backtest()
    values = engine.get_portfolio_values()

    # Terminal output
    if values:
        print(f"\n{Fore.WHITE}{Style.BRIGHT}ENGINE RUN COMPLETE{Style.RESET_ALL}")
        last_value = values[-1]["Portfolio Value"]
        start_value = values[0]["Portfolio Value"]
        total_return = (last_value / start_value - 1.0) * 100.0 if start_value else 0.0
        print(f"Total Return: {Fore.GREEN if total_return >= 0 else Fore.RED}{total_return:.2f}%{Style.RESET_ALL}")
    if metrics.get("sharpe_ratio") is not None:
        print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
    if metrics.get("sortino_ratio") is not None:
        print(f"Sortino: {metrics['sortino_ratio']:.2f}")
    if metrics.get("max_drawdown") is not None:
        md = abs(metrics["max_drawdown"]) if metrics["max_drawdown"] is not None else 0.0
        if metrics.get("max_drawdown_date"):
            print(f"Max DD: {md:.2f}% on {metrics['max_drawdown_date']}")
        else:
            print(f"Max DD: {md:.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
