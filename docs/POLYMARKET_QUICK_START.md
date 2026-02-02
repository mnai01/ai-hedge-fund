# Polymarket Quick Start Guide

Quick test commands for the Polymarket integration. All commands use `gemini-2.0-flash` model.

## Prerequisites

```bash
# Required: Set your Google API key
export GOOGLE_API_KEY=your_key_here

# Or add to .env file
echo "GOOGLE_API_KEY=your_key_here" >> .env
```

---

## Part 1: API Tests (No LLM Required)

Test the Polymarket API without using any LLM credits.

### Test API Connection

```bash
poetry run python -c "
from src.tools.polymarket_api import get_active_events
events = get_active_events(limit=5)
print(f'Found {len(events)} events')
for e in events:
    print(f'  - {e.title[:60]}... (vol: \${e.volume:,.0f})')
"
```

### Test Event Scoring

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

### Test Enhanced Signals

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

### Test Resolved Events

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

---

## Part 2: Polymarket CLI Backtests (Uses LLM)

### AI Stock Discovery

Let Gemini discover affected stocks for an event:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --model gemini-2.0-flash \
  --provider Google \
  --verbose
```

### Manual Tickers - Bullish

Test specific stocks with bullish thesis:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --tickers DJT GEO CXW \
  --direction bullish \
  --model gemini-2.0-flash \
  --provider Google
```

### Manual Tickers - Bearish

Test stocks that should decline:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --tickers FSLR ENPH TAN \
  --direction bearish \
  --model gemini-2.0-flash \
  --provider Google
```

### Historical Backtest (Recommended)

Simulate running the app on a specific historical date:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --min-volume 50000 \
  --max-events 5 \
  --model gemini-2.0-flash \
  --provider Google \
  --verbose
```

### Long-Only Mode (No Short Selling)

Disable short positions to only trade bullish opportunities:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --no-short \
  --max-events 5 \
  --verbose
```

### Save Results to JSON

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --model gemini-2.0-flash \
  --provider Google \
  --output results.json
```

---

## Part 3: Main CLI Backtests

The main CLI uses interactive prompts for model selection.

### Manual Mode

```bash
poetry run python -m src.backtesting.cli \
  --tickers AAPL,MSFT,NVDA \
  --start-date 2024-01-01 \
  --end-date 2024-03-01 \
  --initial-capital 100000 \
  --analysts warren_buffett,ben_graham,technicals
```

### Autonomous Mode

```bash
poetry run python -m src.backtesting.cli \
  --autonomous \
  --max-positions 3 \
  --start-date 2024-01-01 \
  --end-date 2024-02-01 \
  --initial-capital 50000
```

### Autonomous with Event Focus

```bash
poetry run python -m src.backtesting.cli \
  --autonomous \
  --polymarket-event presidential-election-winner-2024 \
  --max-positions 5 \
  --start-date 2024-10-01 \
  --end-date 2024-11-15
```

---

## CLI Reference

### Polymarket CLI Flags

| Flag                | Description                  | Default            |
| ------------------- | ---------------------------- | ------------------ |
| `--event-slug`      | Polymarket event slug        | -                  |
| `--start-date`      | Simulate running on date     | -                  |
| `--min-volume`      | Minimum event volume         | `50000`            |
| `--min-liquidity`   | Minimum event liquidity      | `10000`            |
| `--min-score`       | Minimum EventScorer score    | `50.0`             |
| `--min-relevance`   | Min stock relevance level    | `medium`           |
| `--category`        | Filter by category           | -                  |
| `--max-events`      | Max events to backtest       | `5`                |
| `--tickers`         | Space-separated tickers      | AI discovers       |
| `--direction`       | `bullish` or `bearish`       | `bullish`          |
| `--long-hold-days`  | Days to hold long positions  | `7`                |
| `--short-hold-days` | Days to hold short positions | `0`                |
| `--no-short`        | Disable short selling        | `false`            |
| `--model`           | LLM model name               | `gemini-2.0-flash` |
| `--provider`        | LLM provider                 | `Google`           |
| `--output`          | Save to JSON file            | -                  |
| `-v, --verbose`     | Detailed output              | `false`            |

### Main CLI Flags

| Flag                 | Description                | Default     |
| -------------------- | -------------------------- | ----------- |
| `--autonomous`       | Enable autonomous mode     | `false`     |
| `--tickers`          | Comma-separated tickers    | -           |
| `--max-positions`    | Max positions (autonomous) | `10`        |
| `--polymarket-event` | Focus on specific event    | -           |
| `--start-date`       | Start date (YYYY-MM-DD)    | 1 month ago |
| `--end-date`         | End date (YYYY-MM-DD)      | today       |
| `--initial-capital`  | Starting capital           | `100000`    |
| `--analysts`         | Comma-separated analysts   | interactive |
| `--analysts-all`     | Use all analysts           | `false`     |
| `--no-short`         | Disable short selling      | `false`     |

---

## Available Analysts

| Key              | Description               |
| ---------------- | ------------------------- |
| `warren_buffett` | Value investing           |
| `ben_graham`     | Father of value investing |
| `charlie_munger` | Rational thinking         |
| `peter_lynch`    | 10-bagger investor        |
| `cathie_wood`    | Growth/innovation         |
| `michael_burry`  | Contrarian                |
| `technicals`     | Technical analysis        |
| `fundamentals`   | Fundamental analysis      |
| `sentiment`      | Sentiment analysis        |
| `valuation`      | Valuation analysis        |

---

## Notes

- **Polymarket CLI**: Tickers are **space-separated**: `--tickers DJT TSLA`
- **Main CLI**: Tickers are **comma-separated**: `--tickers DJT,TSLA`
- When `--tickers` is provided, AI discovery is disabled
- Use `--start-date` to simulate running the app on a historical date
- Use `--no-short` to disable short selling (long positions only)
- See [TESTING_COMMANDS.md](./TESTING_COMMANDS.md) for comprehensive testing guide
