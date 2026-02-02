# Testing Commands Reference

This document provides copy-paste ready commands for testing all AI Hedge Fund functionality.

## Prerequisites

1. **Environment Setup**: Ensure you have a `.env` file with your API keys:

    ```bash
    GOOGLE_API_KEY=your_google_api_key_here
    ```

2. **Install Dependencies**:
    ```bash
    poetry install
    ```

---

## Part 1: API Tests (No LLM Required)

These commands test the Polymarket API integration without using any LLM credits.

### 1.1 Test Polymarket API Connection

Fetch active events to verify API connectivity:

```bash
poetry run python -c "
from src.tools.polymarket_api import get_active_events
events = get_active_events(limit=5)
print(f'Found {len(events)} events')
for e in events:
    print(f'  - {e.title[:60]}... (vol: \${e.volume:,.0f})')
"
```

**Expected Output:**

```
Found 5 events
  - Will Donald Trump win the 2024 US Presidential Election?... (vol: $1,234,567)
  - Will Bitcoin reach $100k by end of 2024?... (vol: $567,890)
  ...
```

### 1.2 Test Event Scoring

Score and rank events by trading potential:

```bash
poetry run python -c "
from src.tools.polymarket_api import get_active_events
from src.tools.event_scorer import EventScorer
events = get_active_events(limit=20)
scorer = EventScorer()
ranked = scorer.rank_events(events, min_score=50, limit=10)
print(f'Top {len(ranked.events)} events:')
for e in ranked.events:
    print(f'  [{e.total_score:.1f}] {e.event_title[:50]}...')
"
```

**Expected Output:**

```
Top 10 events:
  [85.3] Will Donald Trump win the 2024 US Presidential...
  [78.2] Will Bitcoin reach $100k by end of 2024?...
  ...
```

### 1.3 Test Enhanced Signals

Get options-like signals for the top event:

```bash
poetry run python -c "
from src.tools.polymarket_api import get_active_events
from src.tools.event_scorer import EnhancedEventScorer
events = get_active_events(limit=5)
scorer = EnhancedEventScorer()
if events:
    summary = scorer.get_signal_summary(events[0].__dict__, {})
    print(f'Signals for: {events[0].title[:50]}...')
    print(f'  Unusual Volume: {summary.unusual_volume.strength:.2f} - {summary.unusual_volume.interpretation}')
    print(f'  Delta Movement: {summary.delta_movement.strength:.2f} - {summary.delta_movement.interpretation}')
    print(f'  Overall: {summary.overall_signal_strength:.2f}')
"
```

**Expected Output:**

```
Signals for: Will Donald Trump win the 2024 US Presidential...
  Unusual Volume: 0.75 - High volume indicates strong market interest
  Delta Movement: 0.45 - Moderate probability movement
  Overall: 0.60
```

### 1.4 Test Resolved Events

Fetch resolved events from the last 30 days:

```bash
poetry run python -c "
from src.tools.polymarket_api import get_resolved_events
from datetime import datetime, timedelta
end = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
events = get_resolved_events(start_date=start, end_date=end, min_volume=50000, limit=5)
print(f'Found {len(events)} resolved events:')
for e in events:
    print(f'  - {e.title[:50]}... (vol: \${e.volume:,.0f})')
"
```

**Expected Output:**

```
Found 5 resolved events:
  - Did the Fed raise rates in January 2024?... (vol: $234,567)
  - Did Bitcoin hit $50k in February 2024?... (vol: $123,456)
  ...
```

---

## Part 2: Polymarket CLI Backtests (Uses LLM)

These commands use the Polymarket CLI for backtesting event correlations with stock prices.

### 2.1 Historical Backtest - Simulate Running on a Past Date

The new historical backtest architecture simulates what would have happened if you ran the app on a specific historical date:

```bash
# Simulate running the app on Jan 1, 2024
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --max-events 5 \
  --min-volume 50000 \
  --model gemini-2.0-flash \
  --provider Google \
  --verbose
```

**Expected Output:**

```
============================================================
📊 Historical Backtest Simulation
============================================================
   Simulation Date: 2024-01-01
   Min Volume: $50,000
   Max Events: 5

🔍 Phase 1: Event Discovery
   Fetching events active on 2024-01-01...
   Found 47 events matching criteria

   Scoring events...
   Events with score > 50: 23

🤖 Phase 2: AI Stock Relevance Check
   Checking 23 events for US stock market relevance...

   ✅ HIGH: Will Donald Trump win the 2024 Presidential Election?
      └─ Sectors: energy, defense, financials, healthcare
   ✅ HIGH: Will the Fed cut rates in Q1 2024?
      └─ Sectors: financials, real estate, tech
   ⚠️ MEDIUM: Will Bitcoin reach $100k by end of 2024?
      └─ Sectors: crypto-related stocks (COIN, MSTR)
   ❌ LOW: Will TikTok be banned in the US?
   ❌ NONE: Will it snow in NYC on Christmas?

   Stock-relevant events: 3

📈 Phase 3: Stock Discovery & Backtest
   [Continues with stock discovery for each relevant event...]
```

### 2.2 Historical Backtest with Specific Tickers

