# AI Hedge Fund - Agent Flow Architecture

This document provides a high-level overview of how the AI Hedge Fund agent system works, including the agent flow, automatic mode looping, and Polymarket integration.

## Table of Contents

1. [System Overview](#system-overview)
2. [Agent Architecture](#agent-architecture)
3. [Trading Modes](#trading-modes)
4. [Agent Flow Diagrams](#agent-flow-diagrams)
5. [Automatic Mode Looping](#automatic-mode-looping)
6. [Polymarket Event Discovery](#polymarket-event-discovery)

---

## System Overview

The AI Hedge Fund is a multi-agent system that uses LLMs to analyze stocks and make trading decisions. The system can operate in two primary modes:

- **Manual Mode**: User provides tickers, AI analyzes them
- **Autonomous Mode**: AI discovers tickers from Polymarket events

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI HEDGE FUND SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                    ┌─────────────────────────────────┐ │
│  │   Manual Mode   │                    │      Autonomous Mode            │ │
│  │  (--tickers)    │                    │      (--autonomous)             │ │
│  └────────┬────────┘                    └────────────────┬────────────────┘ │
│           │                                              │                  │
│           │                             ┌────────────────▼────────────────┐ │
│           │                             │  POLYMARKET DISCOVERY LAYER    │ │
│           │                             │  (Runs BEFORE analyst agents)  │ │
│           │                             │                                │ │
│           │                             │  ┌────────────────────────────┐│ │
│           │                             │  │ 1. DISCOVERY MODE          ││ │
│           │                             │  │    Find new events → stocks││ │
│           │                             │  │                            ││ │
│           │                             │  │ 2. UPDATE MODE             ││ │
│           │                             │  │    Update existing context ││ │
│           │                             │  │    Check event resolution  ││ │
│           │                             │  └────────────────────────────┘│ │
│           │                             └────────────────┬────────────────┘ │
│           │                                              │                  │
│           │              ┌───────────────────────────────┘                  │
│           │              │ (Discovered tickers + context)                   │
│           ▼              ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       AGENT PIPELINE                                │   │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────┐   │   │
│  │  │ Analyst 1 │ │ Analyst 2 │ │ Analyst N │ │ Portfolio Manager │   │   │
│  │  │ (Buffett) │ │  (Lynch)  │ │ Technicals│ │                   │   │   │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────────┬─────────┘   │   │
│  │        └─────────────┴─────────────┴─────────────────┘             │   │
│  │                                                                     │   │
│  │  NOTE: In Autonomous Mode, agents receive PositionContext with     │   │
│  │        Polymarket data. In Manual Mode, no Polymarket context.     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       EXECUTION LAYER                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │   │
│  │  │  Backtest   │  │    Paper    │  │         Live                │ │   │
│  │  │   Engine    │  │   Trading   │  │        Trading              │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Polymarket CLI (Standalone)                      │   │
│  │  Separate research tool - NOT part of the main trading system      │   │
│  │  Used for: Testing correlations, backtesting resolved events       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Architecture

### Available Analyst Agents

The system includes multiple analyst agents, each with a unique investment philosophy:

| Agent                 | Philosophy                 | Focus                       |
| --------------------- | -------------------------- | --------------------------- |
| Warren Buffett        | Value investing            | Moats, management quality   |
| Peter Lynch           | Growth at reasonable price | PEG ratio, growth potential |
| Charlie Munger        | Quality businesses         | Competitive advantages      |
| Ben Graham            | Deep value                 | Margin of safety            |
| Bill Ackman           | Activist investing         | Catalysts, restructuring    |
| Cathie Wood           | Disruptive innovation      | Technology, growth          |
| Michael Burry         | Contrarian value           | Asymmetric opportunities    |
| Stanley Druckenmiller | Macro trading              | Economic trends             |
| Technicals Agent      | Technical analysis         | Price patterns, momentum    |
| Fundamentals Agent    | Financial analysis         | Ratios, earnings            |
| Sentiment Agent       | News sentiment             | Market mood                 |
| Polymarket Analyst    | Prediction markets         | Event probabilities         |

### Agent Signal Flow - Manual Mode vs Discovery Mode

The data collection and agent flow differs based on whether `--discovery` is enabled:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA COLLECTION COMPARISON                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MANUAL MODE (--tickers AAPL,MSFT)          DISCOVERY MODE (--autonomous)   │
│  ════════════════════════════════           ═══════════════════════════════ │
│                                                                             │
│  Data Collected:                            Data Collected:                 │
│  ┌─────────────────────────┐                ┌─────────────────────────────┐ │
│  │ • Price History         │                │ • Price History             │ │
│  │ • Financial Metrics     │                │ • Financial Metrics         │ │
│  │ • News & Sentiment      │                │ • News & Sentiment          │ │
│  │ • Insider Trades        │                │ • Insider Trades            │ │
│  │                         │                │                             │ │
│  │ (No Polymarket data)    │                │ ADDITIONAL POLYMARKET DATA: │ │
│  │                         │                │ ┌─────────────────────────┐ │ │
│  └─────────────────────────┘                │ │ • Event Title & ID      │ │ │
│                                             │ │ • Current Probability   │ │ │
│                                             │ │ • Probability History   │ │ │
│                                             │ │ • 24hr/7d Prob Changes  │ │ │
│                                             │ │ • Event Category        │ │ │
│                                             │ │ • Event Score           │ │ │
│                                             │ │ • Investment Thesis     │ │ │
│                                             │ │ • Impact Direction      │ │ │
│                                             │ │ • Confidence Level      │ │ │
│                                             │ │ • Event State           │ │ │
│                                             │ │   (active/resolved)     │ │ │
│                                             │ └─────────────────────────┘ │ │
│                                             └─────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Happens When --discovery is Enabled

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISCOVERY MODE WORKFLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: POLYMARKET DISCOVERY AGENT RUNS FIRST                             │
│  ═══════════════════════════════════════════════                           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                POLYMARKET DISCOVERY AGENT                           │   │
│  │                                                                     │   │
│  │  Input: None (fetches from Polymarket API)                         │   │
│  │                                                                     │   │
│  │  Process:                                                          │   │
│  │  1. Fetch active events from Polymarket API                        │   │
│  │  2. Score events with EventScorer (volume, liquidity, timing)      │   │
│  │  3. Filter by probability range (60-85% = high conviction)         │   │
│  │  4. Deduplicate against EventHistory                               │   │
│  │  5. LLM maps events → affected stocks                              │   │
│  │                                                                     │   │
│  │  NOTE: LLM receives EVENT DATA ONLY during discovery:              │   │
│  │  • Event title, description, category                              │   │
│  │  • Current probability                                             │   │
│  │  • Portfolio context (existing positions to avoid duplicates)      │   │
│  │                                                                     │   │
│  │  LLM does NOT receive financial data (prices, P/E, etc.)           │   │
│  │  Financial data is fetched AFTER discovery for analyst agents.     │   │
│  │                                                                     │   │
│  │  Output: List of discovered tickers with PositionContext           │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │  {                                                          │   │   │
│  │  │    "ticker": "JPM",                                         │   │   │
│  │  │    "context": {                                             │   │   │
│  │  │      "event_id": "fed-rate-cut-march-2025",                │   │   │
│  │  │      "event_title": "Will Fed cut rates in March?",        │   │   │
│  │  │      "thesis": "Rate cuts benefit banks via lending",      │   │   │
│  │  │      "impact_direction": "bullish",                        │   │   │
│  │  │      "confidence": 85,                                     │   │   │
│  │  │      "probability": {                                      │   │   │
│  │  │        "current": 0.72,                                    │   │   │
│  │  │        "change_24h": +0.03,                                │   │   │
│  │  │        "change_7d": +0.08                                  │   │   │
│  │  │      },                                                    │   │   │
│  │  │      "event_score": 78.5                                   │   │   │
│  │  │    }                                                       │   │   │
│  │  │  }                                                         │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 2: DISCOVERED TICKERS ENTER STANDARD PIPELINE                        │
│  ══════════════════════════════════════════════════                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Discovered tickers (JPM, XLF, etc.) + Any manual tickers           │   │
│  │  are now analyzed by ALL selected analyst agents                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Polymarket Context Flows to Analyst Agents

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POLYMARKET CONTEXT IN AGENT DECISIONS                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  When --discovery is enabled, each analyst agent receives EXTRA context:   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    AGENT INPUT (Discovery Mode)                     │   │
│  │                                                                     │   │
│  │  Standard Data:                    Polymarket Context:              │   │
│  │  ┌─────────────────────────┐      ┌─────────────────────────────┐  │   │
│  │  │ • Ticker: JPM           │      │ • Event: "Fed rate cut"     │  │   │
│  │  │ • Price: $185.50        │      │ • Probability: 72%          │  │   │
│  │  │ • P/E: 12.3             │      │ • 24h Change: +3%           │  │   │
│  │  │ • Revenue Growth: 8%    │      │ • Thesis: "Rate cuts help   │  │   │
│  │  │ • News Sentiment: 0.6   │      │   banks via lending"        │  │   │
│  │  │ • RSI: 55               │      │ • Direction: Bullish        │  │   │
│  │  │ • 52-week High: $200    │      │ • Confidence: 85%           │  │   │
│  │  └─────────────────────────┘      │ • Event Score: 78.5         │  │   │
│  │                                   └─────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    AGENT DECISION PROCESS                           │   │
│  │                                                                     │   │
│  │  Warren Buffett Agent:                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ "JPM has strong fundamentals (P/E 12.3, good ROE).          │   │   │
│  │  │  The Polymarket event shows 72% probability of rate cut,    │   │   │
│  │  │  which would benefit JPM's lending margins.                 │   │   │
│  │  │                                                             │   │   │
│  │  │  Signal: BULLISH                                            │   │   │
│  │  │  Confidence: 80%                                            │   │   │
│  │  │  Reasoning: Strong bank + favorable rate environment"       │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │  Technicals Agent:                                                 │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ "RSI at 55 is neutral. Price below 52-week high.            │   │   │
│  │  │  Polymarket probability rising (+3% in 24h) suggests        │   │   │
│  │  │  potential catalyst approaching.                            │   │   │
│  │  │                                                             │   │   │
│  │  │  Signal: BULLISH                                            │   │   │
│  │  │  Confidence: 65%                                            │   │   │
│  │  │  Reasoning: Neutral technicals + positive catalyst"         │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### PositionContext Data Structure

This is the additional data stored and passed to agents when --discovery is enabled:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSITION CONTEXT (Stored Per Ticker)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PositionContext {                                                         │
│    // Event Identification                                                 │
│    event_id: "fed-rate-cut-march-2025"                                    │
│    event_title: "Will the Fed cut rates in March 2025?"                   │
│    event_type: BINARY | SEQUENTIAL | MULTI_OUTCOME                        │
│    event_state: ACTIVE | RESOLVED_YES | RESOLVED_NO | EXPIRED             │
│                                                                            │
│    // Investment Thesis (from LLM mapping)                                 │
│    thesis: "Rate cuts benefit banks through increased lending activity"   │
│    thesis_type: SHORT_TERM | LONG_TERM                                    │
│    ticker: "JPM"                                                          │
│    impact_direction: "bullish" | "bearish"                                │
│    confidence: 85  // 0-100                                               │
│                                                                            │
│    // Probability Tracking                                                 │
│    probability: {                                                         │
│      current: 0.72                                                        │
│      change_24h: +0.03                                                    │
│      change_7d: +0.08                                                     │
│      at_entry: 0.65  // When position was opened                          │
│      since_entry: +0.07                                                   │
│    }                                                                       │
│                                                                            │
│    // Position Tracking                                                    │
│    entry_date: "2025-01-15"                                               │
│    entry_price: 180.25                                                    │
│    last_updated: "2025-01-20T10:30:00Z"                                   │
│                                                                            │
│    // Event Scoring (from EventScorer)                                     │
│    event_score: 78.5                                                      │
│  }                                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Complete Agent Signal Flow (Both Modes)

```
                    ┌─────────────────────────────────────┐
                    │         TICKER INPUT                │
                    │   (Manual or Discovered)            │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │    DATA COLLECTION / UPDATE         │
                    │                                     │
                    │  Standard Data (Always):            │
                    │  • Price History (Yahoo Finance)    │
                    │  • Financial Metrics                │
                    │  • News & Sentiment                 │
                    │  • Insider Trades                   │
                    │                                     │
                    │  IF --autonomous enabled:           │
                    │  • PositionContext (see above)      │
                    │  • Updated probability snapshots    │
                    │  • Event state (active/resolved)    │
                    └─────────────────┬───────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  Warren Buffett │       │   Peter Lynch   │       │   Technicals    │
│     Agent       │       │     Agent       │       │     Agent       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ Sees: Financials│       │ Sees: Growth    │       │ Sees: Charts    │
│ + Polymarket    │       │ + Polymarket    │       │ + Polymarket    │
│   context       │       │   context       │       │   context       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ Signal: BULLISH │       │ Signal: BULLISH │       │ Signal: NEUTRAL │
│ Confidence: 80% │       │ Confidence: 75% │       │ Confidence: 60% │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         └─────────────────────────┼─────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     SIGNAL AGGREGATION      │
                    │  • Weighted average         │
                    │  • Confidence scoring       │
                    │  • Consensus building       │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     PORTFOLIO MANAGER       │
                    │  • Position sizing          │
                    │  • Risk management          │
                    │  • Trade execution          │
                    │                             │
                    │  IF --autonomous enabled:   │
                    │  • Updates PositionContext  │
                    │  • Tracks event resolution  │
                    └─────────────────────────────┘
```

---

## Trading Modes

### Manual Mode

User provides specific tickers for analysis:

```bash
poetry run python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL
```

**Flow:**

1. User specifies tickers
2. System fetches data for each ticker
3. Selected analysts analyze each ticker
4. Signals are aggregated
5. Portfolio manager executes trades

### Autonomous Mode

AI discovers tickers from Polymarket events:

```bash
poetry run python -m src.backtesting.cli --autonomous --max-positions 10
```

**Flow:**

1. Polymarket Discovery Agent fetches high-conviction events
2. Events are scored with EventScorer (volume, liquidity, time horizon)
3. LLM maps events to affected stocks
4. Discovered tickers enter the standard analysis pipeline
5. Position context tracks the original thesis

---

## Polymarket Discovery Layer (Autonomous Mode Only)

The Polymarket Discovery Layer runs **BEFORE** the analyst agents in Autonomous Mode. It has two sub-modes that run sequentially:

### Discovery Layer Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POLYMARKET DISCOVERY LAYER                               │
│                    (Runs BEFORE Analyst Agents)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MODE 1: DISCOVERY (Find NEW Events)                                │   │
│  │  ════════════════════════════════════                               │   │
│  │                                                                     │   │
│  │  When: First run OR when looking for new opportunities             │   │
│  │  What: Fetch events from Polymarket → Score → Map to stocks        │   │
│  │  Output: New tickers with PositionContext                          │   │
│  │                                                                     │   │
│  │  Runs if: No existing positions OR max_positions not reached       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MODE 2: UPDATE (Update EXISTING Context)                           │   │
│  │  ════════════════════════════════════════                           │   │
│  │                                                                     │   │
│  │  When: ALWAYS runs if there are existing Polymarket positions      │   │
│  │  What: Update probability snapshots, check event resolution        │   │
│  │  Output: Updated PositionContext, event status changes             │   │
│  │                                                                     │   │
│  │  Runs if: Any existing positions have Polymarket context           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  OUTPUT: Combined ticker list with updated context                  │   │
│  │  • New discoveries (from Mode 1)                                    │   │
│  │  • Existing positions with updated context (from Mode 2)            │   │
│  │  • Event status changes (resolved, expired)                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│                    ANALYST AGENTS RECEIVE THIS DATA                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Mode 2: UPDATE - What Happens for Existing Positions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UPDATE MODE - EXISTING POSITION HANDLING                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  For EACH existing position with Polymarket context:                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 1: FETCH CURRENT EVENT STATE                                  │   │
│  │  • Call Polymarket API with event_id from PositionContext           │   │
│  │  • Get current probability, volume, status                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 2: UPDATE PROBABILITY SNAPSHOT                                │   │
│  │                                                                     │   │
│  │  Before:                        After:                              │   │
│  │  probability: {                 probability: {                      │   │
│  │    current: 0.72                  current: 0.78  ← Updated          │   │
│  │    change_24h: null               change_24h: +0.03  ← Calculated   │   │
│  │    change_7d: null                change_7d: +0.08  ← Calculated    │   │
│  │    at_entry: 0.65                 at_entry: 0.65  ← Unchanged       │   │
│  │    since_entry: null              since_entry: +0.13  ← Calculated  │   │
│  │  }                              }                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 3: CHECK EVENT RESOLUTION                                     │   │
│  │                                                                     │   │
│  │  Is event closed/resolved?                                          │   │
│  │  ├── YES → Determine outcome (Yes/No) → Update event_state          │   │
│  │  └── NO  → Keep event_state as ACTIVE                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  STEP 4: RETURN STATUS CHANGES                                      │   │
│  │                                                                     │   │
│  │  If event_state changed:                                            │   │
│  │  status_changes = {"JPM": "resolved_yes", "XLF": "expired"}        │   │
│  │                                                                     │   │
│  │  These changes are passed to analyst agents as context              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Event States and What They Mean

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVENT STATES & AGENT BEHAVIOR                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  EVENT STATE         │ MEANING                │ AGENT BEHAVIOR              │
│  ════════════════════│════════════════════════│═════════════════════════════│
│                      │                        │                             │
│  ACTIVE              │ Event is ongoing,      │ Full analysis with          │
│                      │ probability updating   │ Polymarket context          │
│                      │                        │ Thesis is ACTIVE driver     │
│  ────────────────────┼────────────────────────┼─────────────────────────────│
│  RESOLVED_YES        │ Event resolved as YES  │ Thesis becomes HISTORICAL   │
│                      │ (e.g., Fed DID cut)    │ context. AI keeps managing  │
│                      │                        │ based on all data.          │
│                      │                        │ NO automatic exit.          │
│  ────────────────────┼────────────────────────┼─────────────────────────────│
│  RESOLVED_NO         │ Event resolved as NO   │ Thesis becomes HISTORICAL   │
│                      │ (e.g., Fed did NOT cut)│ context. Original thesis    │
│                      │                        │ was WRONG. AI re-evaluates  │
│                      │                        │ position based on new data. │
│  ────────────────────┼────────────────────────┼─────────────────────────────│
│  EXPIRED             │ Event ended without    │ Thesis becomes HISTORICAL   │
│                      │ clear resolution OR    │ context. AI manages based   │
│                      │ event not found        │ on remaining data.          │
│                      │                        │                             │
└─────────────────────────────────────────────────────────────────────────────┘

IMPORTANT: Event resolution does NOT trigger automatic position exit!
           The AI continues to manage the position using all available data.
           The original Polymarket thesis becomes historical context.
```

### How Event State is Passed to Agents

The PositionContext is passed to analyst agents as structured data. Each agent can use this context in their analysis. The event_state field indicates whether the event is still active or has resolved:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSITION CONTEXT PASSED TO AGENTS                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  The PositionContext is passed as structured data (not a prompt):          │
│                                                                             │
│  {                                                                         │
│    "event_id": "fed-rate-cut-march-2025",                                  │
│    "event_title": "Will Fed cut rates in March 2025?",                     │
│    "event_state": "ACTIVE" | "RESOLVED_YES" | "RESOLVED_NO" | "EXPIRED",   │
│    "thesis": "Rate cuts benefit banks via lending",                        │
│    "thesis_type": "short_term" | "long_term",                              │
│    "impact_direction": "bullish",                                          │
│    "confidence": 85,                                                       │
│    "probability": {                                                        │
│      "current": 0.78,                                                      │
│      "change_24h": 0.03,                                                   │
│      "at_entry": 0.65,                                                     │
│      "since_entry": 0.13                                                   │
│    }                                                                       │
│  }                                                                         │
│                                                                             │
│  Each analyst agent receives this context and can incorporate it into      │
│  their analysis. The agent's prompt template determines how this data      │
│  is used in the final LLM call.                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Thesis-Type-Aware Exit Guidance

When events resolve, the system automatically generates **exit guidance** based on:

1. **Event State** - How the event resolved (YES, NO, or EXPIRED)
2. **Thesis Type** - Whether the thesis was short-term (catalyst) or long-term (structural)
3. **Impact Direction** - Whether the thesis was bullish or bearish

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXIT GUIDANCE MATRIX                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  THESIS TYPE    │ RESOLVED IN FAVOR        │ RESOLVED AGAINST              │
│  ═══════════════╪══════════════════════════╪═══════════════════════════════│
│                 │                          │                               │
│  SHORT_TERM     │ ⚠️ CATALYST REALIZED     │ 🚨 CATALYST FAILED            │
│  (catalyst)     │ "Consider taking profits │ "Consider exiting position    │
│                 │  as the catalyst has     │  as the original catalyst     │
│                 │  played out"             │  is invalidated"              │
│                 │                          │                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│                 │                          │                               │
│  LONG_TERM      │ ✓ THESIS VALIDATED       │ ⚠️ THESIS CHALLENGED          │
│  (structural)   │ "Long-term structural    │ "Reassess position as the     │
│                 │  benefits expected.      │  structural change may not    │
│                 │  Consider holding"       │  materialize as expected"     │
│                 │                          │                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│                 │                          │                               │
│  EXPIRED        │ SHORT: "Catalyst no longer valid - reassess"             │
│                 │ LONG: "Thesis may still be valid - check fundamentals"   │
│                 │                          │                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How Exit Guidance Works:**

1. When an event resolves, the `EventThesis.get_exit_guidance()` method generates appropriate guidance
2. The guidance is appended to the thesis text via `get_thesis_with_guidance()`
3. Agents see the full thesis + guidance when analyzing positions
4. This helps prevent unlimited holding of positions after catalysts expire

**Example Output:**

```
Original Thesis: "Trump win benefits private prison stocks via policy changes"

After RESOLVED_YES (short-term bullish):
"Trump win benefits private prison stocks via policy changes

⚠️ SHORT-TERM CATALYST REALIZED - Event 'Trump wins 2024' resolved in favor
of thesis. Consider taking profits as the catalyst has played out."
```

### Complete Autonomous Mode Flow (Per Day/Cycle)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS MODE - COMPLETE DAILY FLOW                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DAY START                                                                  │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 1: POLYMARKET DISCOVERY LAYER                                │   │
│  │  ═══════════════════════════════════                                │   │
│  │                                                                     │   │
│  │  1a. UPDATE MODE (if existing positions)                           │   │
│  │      • Fetch current event states                                  │   │
│  │      • Update probability snapshots                                │   │
│  │      • Check for event resolution                                  │   │
│  │      • Mark status changes                                         │   │
│  │                                                                     │   │
│  │  1b. DISCOVERY MODE (if max_positions not reached)                 │   │
│  │      • Fetch new events from Polymarket                            │   │
│  │      • Score and filter events                                     │   │
│  │      • LLM maps to stocks                                          │   │
│  │      • Create PositionContext for new tickers                      │   │
│  │                                                                     │   │
│  │  Output: Ticker list + PositionContext for each                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 2: DATA COLLECTION                                           │   │
│  │  ════════════════════════                                           │   │
│  │                                                                     │   │
│  │  For each ticker (discovered + existing):                          │   │
│  │  • Price history (Yahoo Finance)                                   │   │
│  │  • Financial metrics                                               │   │
│  │  • News & sentiment                                                │   │
│  │  • Insider trades                                                  │   │
│  │  • PositionContext (from Phase 1)  ← Polymarket data               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 3: ANALYST AGENTS (Run in Parallel)                          │   │
│  │  ═════════════════════════════════════════                          │   │
│  │                                                                     │   │
│  │  Each agent receives:                                              │   │
│  │  • Standard financial data                                         │   │
│  │  • PositionContext with Polymarket data (if available)             │   │
│  │  • Event state (ACTIVE/RESOLVED_YES/RESOLVED_NO/EXPIRED)           │   │
│  │                                                                     │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                   │   │
│  │  │ Buffett │ │  Lynch  │ │Technicals│ │Sentiment│ ...              │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘                   │   │
│  │       └───────────┴───────────┴───────────┘                        │   │
│  │                       │                                            │   │
│  │                       ▼                                            │   │
│  │              Signal Aggregation                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PHASE 4: PORTFOLIO MANAGER                                         │   │
│  │  ══════════════════════════                                         │   │
│  │                                                                     │   │
│  │  • Review aggregated signals                                       │   │
│  │  • Apply risk management rules                                     │   │
│  │  • Decide: BUY / SELL / HOLD / SHORT / COVER                       │   │
│  │  • Execute trades                                                  │   │
│  │  • Update PositionContext with new entry prices                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│    │                                                                        │
│    ▼                                                                        │
│  DAY END → NEXT DAY (Loop continues)                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Flow Diagrams

### Backtesting Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         BACKTESTING ENGINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  START                                                                  │
│    │                                                                    │
│    ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    INITIALIZATION                                │   │
│  │  • Parse arguments (tickers, dates, analysts)                   │   │
│  │  • Initialize portfolio with starting capital                   │   │
│  │  • Set up data providers                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│    │                                                                    │
│    ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    FOR EACH DAY IN DATE RANGE                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  1. Fetch market data for all tickers                     │ │   │
│  │  │  2. Run each analyst agent                                │ │   │
│  │  │  3. Aggregate signals                                     │ │   │
│  │  │  4. Portfolio manager decides trades                      │ │   │
│  │  │  5. Execute trades (buy/sell/short/cover)                 │ │   │
│  │  │  6. Update portfolio state                                │ │   │
│  │  │  7. Calculate daily metrics                               │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│    │                                                                    │
│    ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    RESULTS & METRICS                            │   │
│  │  • Total Return                                                 │   │
│  │  • Sharpe Ratio                                                 │   │
│  │  • Sortino Ratio                                                │   │
│  │  • Maximum Drawdown                                             │   │
│  │  • Win Rate                                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Autonomous Mode Discovery Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    POLYMARKET DISCOVERY FLOW                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 1: FETCH EVENTS                                           │   │
│  │  • Get active events from Polymarket API                        │   │
│  │  • Filter by volume, liquidity thresholds                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 2: SCORE EVENTS (EventScorer)                             │   │
│  │  • Volume Score (total + 24hr activity)                         │   │
│  │  • Liquidity Score                                              │   │
│  │  • Time Horizon Score (7-30 days optimal)                       │   │
│  │  • Category Score (economy/finance/politics = high)             │   │
│  │  • Momentum Score (price changes)                               │   │
│  │  • Volume Trend Score (acceleration)                            │   │
│  │  • Smart Money Score (OI patterns)                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 3: FILTER & DEDUPLICATE                                   │   │
│  │  • Apply minimum score threshold                                │   │
│  │  • Filter by probability range (60-85%)                         │   │
│  │  • Check EventHistory for duplicates                            │   │
│  │  • Fuzzy match titles to avoid similar events                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 4: LLM STOCK MAPPING                                      │   │
│  │  • Send event details to LLM                                    │   │
│  │  • Inject portfolio context (avoid duplicates)                  │   │
│  │  • LLM identifies affected stocks                               │   │
│  │  • Returns: ticker, direction, confidence, thesis               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 5: CREATE POSITION CONTEXT                                │   │
│  │  • Build PositionContext for each discovered ticker             │   │
│  │  • Track event ID, thesis, probability snapshots                │   │
│  │  • Update EventHistory for future deduplication                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  STEP 6: ENTER STANDARD PIPELINE                                │   │
│  │  • Discovered tickers join manual tickers                       │   │
│  │  • All analysts analyze with Polymarket context                 │   │
│  │  • Portfolio manager makes final decisions                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Automatic Mode Looping

In live trading or continuous backtesting, the system operates in a loop:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AUTOMATIC TRADING LOOP                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    LOOP START                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  1. DISCOVERY PHASE (Autonomous Mode Only)                      │   │
│  │     • Check for new high-conviction events                      │   │
│  │     • Score and filter events                                   │   │
│  │     • Map to stocks, add to watchlist                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  2. UPDATE PHASE                                                │   │
│  │     • Update probability snapshots for existing positions       │   │
│  │     • Check for event resolution                                │   │
│  │     • Mark resolved events as historical context                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  3. ANALYSIS PHASE                                              │   │
│  │     • Fetch latest market data                                  │   │
│  │     • Run all analyst agents                                    │   │
│  │     • Aggregate signals                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  4. EXECUTION PHASE                                             │   │
│  │     • Portfolio manager reviews signals                         │   │
│  │     • Apply risk management rules                               │   │
│  │     • Execute trades (if any)                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  5. WAIT FOR NEXT CYCLE                                         │   │
│  │     • Backtest: Move to next day                                │   │
│  │     • Live: Wait for market hours / interval                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              └──────────────────────────────────────────┤
│                                                                         │
│                    LOOP CONTINUES UNTIL:                                │
│                    • End date reached (backtest)                        │
│                    • User stops (live trading)                          │
│                    • Error condition                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Position Lifecycle in Automatic Mode

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    POSITION LIFECYCLE                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  DISCOVERY ──► ENTRY ──► MANAGEMENT ──► EXIT                           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  DISCOVERY                                                      │   │
│  │  • Event found on Polymarket                                    │   │
│  │  • LLM maps to stock (e.g., "Fed rate cut" → JPM)              │   │
│  │  • PositionContext created with thesis                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ENTRY                                                          │   │
│  │  • Analysts analyze ticker (with Polymarket context)            │   │
│  │  • Consensus reached → position opened                          │   │
│  │  • Entry price recorded                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  MANAGEMENT (Daily Loop)                                        │   │
│  │  • Update probability snapshots                                 │   │
│  │  • Re-analyze with all available data                           │   │
│  │  • Polymarket is ONE input, not the only input                  │   │
│  │  • AI decides: hold, add, reduce, exit                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EVENT RESOLUTION (If Applicable)                               │   │
│  │  • Event resolves (Yes/No)                                      │   │
│  │  • Marked as HISTORICAL CONTEXT                                 │   │
│  │  • NO automatic exit - AI keeps managing                        │   │
│  │  • Original thesis becomes context, not constraint              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EXIT                                                           │   │
│  │  • AI decides based on:                                         │   │
│  │    - Changed fundamentals                                       │   │
│  │    - Technical signals                                          │   │
│  │    - Risk management rules                                      │   │
│  │    - New information                                            │   │
│  │  • Position closed, P&L recorded                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Polymarket Event Discovery

### Event Scoring System

The EventScorer ranks events by trading potential before expensive LLM analysis:

| Component    | Weight | Description                                          |
| ------------ | ------ | ---------------------------------------------------- |
| Volume       | 25%    | Total trading volume (higher = more interest)        |
| Liquidity    | 20%    | Current market liquidity (higher = better execution) |
| Time Horizon | 15%    | Days to resolution (7-30 days optimal)               |
| Category     | 15%    | Stock market relevance (economy/finance = high)      |
| Momentum     | 10%    | Price movement (strong moves = clearer signal)       |
| Volume Trend | 10%    | Volume acceleration (unusual activity)               |
| Smart Money  | 5%     | OI patterns (institutional activity proxy)           |

### Enhanced Signals (Options-Like Analysis)

The EnhancedEventScorer provides options-market-style signals:

| Signal             | Polymarket Equivalent  | Interpretation            |
| ------------------ | ---------------------- | ------------------------- |
| Unusual Volume     | volume24hr / daily_avg | Informed trading activity |
| Delta Movement     | oneDayPriceChange      | Probability momentum      |
| Implied Volatility | bid-ask spread         | Market uncertainty        |
| Smart Money        | volume / openInterest  | Institutional positioning |

### Category Relevance

Events are weighted by stock market relevance:

| Category | Weight | Rationale              |
| -------- | ------ | ---------------------- |
| Economy  | 1.0    | Direct market impact   |
| Finance  | 1.0    | Direct market impact   |
| Politics | 0.9    | Policy implications    |
| Tech     | 0.8    | Sector-specific impact |
| Crypto   | 0.6    | Indirect correlation   |
| Climate  | 0.5    | Long-term implications |
| Sports   | 0.2    | Limited market impact  |
| Culture  | 0.2    | Limited market impact  |

---

## Quick Reference

### CLI Commands

```bash
# Manual Mode
poetry run python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL

# Manual Mode - Long Only (no short selling)
poetry run python -m src.backtesting.cli --tickers AAPL,MSFT,GOOGL --no-short

# Autonomous Mode
poetry run python -m src.backtesting.cli --autonomous --max-positions 10

# Autonomous Mode - Long Only (no short selling)
poetry run python -m src.backtesting.cli --autonomous --max-positions 10 --no-short

# Polymarket Research CLI - Single Event
poetry run python -m src.backtesting.polymarket_cli --event-slug presidential-election-winner-2024

# Polymarket Research CLI - Historical Backtest
poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --max-events 5

# Polymarket Research CLI - Long Only
poetry run python -m src.backtesting.polymarket_cli --start-date 2024-01-01 --no-short
```

### Key Files

| File                                 | Purpose                          |
| ------------------------------------ | -------------------------------- |
| `src/backtesting/cli.py`             | Main backtesting CLI             |
| `src/backtesting/polymarket_cli.py`  | Polymarket research CLI          |
| `src/agents/polymarket_discovery.py` | Event discovery agent            |
| `src/agents/portfolio_manager.py`    | Portfolio decisions (--no-short) |
| `src/core/trading_cycle.py`          | Unified trading cycle            |
| `src/core/discovery_manager.py`      | Discovery orchestration          |
| `src/core/position_tracker.py`       | Position tracking                |
| `src/tools/event_scorer.py`          | Event scoring engine             |
| `src/data/position_context.py`       | Position context models          |
| `src/data/event_models.py`           | Event scoring models             |

### Environment Variables

```bash
# Required: At least one LLM API key
GOOGLE_API_KEY=your_key      # Recommended for Gemini
OPENAI_API_KEY=your_key      # Alternative
ANTHROPIC_API_KEY=your_key   # Alternative

# Optional: Live trading
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_PAPER_TRADING=true
```
