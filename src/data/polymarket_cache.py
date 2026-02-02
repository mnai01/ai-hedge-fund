"""SQLite-based persistent cache for Polymarket data.

This module provides a persistent cache that survives application restarts.
It stores:
- Events and their metadata
- Probability history snapshots
- LLM-generated stock mappings
- Trade decisions for backtesting

Follows patterns from src/data/cache.py but uses SQLite for persistence.
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from src.data.polymarket_models import (
    PolymarketEvent,
    PriceHistory,
    EventStockMapping,
    EventStockImpact,
    PolymarketTradeDecision,
    CachedEvent,
    CachedProbability,
    CachedStockMapping,
)


# Default database path
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "polymarket_cache.db"
)


class PolymarketCache:
    """SQLite-based persistent cache for Polymarket data.
    
    This cache stores data in a SQLite database for persistence across
    application restarts. It provides methods for storing and retrieving:
    - Events and markets
    - Price/probability history
    - Stock mappings (LLM-generated)
    - Trade decisions
    
    Example:
        >>> cache = PolymarketCache()
        >>> cache.set_event("event_123", event_data)
        >>> event = cache.get_event("event_123")
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the cache with a database path.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default path.
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Ensure the directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # Initialize the database schema
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    volume REAL,
                    liquidity REAL,
                    active INTEGER DEFAULT 1,
                    closed INTEGER DEFAULT 0,
                    raw_data TEXT,
                    first_seen TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            
            # Markets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS markets (
                    market_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    token_id TEXT,
                    raw_data TEXT,
                    last_updated TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            
            # Probability snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS probability_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    probability REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events(event_id),
                    FOREIGN KEY (market_id) REFERENCES markets(market_id)
                )
            """)
            
            # Create index for faster probability queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prob_event_time 
                ON probability_snapshots(event_id, timestamp)
            """)
            
            # Price history cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history_cache (
                    cache_key TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            
            # Stock mappings table (LLM-generated)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    reasoning TEXT,
                    sources TEXT,
                    model_used TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    FOREIGN KEY (event_id) REFERENCES events(event_id),
                    UNIQUE(event_id, ticker)
                )
            """)
            
            # Trade decisions table (for backtesting)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_title TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    probability_at_decision REAL NOT NULL,
                    probability_change REAL NOT NULL,
                    decision_timestamp TEXT NOT NULL,
                    reasoning TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    profit_loss REAL,
                    profit_loss_percent REAL,
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            
            # Generic cache table for API responses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
    
    # ==================== Event Methods ====================
    
    def get_event(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get a cached event by cache key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT raw_data FROM events WHERE event_id = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row and row["raw_data"]:
                return json.loads(row["raw_data"])
            return None
    
    def set_event(self, cache_key: str, data: Dict[str, Any]):
        """Store an event in the cache."""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO events 
                (event_id, title, description, category, volume, liquidity, 
                 active, closed, raw_data, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT first_seen FROM events WHERE event_id = ?), ?), ?)
            """, (
                cache_key,
                data.get("title", ""),
                data.get("description"),
                data.get("category"),
                data.get("volume"),
                data.get("liquidity"),
                1 if data.get("active", True) else 0,
                1 if data.get("closed", False) else 0,
                json.dumps(data),
                cache_key,
                now,
                now,
            ))
    
    def get_events(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached events list by cache key."""
        return self._get_api_cache(cache_key)
    
    def set_events(self, cache_key: str, data: List[Dict[str, Any]], ttl_hours: int = 1):
        """Store events list in cache."""
        self._set_api_cache(cache_key, data, ttl_hours)
    
    def get_all_events(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all cached events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if active_only:
                cursor.execute(
                    "SELECT raw_data FROM events WHERE active = 1 AND closed = 0"
                )
            else:
                cursor.execute("SELECT raw_data FROM events")
            
            rows = cursor.fetchall()
            return [json.loads(row["raw_data"]) for row in rows if row["raw_data"]]
    
    # ==================== Price History Methods ====================
    
    def get_price_history(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached price history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data, expires_at FROM price_history_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if expires_at > datetime.now():
                    return json.loads(row["data"])
                else:
                    # Expired, delete it
                    cursor.execute(
                        "DELETE FROM price_history_cache WHERE cache_key = ?",
                        (cache_key,)
                    )
            return None
    
    def set_price_history(self, cache_key: str, data: Dict[str, Any], ttl_hours: int = 1):
        """Store price history in cache."""
        now = datetime.now()
        expires_at = now + timedelta(hours=ttl_hours)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO price_history_cache 
                (cache_key, token_id, data, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                cache_key,
                data.get("token_id", ""),
                json.dumps(data),
                now.isoformat(),
                expires_at.isoformat(),
            ))
    
    # ==================== Probability Snapshot Methods ====================
    
    def record_probability(self, event_id: str, market_id: str, probability: float):
        """Record a probability snapshot for tracking changes over time."""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO probability_snapshots 
                (event_id, market_id, probability, timestamp)
                VALUES (?, ?, ?, ?)
            """, (event_id, market_id, probability, now))
    
    def get_probability_history(
        self,
        event_id: str,
        market_id: Optional[str] = None,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get probability history for an event."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if market_id:
                cursor.execute("""
                    SELECT probability, timestamp 
                    FROM probability_snapshots 
                    WHERE event_id = ? AND market_id = ? AND timestamp > ?
                    ORDER BY timestamp ASC
                """, (event_id, market_id, cutoff))
            else:
                cursor.execute("""
                    SELECT market_id, probability, timestamp 
                    FROM probability_snapshots 
                    WHERE event_id = ? AND timestamp > ?
                    ORDER BY timestamp ASC
                """, (event_id, cutoff))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_probability_change(
        self,
        event_id: str,
        market_id: str,
        hours: int = 24,
    ) -> Optional[float]:
        """Calculate probability change over a time period."""
        history = self.get_probability_history(event_id, market_id, hours)
        
        if len(history) < 2:
            return None
        
        return history[-1]["probability"] - history[0]["probability"]
    
    # ==================== Stock Mapping Methods ====================
    
    def get_stock_mapping(
        self,
        event_id: str,
        ticker: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get stock mapping for an event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if ticker:
                cursor.execute("""
                    SELECT * FROM stock_mappings 
                    WHERE event_id = ? AND ticker = ? 
                    AND (expires_at IS NULL OR expires_at > ?)
                """, (event_id, ticker.upper(), datetime.now().isoformat()))
                row = cursor.fetchone()
                return dict(row) if row else None
            else:
                cursor.execute("""
                    SELECT * FROM stock_mappings 
                    WHERE event_id = ? 
                    AND (expires_at IS NULL OR expires_at > ?)
                """, (event_id, datetime.now().isoformat()))
                rows = cursor.fetchall()
                return [dict(row) for row in rows] if rows else None
    
    def set_stock_mapping(
        self,
        event_id: str,
        mapping: EventStockImpact,
        model_used: Optional[str] = None,
        ttl_hours: int = 24,
    ):
        """Store a stock mapping."""
        now = datetime.now()
        expires_at = now + timedelta(hours=ttl_hours)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO stock_mappings 
                (event_id, ticker, direction, confidence, reasoning, sources, 
                 model_used, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                mapping.ticker.upper(),
                mapping.direction,
                mapping.confidence,
                mapping.reasoning,
                json.dumps(mapping.sources),
                model_used,
                now.isoformat(),
                expires_at.isoformat(),
            ))
    
    def set_event_stock_mapping(
        self,
        mapping: EventStockMapping,
        ttl_hours: int = 24,
    ):
        """Store a complete event-to-stocks mapping."""
        for impact in mapping.affected_stocks:
            self.set_stock_mapping(
                event_id=mapping.event_id,
                mapping=impact,
                model_used=mapping.model_used,
                ttl_hours=ttl_hours,
            )
    
    def get_mappings_for_ticker(self, ticker: str) -> List[Dict[str, Any]]:
        """Get all event mappings that affect a specific ticker."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sm.*, e.title as event_title, e.description as event_description
                FROM stock_mappings sm
                JOIN events e ON sm.event_id = e.event_id
                WHERE sm.ticker = ? 
                AND (sm.expires_at IS NULL OR sm.expires_at > ?)
                AND e.active = 1 AND e.closed = 0
            """, (ticker.upper(), datetime.now().isoformat()))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ==================== Trade Decision Methods ====================
    
    def record_trade_decision(self, decision: PolymarketTradeDecision):
        """Record a trade decision for backtesting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_decisions 
                (ticker, event_id, event_title, signal, confidence, 
                 probability_at_decision, probability_change, decision_timestamp,
                 reasoning, entry_price, exit_price, profit_loss, profit_loss_percent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.ticker,
                decision.event_id,
                decision.event_title,
                decision.signal,
                decision.confidence,
                decision.probability_at_decision,
                decision.probability_change,
                decision.decision_timestamp.isoformat(),
                decision.reasoning,
                decision.entry_price,
                decision.exit_price,
                decision.profit_loss,
                decision.profit_loss_percent,
            ))
    
    def update_trade_result(
        self,
        decision_id: int,
        exit_price: float,
        profit_loss: float,
        profit_loss_percent: float,
    ):
        """Update a trade decision with exit results."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trade_decisions 
                SET exit_price = ?, profit_loss = ?, profit_loss_percent = ?
                WHERE id = ?
            """, (exit_price, profit_loss, profit_loss_percent, decision_id))
    
    def get_trade_decisions(
        self,
        ticker: Optional[str] = None,
        event_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get trade decisions with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trade_decisions WHERE 1=1"
            params = []
            
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker.upper())
            
            if event_id:
                query += " AND event_id = ?"
                params.append(event_id)
            
            if start_date:
                query += " AND decision_timestamp >= ?"
                params.append(start_date.isoformat())
            
            if end_date:
                query += " AND decision_timestamp <= ?"
                params.append(end_date.isoformat())
            
            query += " ORDER BY decision_timestamp DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ==================== Generic API Cache Methods ====================
    
    def _get_api_cache(self, cache_key: str) -> Optional[Any]:
        """Get data from generic API cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data, expires_at FROM api_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                expires_at = datetime.fromisoformat(row["expires_at"])
                if expires_at > datetime.now():
                    return json.loads(row["data"])
                else:
                    cursor.execute(
                        "DELETE FROM api_cache WHERE cache_key = ?",
                        (cache_key,)
                    )
            return None
    
    def _set_api_cache(self, cache_key: str, data: Any, ttl_hours: int = 1):
        """Store data in generic API cache."""
        now = datetime.now()
        expires_at = now + timedelta(hours=ttl_hours)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO api_cache 
                (cache_key, data, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (
                cache_key,
                json.dumps(data),
                now.isoformat(),
                expires_at.isoformat(),
            ))
    
    # ==================== Maintenance Methods ====================
    
    def cleanup_expired(self):
        """Remove expired entries from all cache tables."""
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Clean up price history cache
            cursor.execute(
                "DELETE FROM price_history_cache WHERE expires_at < ?",
                (now,)
            )
            
            # Clean up stock mappings
            cursor.execute(
                "DELETE FROM stock_mappings WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,)
            )
            
            # Clean up API cache
            cursor.execute(
                "DELETE FROM api_cache WHERE expires_at < ?",
                (now,)
            )
    
    def cleanup_old_snapshots(self, days: int = 30):
        """Remove probability snapshots older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM probability_snapshots WHERE timestamp < ?",
                (cutoff,)
            )
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute("SELECT COUNT(*) as count FROM events")
            stats["events"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM markets")
            stats["markets"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM probability_snapshots")
            stats["probability_snapshots"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM stock_mappings")
            stats["stock_mappings"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM trade_decisions")
            stats["trade_decisions"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM api_cache")
            stats["api_cache_entries"] = cursor.fetchone()["count"]
            
            return stats
    
    def clear_all(self):
        """Clear all cached data. Use with caution!"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM probability_snapshots")
            cursor.execute("DELETE FROM stock_mappings")
            cursor.execute("DELETE FROM trade_decisions")
            cursor.execute("DELETE FROM price_history_cache")
            cursor.execute("DELETE FROM api_cache")
            cursor.execute("DELETE FROM markets")
            cursor.execute("DELETE FROM events")
    
    # ==================== Position Context Methods ====================
    
    def save_position_context(self, ticker: str, context: Dict[str, Any]) -> None:
        """Save position context for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            context: Position context dict
        """
        cache_key = f"position_context:{ticker}"
        self._set_api_cache(cache_key, context, ttl_hours=24 * 30)  # 30 day TTL
    
    def load_position_context(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Load position context for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Position context dict if exists
        """
        cache_key = f"position_context:{ticker}"
        return self._get_api_cache(cache_key)
    
    def load_all_position_contexts(self) -> Dict[str, Dict[str, Any]]:
        """Load all saved position contexts.
        
        Returns:
            Dict of ticker -> context
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT cache_key, data FROM api_cache
                WHERE cache_key LIKE 'position_context:%'
                AND (expires_at IS NULL OR expires_at > ?)
                """,
                (datetime.now().isoformat(),)
            )
            
            contexts = {}
            for row in cursor.fetchall():
                ticker = row[0].replace("position_context:", "")
                try:
                    contexts[ticker] = json.loads(row[1])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return contexts
    
    def delete_position_context(self, ticker: str) -> None:
        """Delete position context for a ticker.
        
        Args:
            ticker: Stock ticker symbol
        """
        cache_key = f"position_context:{ticker}"
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM api_cache WHERE cache_key = ?",
                (cache_key,)
            )
            conn.commit()


# Global cache instance
_polymarket_cache: Optional[PolymarketCache] = None


def get_polymarket_cache(db_path: Optional[str] = None) -> PolymarketCache:
    """
    Get the global Polymarket cache instance.
    
    Args:
        db_path: Optional custom database path. If provided on first call,
                 will be used for the global instance.
    
    Returns:
        PolymarketCache instance
    """
    global _polymarket_cache
    
    if _polymarket_cache is None:
        _polymarket_cache = PolymarketCache(db_path)
    
    return _polymarket_cache


def reset_polymarket_cache():
    """Reset the global cache instance. Useful for testing."""
    global _polymarket_cache
    _polymarket_cache = None