Skip stock discovery and use your own tickers:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --tickers DJT XOM FSLR \
  --direction bullish \
  --verbose
```

### 2.3 Historical Backtest with Category Filter

Focus on specific event categories:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-06-01 \
  --category politics \
  --max-events 3 \
  --min-relevance high \
  --verbose
```

### 2.4 Long-Only Mode (No Short Selling)

Disable short positions to only trade bullish opportunities:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --no-short \
  --max-events 5 \
  --verbose
```

**What happens with `--no-short`:**

- Bearish (short) stock picks are filtered out before backtesting
- Only bullish (long) positions are analyzed and traded
- Useful for accounts that don't support short selling

### 2.5 Backtest Single Event by Slug

Test a specific event directly (skips event discovery):

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug "presidential-election-winner-2024" \
  --model gemini-2.0-flash \
  --provider Google \
  --verbose
```

### 2.6 Backtest Single Event with Specific Tickers

Provide your own tickers instead of AI discovery:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug "presidential-election-winner-2024" \
  --tickers DJT XOM FSLR \
  --direction bullish \
  --verbose
```

---

## Part 3: Main CLI Backtests (Interactive)

The main CLI uses interactive prompts for model and analyst selection.

### 3.1 Manual Mode with Specific Tickers

Run backtest with user-provided tickers:

```bash
poetry run python -m src.backtesting.cli \
  --tickers AAPL,MSFT,NVDA \
  --start-date 2024-01-01 \
  --end-date 2024-03-01 \
  --initial-capital 100000 \
  --analysts warren_buffett,ben_graham,technicals
```

**Note:** This will prompt you to select an LLM model interactively.

### 3.2 Autonomous Mode

Let AI discover tickers via Polymarket:

```bash
poetry run python -m src.backtesting.cli \
  --autonomous \
  --max-positions 3 \
  --start-date 2024-01-01 \
  --end-date 2024-02-01 \
  --initial-capital 50000
```

### 3.3 Long-Only Mode (No Short Selling)

Disable short selling in both Manual and Autonomous modes:

```bash
# Manual mode - long only
poetry run python -m src.backtesting.cli \
  --tickers AAPL,MSFT,NVDA \
  --no-short \
  --start-date 2024-01-01 \
  --end-date 2024-03-01

# Autonomous mode - long only
poetry run python -m src.backtesting.cli \
  --autonomous \
  --no-short \
  --max-positions 5 \
  --start-date 2024-01-01 \
  --end-date 2024-02-01
```

**What happens with `--no-short`:**

- Portfolio manager sets `max_short = 0` in allowed actions
- Agents cannot recommend short positions
- Only long (buy) positions are allowed

### 3.4 Autonomous Mode with Event Focus

Focus on a specific Polymarket event:

```bash
poetry run python -m src.backtesting.cli \
  --autonomous \
  --polymarket-event presidential-election-winner-2024 \
  --max-positions 5 \
  --start-date 2024-01-01 \
  --end-date 2024-03-01 \
  --initial-capital 100000
```

### 3.5 Use All Analysts

Run with all available analysts:

```bash
poetry run python -m src.backtesting.cli \
  --tickers AAPL,MSFT \
  --analysts-all \
  --start-date 2024-01-01 \
  --end-date 2024-02-01
```

---

## Part 4: Unit Tests

Run the test suite to verify all components work correctly.

### 4.1 Run All Tests

```bash
poetry run pytest
```

### 4.2 Run Specific Test Files

```bash
# Test Polymarket API
poetry run pytest tests/tools/test_polymarket_api.py -v

# Test Event Scorer
poetry run pytest tests/tools/test_event_scorer.py -v

# Test Integration
poetry run pytest tests/integration/ -v

# Test Phase 6 Validation (21 new tests)
poetry run pytest tests/agents/test_polymarket_discovery.py -v -k "Validation"
```

### 4.3 Run Tests with Coverage

```bash
poetry run pytest --cov=src --cov-report=html
```

---

## Available Analysts

For the `--analysts` flag, use these analyst names (comma-separated):

| Analyst Key          | Description                          |
| -------------------- | ------------------------------------ |
| `warren_buffett`     | Value investing legend               |
| `ben_graham`         | Father of value investing            |
| `charlie_munger`     | Rational thinker                     |
| `peter_lynch`        | 10-bagger investor                   |
| `cathie_wood`        | Growth/innovation focus              |
| `michael_burry`      | Contrarian investor                  |
| `bill_ackman`        | Activist investor                    |
| `technicals`         | Technical analysis                   |
| `fundamentals`       | Fundamental analysis                 |
| `sentiment`          | Sentiment analysis                   |
| `valuation`          | Valuation analysis                   |
| `growth`             | Growth analysis                      |
| `news_sentiment`     | News sentiment                       |
| `polymarket_analyst` | Polymarket signals (Autonomous Mode) |

---

## Troubleshooting

### API Rate Limiting

If you see `429 Too Many Requests`, the API will automatically retry with backoff. Wait a few minutes before running again.

### Missing API Keys

Ensure your `.env` file contains:

```
GOOGLE_API_KEY=your_key_here
```

### Import Errors

Make sure you're running from the project root directory and have installed dependencies:

```bash
poetry install
```
