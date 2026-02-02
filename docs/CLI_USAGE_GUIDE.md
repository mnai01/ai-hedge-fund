# CLI Usage Guide - AI Hedge Fund with Polymarket Integration

This guide covers all CLI commands, their expected processes, outputs, and required environment variables.

## Table of Contents

1. [Environment Variables](#environment-variables)
2. [Trading Modes Overview](#trading-modes-overview)
3. [Main Backtesting CLI](#main-backtesting-cli)
4. [Polymarket CLI](#polymarket-cli)
5. [Live Trading CLI](#live-trading-cli)
6. [Expected Outputs](#expected-outputs)
7. [Position Lifecycle](#position-lifecycle)

---

## Environment Variables

Create a `.env` file in the project root with the following variables:

### Required for All Modes

```bash
# LLM Provider API Keys (at least one required)
OPENAI_API_KEY=sk-...                    # For OpenAI models (GPT-4, etc.)
ANTHROPIC_API_KEY=sk-ant-...             # For Claude models
GOOGLE_API_KEY=AIza...                   # For Gemini models (recommended)
GROQ_API_KEY=gsk_...                     # For Groq models (fast inference)

# Financial Data - Yahoo Finance is used by default (NO API KEY NEEDED)
# The system uses yfinance library which is free and requires no API key
```

### Optional

```bash
# Alternative Data Provider (if you want premium data)
FINANCIAL_DATASETS_API_KEY=your_key      # For Financial Datasets API (premium)

# Live Trading
ALPACA_API_KEY=your_key                  # For live trading
ALPACA_SECRET_KEY=your_secret            # For live trading
ALPACA_PAPER_TRADING=true                # Use paper trading (recommended)

# Ollama (for local LLM)
# No API key needed - just have Ollama running locally
```

### Environment Variables by Mode

| Mode       | Required Variables                                 |
| ---------- | -------------------------------------------------- |
| Manual     | One LLM key (OPENAI, ANTHROPIC, GOOGLE, or GROQ)   |
| Autonomous | `GOOGLE_API_KEY` (for stock mapping) + One LLM key |
| Live       | All above + `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`  |

**Note:** Yahoo Finance is used by default for all financial data. No API key is required for stock prices, financial metrics, or company information.

---

## Trading Modes Overview

The AI Hedge Fund operates in **two clear modes**:

### Manual Mode (Default)

User provides tickers, AI analyzes and trades what's given.

- **Use case**: You know which stocks you want to analyze
- **Control**: Full control over which tickers are analyzed
- **Cost**: Predictable LLM costs based on ticker count

### Autonomous Mode (`--autonomous`)

AI discovers tickers via Polymarket and manages everything.

- **Use case**: Let AI find opportunities from prediction markets
- **Control**: AI discovers and manages positions autonomously
- **Cost**: Controlled via `--max-positions` (default: 10)

### Key Principles

1. **Polymarket is HOW we found the stock, not WHY we keep it**
    - Once a position is opened, AI manages it based on all available data
    - The original Polymarket event is context, not a binding constraint

2. **AI manages positions until sold**
    - No automatic exits when events expire
    - Event expiry = historical context, AI keeps managing
    - AI decides when to exit based on full analysis

3. **Multiple event theses per ticker allowed**
    - A stock can be affected by multiple Polymarket events
    - Agents see all theses and make holistic decisions

4. **Position limits prevent cost explosion**
    - Default max 10 positions in Autonomous Mode
    - Configurable via `--max-positions`

---

## Main Backtesting CLI

**Command:** `poetry run python -m src.backtesting.cli`

### All Available Arguments

```bash
poetry run python -m src.backtesting.cli --help
```

```
usage: cli.py [-h] [--autonomous] [--tickers TICKERS] [--exclude EXCLUDE]
              [--max-positions MAX_POSITIONS] [--polymarket-event EVENT]
              [--end-date END_DATE] [--start-date START_DATE]
              [--initial-capital CAPITAL] [--margin-requirement MARGIN]
              [--analysts ANALYSTS] [--analysts-all] [--ollama]
              [--no-short]

options:
  --autonomous          Enable Autonomous Mode: AI discovers tickers via Polymarket
  --tickers TICKERS     Comma-separated tickers for Manual Mode
  --exclude EXCLUDE     Comma-separated tickers to exclude from AI management
  --max-positions N     Maximum positions in Autonomous Mode (default: 10)
  --polymarket-event    Specific Polymarket event slug to focus on
  --end-date            End date YYYY-MM-DD (default: today)
  --start-date          Start date YYYY-MM-DD (default: 1 month ago)
  --initial-capital     Initial capital (default: 100000)
  --margin-requirement  Margin requirement (default: 0.0)
  --analysts            Comma-separated analyst names
  --analysts-all        Use all analysts
  --ollama              Use Ollama for local LLM
  --no-short            Disable short selling (long positions only)
```

---

### Manual Mode (Default)

User provides tickers, AI analyzes and trades what's given.

**Required ENV:**

- One LLM API key (OPENAI, ANTHROPIC, GOOGLE, or GROQ)
- **No financial data API key needed** - Yahoo Finance is used by default

**Command:**

```bash
# Interactive mode (prompts for analysts, model)
poetry run python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL

# Non-interactive with all parameters
poetry run python -m src.backtesting.cli \
  --tickers AAPL,MSFT,GOOGL \
  --start-date 2024-01-01 \
  --end-date 2024-06-30 \
  --initial-capital 100000 \
  --analysts warren_buffett_agent,peter_lynch_agent,technicals_agent
```

**Expected Process:**

1. Parse arguments / Interactive prompts
2. Select LLM model
3. For each day in date range:
    - Fetch financial data for each ticker (via Yahoo Finance)
    - Run selected analyst agents
    - Aggregate signals
    - Execute trades via portfolio manager
4. Calculate performance metrics
5. Display results

**Expected Output:**

```
============================================================
Operating Mode: Manual
  User provides tickers, AI analyzes and trades what's given
  Tickers: AAPL, MSFT, GOOGL
============================================================

Selected analysts: Warren Buffett, Peter Lynch, Technicals

Selected Google model: gemini-2.0-flash

========== warren_buffett_agent ==========
{
  "AAPL": {
    "signal": "bullish",
    "confidence": 75,
    "reasoning": "..."
  }
}
==========================================

... (more agent outputs)

ENGINE RUN COMPLETE
Total Return: 5.23%
Sharpe: 1.45
Max DD: 3.20%
```

---

### Autonomous Mode

AI discovers tickers via Polymarket and manages all positions.

**Required ENV:**

- `GOOGLE_API_KEY` (for LLM stock mapping)
- **No financial data API key needed** - Yahoo Finance is used by default

**Command - Basic:**

```bash
# Let AI discover and manage up to 10 positions
poetry run python -m src.backtesting.cli --autonomous
```

**Command - With Position Limit:**

```bash
# Limit to 5 positions to control costs
poetry run python -m src.backtesting.cli --autonomous --max-positions 5
```

**Command - With Exclusions:**

```bash
# Exclude certain tickers from AI management
poetry run python -m src.backtesting.cli --autonomous --exclude AAPL,TSLA
```

**Command - Specific Event Focus:**

```bash
# Focus on a specific Polymarket event
poetry run python -m src.backtesting.cli \
  --autonomous \
  --polymarket-event presidential-election-winner-2024 \
  --start-date 2024-10-01 \
  --end-date 2024-11-15 \
  --analysts-all
```

**Expected Process:**

1. Parse arguments
2. **Discovery Phase:**
    - Fetch high-conviction events from Polymarket (60-85% probability)
    - Use LLM to map events to affected stocks
    - Create PositionContext with thesis for each ticker
    - Respect `--max-positions` limit
    - Skip any `--exclude` tickers
3. For each day in date range:
    - Update probability snapshots
    - Check for event resolution (mark as historical context)
    - Run analyst agents (with Polymarket context)
    - Aggregate signals
    - Execute trades
4. Calculate performance metrics
5. Display results

**Expected Output:**

```
============================================================
Operating Mode: Autonomous
  AI discovers tickers via Polymarket and manages all positions
  Max positions: 10
  Excluded tickers: AAPL, TSLA
  Event focus: presidential-election-winner-2024
============================================================

Discovering tickers from Polymarket events...
Found 3 high-conviction events:
  - "Will Trump win 2024 election?" (72% probability)
  - "Will Fed cut rates in December?" (68% probability)
  - "Will Bitcoin reach $100k by year end?" (61% probability)

Mapping events to stocks...
Discovered tickers (respecting max 10 positions):
  - DJT (Trump win → bullish, confidence: 95%)
  - JPM (Fed rate cut → bullish, confidence: 70%)
  - MSTR (Bitcoin ATH → bullish, confidence: 80%)

Note: TSLA excluded per --exclude flag

Selected analysts: All (15 analysts)

========== polymarket_discovery_agent ==========
{
  "discovered_tickers": [
    {"ticker": "DJT", "context": {...}},
    {"ticker": "JPM", "context": {...}}
  ],
  "status_changes": {}
}
================================================

... (more agent outputs with Polymarket context)

ENGINE RUN COMPLETE
Total Return: 12.46%
Sharpe: 1.82
Max DD: 5.30%
```

---

## Polymarket Research CLI (Standalone Tool)

**Command:** `poetry run python -m src.backtesting.polymarket_cli`

> **⚠️ Important:** This is a **standalone research tool**, completely separate from the main hedge fund CLI. It is NOT part of the Manual/Autonomous mode system. Use this tool to:
>
> - **Historical Backtest:** Simulate running the app on a past date
> - Test if correlations exist between Polymarket events and stocks
> - Run simple backtests to validate hypotheses before using the main system
> - Research which stocks might be affected by prediction market events
> - **AI Stock Relevance Check:** Pre-filter events by stock market impact

### Architecture Overview

The new historical backtest architecture simulates live mode at a historical point in time:

```
--start-date 2024-01-01
        ↓
1. Fetch ALL events (active + closed) from API
        ↓
2. Filter: Events that were ACTIVE on start_date
   (creationDate <= start_date AND (closedTime > start_date OR closedTime is null))
        ↓
3. Algorithmic Scoring (EventScorer)
        ↓
4. 🆕 AI Stock Relevance Check - "Will this event impact US stocks?"
        ↓
5. Stock Discovery (LLM discovery)
        ↓
6. News Validation
        ↓
7. Backtest
```

### Usage

```bash
poetry run python -m src.backtesting.polymarket_cli --help
```

```
usage: polymarket_cli.py [-h] (--event-slug EVENT_SLUG | --start-date START_DATE)
                         [--min-volume MIN_VOLUME] [--min-liquidity MIN_LIQUIDITY]
                         [--category CATEGORY] [--max-events MAX_EVENTS]
                         [--min-score MIN_SCORE] [--min-relevance {high,medium,low}]
                         [--tickers TICKERS ...] [--direction {bullish,bearish}]
                         [--long-hold-days DAYS] [--short-hold-days DAYS]
                         [--min-probability MIN_PROBABILITY] [--no-short]
                         [--verbose] [--model MODEL] [--provider PROVIDER]
                         [--output OUTPUT]

options:
  --event-slug EVENT_SLUG   The Polymarket event slug (from URL)
  --start-date START_DATE   Simulate running the app on this date (ISO format: 2024-01-01)
  --min-volume MIN_VOLUME   Minimum event volume (default: 50000)
  --min-liquidity MIN_LIQUIDITY  Minimum event liquidity (default: 10000)
  --category CATEGORY       Filter by category (e.g., 'politics', 'crypto')
  --max-events MAX_EVENTS   Maximum events to analyze (default: 5)
  --min-score MIN_SCORE     Minimum EventScorer score (default: 50.0)
  --min-relevance           Minimum stock relevance level (default: medium)
  --tickers TICKERS ...     Specific stock tickers to analyze (space-separated)
  --direction               Direction for manual tickers: bullish (long) or bearish (short)
  --long-hold-days          Days to hold long positions after event (default: 7)
  --short-hold-days         Days to hold short positions after event (default: 0)
  --min-probability         Minimum probability threshold (default: 0.70)
  --no-short                Disable short selling (long positions only)
  --verbose, -v             Show detailed output
  --model MODEL             LLM model name (default: gemini-2.0-flash)
  --provider PROVIDER       LLM provider (default: Google)
  --output OUTPUT           Save results to JSON file
```

> **📘 Quick Start:** See [POLYMARKET_QUICK_START.md](POLYMARKET_QUICK_START.md) for ready-to-run test commands.

---

### Historical Backtest (NEW - Recommended)

Simulate running the app on a specific historical date:

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

**What happens:**

1. **Phase 1 - Event Discovery:** Fetches events that were ACTIVE on the start date
2. **Phase 1b - Scoring:** Ranks events by trading potential using EventScorer
3. **Phase 2 - AI Relevance Check:** Uses LLM to filter events by US stock market relevance
4. **Phase 3 - Stock Discovery & Backtest:** For each relevant event:
    - Discovers affected stocks (LLM)
    - Finds entry date (when prob crosses threshold)
    - Validates stocks with historical news
    - Runs backtest simulation
5. **Summary:** Aggregates results across all events

**Example Output:**

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
      └─ Limited direct stock impact
   ❌ NONE: Will it snow in NYC on Christmas?
      └─ No stock market relevance

   Stock-relevant events: 3

📈 Phase 3: Stock Discovery & Backtest
   [Continues with stock discovery for each relevant event...]

============================================================
📋 Historical Backtest Summary
============================================================

Simulation Date: 2024-01-01
Events Analyzed: 3
Stocks Traded: 8

Trading Performance:
   Win rate: 62.5%
   Total return: +18.45%
   Avg return per trade: +2.31%
```

### Historical Backtest with Specific Tickers

Skip stock discovery and use your own tickers:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --tickers DJT XOM FSLR \
  --direction bullish \
  --verbose
```

### Historical Backtest with Category Filter

Focus on specific event categories:

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-06-01 \
  --category politics \
  --max-events 3 \
  --min-relevance high \
  --verbose
```

---

### Single Event Backtest

Test a specific event directly (skips event discovery):

```bash
# AI discovers affected stocks and runs correlation analysis
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024
```

**What happens:**

1. Fetches the Polymarket event details and probability history
2. Uses LLM to discover which stocks might be affected (e.g., DJT, TSLA, LMT)
3. Fetches stock price history for discovered stocks
4. Calculates correlation between probability changes and stock price changes
5. Reports results showing if the correlation was profitable

### With Manual Tickers (No LLM)

When you provide `--tickers`, LLM stock discovery is automatically disabled:

```bash
# You specify which stocks to analyze (space-separated, not comma-separated)
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --tickers DJT TSLA \
  --direction bullish

# Test bearish thesis (e.g., solar stocks hurt by Trump win)
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --tickers FSLR ENPH TAN \
  --direction bearish
```

**When to use manual tickers:**

- You already know which stocks correlate with an event
- You want to test a specific hypothesis (e.g., "Does DJT move with Trump's win probability?")
- You want to save LLM API costs during research
- You're comparing multiple stocks against the same event

### Hold Period Configuration

Control how long positions are held after event resolution:

```bash
# Long positions hold 7 days (capture post-event momentum)
# Short positions exit immediately (avoid squeeze risk)
poetry run python -m src.backtesting.polymarket_cli \
  --event-slug presidential-election-winner-2024 \
  --tickers DJT GEO \
  --direction bullish \
  --long-hold-days 7 \
  --short-hold-days 0
```

| Position        | Default Hold | Rationale                           |
| --------------- | ------------ | ----------------------------------- |
| Long (bullish)  | 7 days       | Capture post-event rally momentum   |
| Short (bearish) | 0 days       | Exit at resolution to avoid squeeze |

### Save Results

```bash
poetry run python -m src.backtesting.polymarket_cli \
  --start-date 2024-01-01 \
  --output results.json
```

> **Note:** When `--tickers` is provided, LLM stock discovery is automatically disabled. This is separate from the Manual/Autonomous modes in the main hedge fund CLI.

---

## Live Trading CLI

**Command:** `poetry run python -m src.trader`

**Required ENV:**

- One LLM API key
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ALPACA_PAPER_TRADING=true` (recommended)

```bash
# Manual Mode with live trading
poetry run python -m src.trader --tickers AAPL,MSFT

# Autonomous Mode with live trading
poetry run python -m src.trader --autonomous --max-positions 5
```

**Note:** Live trading follows the same mode logic but executes real trades through Alpaca.

---

## Expected Outputs

### Successful Run

```
============================================================
Operating Mode: [Manual/Autonomous]
  [Mode description]
  [Mode-specific details]
============================================================

[Agent outputs with signals]

ENGINE RUN COMPLETE
Total Return: X.XX%
Sharpe: X.XX
Sortino: X.XX
Max DD: X.XX%
```

### Common Errors

**Missing LLM API Key:**

```
Error: No LLM API key found in environment
Please set at least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY
```

**Manual Mode Without Tickers:**

```
Error: Manual Mode requires --tickers argument

Usage examples:
  Manual Mode:     poetry run python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL
  Autonomous Mode: poetry run python -m src.backtesting.cli --autonomous
```

**Invalid Event Slug:**

```
Error: Event 'invalid-event-slug' not found on Polymarket
Available events can be found at: https://polymarket.com
```

**Max Positions Warning:**

```
Warning: --max-positions > 20 may cause high LLM costs. Consider using a lower value.
```

---

## Position Lifecycle

Understanding how positions are managed in the AI Hedge Fund:

### 1. Discovery (Autonomous Mode Only)

```
Polymarket Event → LLM Stock Mapping → PositionContext Created
```

- AI finds high-conviction events (60-85% probability)
- Maps events to affected stocks with thesis
- Creates PositionContext with event details

### 2. Entry

```
Analyst Signals → Portfolio Manager → Position Opened
```

- All analysts analyze the ticker (with Polymarket context if available)
- Portfolio manager aggregates signals
- Position opened if consensus is bullish/bearish

### 3. Ongoing Management

```
Daily Analysis → Signal Updates → Hold/Adjust/Exit Decision
```

- AI continues analyzing based on ALL available data
- Polymarket probability is ONE input, not the only input
- Fundamentals, technicals, sentiment all factor in

### 4. Event Resolution

```
Event Resolves → Marked as Historical Context → AI Keeps Managing
```

- When a Polymarket event resolves, it becomes historical context
- **No automatic exit** - AI decides based on full analysis
- The original thesis is context, not a binding constraint

### 5. Exit

```
AI Decision → Portfolio Manager → Position Closed
```

- AI decides when to exit based on:
    - Changed fundamentals
    - Technical signals
    - Risk management
    - New information
- Exit is AI's decision, not tied to event lifecycle

### Multiple Events Per Ticker

A single ticker can have multiple event theses:

```
TSLA:
  - Event 1: "Trump wins 2024" → bullish (resolved YES)
  - Event 2: "Fed cuts rates" → bullish (active, 68%)
  - Event 3: "EV tax credits extended" → bullish (active, 55%)
```

Agents see ALL theses and make holistic decisions.

---

## Quick Reference

| Mode       | Command                                                  | Key Flags                                                          |
| ---------- | -------------------------------------------------------- | ------------------------------------------------------------------ |
| Manual     | `poetry run python -m src.backtesting.cli --tickers ...` | `--tickers` (required), `--no-short`                               |
| Autonomous | `poetry run python -m src.backtesting.cli --autonomous`  | `--max-positions`, `--exclude`, `--polymarket-event`, `--no-short` |

| Flag                 | Mode       | Description                           |
| -------------------- | ---------- | ------------------------------------- |
| `--tickers`          | Manual     | Comma-separated tickers to analyze    |
| `--autonomous`       | Autonomous | Enable AI-driven ticker discovery     |
| `--max-positions`    | Autonomous | Limit positions (default: 10)         |
| `--exclude`          | Autonomous | Tickers to exclude from AI management |
| `--polymarket-event` | Both       | Focus on specific event               |
| `--no-short`         | Both       | Disable short selling (long only)     |

| ENV Variable        | Required For | Purpose                |
| ------------------- | ------------ | ---------------------- |
| `GOOGLE_API_KEY`    | Autonomous   | LLM stock mapping      |
| `OPENAI_API_KEY`    | Optional     | Alternative LLM        |
| `ANTHROPIC_API_KEY` | Optional     | Alternative LLM        |
| `GROQ_API_KEY`      | Optional     | Alternative LLM (fast) |
| `ALPACA_API_KEY`    | Live trading | Broker connection      |

**Note:** No financial data API key is required. Yahoo Finance (yfinance) is used by default and is free.
