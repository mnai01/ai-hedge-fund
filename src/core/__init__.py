"""
Core module for unified trading architecture.

This module provides shared components used by both backtest and live trading modes,
ensuring consistent behavior across all trading operations.

Key Components:
- TradingCycle: The unified daily trading cycle
- TradingConfig: Configuration for trading operations
- DailyCycleResult: Result of a single daily cycle
- DiscoveryManager: Polymarket event discovery and updates
- PositionTracker: Position context lifecycle management

Design Principles:
1. Mode-Agnostic: Core logic doesn't know if it's backtest or live
2. Reuse Existing Code: Wraps existing functions, doesn't duplicate
3. Clean Interfaces: Clear input/output contracts with type hints
4. No Global State: Returns results, doesn't mutate global state
"""

from src.core.trading_cycle import (
    TradingCycle,
    TradingConfig,
    DailyCycleResult,
)
from src.core.discovery_manager import DiscoveryManager
from src.core.position_tracker import PositionTracker

__all__ = [
    # Main trading cycle
    "TradingCycle",
    "TradingConfig",
    "DailyCycleResult",
    # Discovery management
    "DiscoveryManager",
    # Position tracking
    "PositionTracker",
]
