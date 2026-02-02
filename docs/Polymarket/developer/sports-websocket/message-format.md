---
source_url: https://docs.polymarket.com/developers/sports-websocket/message-format
scraped_at: 2026-01-31T22:34:18.509017
scraper: DocsScraper/1.0
---

Title: Message Format - Polymarket Documentation

URL Source: https://docs.polymarket.com/developers/sports-websocket/message-format

Markdown Content:
Message Format - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/developers/sports-websocket/message-format#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

⌘K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Sports Websocket

Message Format

[User Guide](https://docs.polymarket.com/polymarket-learn/get-started/what-is-polymarket)[For Developers](https://docs.polymarket.com/quickstart/overview)[Changelog](https://docs.polymarket.com/changelog/changelog)

*   [Polymarket](https://polymarket.com/)
*   [Discord Community](https://discord.gg/polymarket)
*   [Twitter](https://x.com/polymarket)

##### Developer Quickstart

*   [Developer Quickstart](https://docs.polymarket.com/quickstart/overview)
*   [Fetching Market Data](https://docs.polymarket.com/quickstart/fetching-data)
*   [Placing Your First Order](https://docs.polymarket.com/quickstart/first-order)
*   [Glossary](https://docs.polymarket.com/quickstart/reference/glossary)
*   [API Rate Limits](https://docs.polymarket.com/quickstart/introduction/rate-limits)
*   [Endpoints](https://docs.polymarket.com/quickstart/reference/endpoints)

##### Market Makers

*   [Market Maker Introduction](https://docs.polymarket.com/developers/market-makers/introduction)
*   [Setup](https://docs.polymarket.com/developers/market-makers/setup)
*   [Trading](https://docs.polymarket.com/developers/market-makers/trading)
*   [Liquidity Rewards](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
*   [Maker Rebates Program](https://docs.polymarket.com/developers/market-makers/maker-rebates-program)
*   [Data Feeds](https://docs.polymarket.com/developers/market-makers/data-feeds)
*   [Inventory Management](https://docs.polymarket.com/developers/market-makers/inventory)

##### Polymarket Builders Program

*   [Builder Program Introduction](https://docs.polymarket.com/developers/builders/builder-intro)
*   [Builder Tiers](https://docs.polymarket.com/developers/builders/builder-tiers)
*   [Builder Profile & Keys](https://docs.polymarket.com/developers/builders/builder-profile)
*   [Order Attribution](https://docs.polymarket.com/developers/builders/order-attribution)
*   [Relayer Client](https://docs.polymarket.com/developers/builders/relayer-client)
*   [Examples](https://docs.polymarket.com/developers/builders/examples)

##### Central Limit Order Book

*   [CLOB Introduction](https://docs.polymarket.com/developers/CLOB/introduction)
*   [Status](https://docs.polymarket.com/developers/CLOB/status)
*   [Quickstart](https://docs.polymarket.com/developers/CLOB/quickstart)
*   [Authentication](https://docs.polymarket.com/developers/CLOB/authentication)
*   [Geographic Restrictions](https://docs.polymarket.com/developers/CLOB/geoblock)
*   Client 
*   REST API 
*   Historical Timeseries Data 
*   Order Management 
*   Trades 

##### Websocket

*   [WSS Overview](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview)
*   [WSS Quickstart](https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart)
*   [WSS Authentication](https://docs.polymarket.com/developers/CLOB/websocket/wss-auth)
*   [User Channel](https://docs.polymarket.com/developers/CLOB/websocket/user-channel)
*   [Market Channel](https://docs.polymarket.com/developers/CLOB/websocket/market-channel)
*   Sports Websocket 
    *   [Overview](https://docs.polymarket.com/developers/sports-websocket/overview)
    *   [Message Format](https://docs.polymarket.com/developers/sports-websocket/message-format)
    *   [Quickstart](https://docs.polymarket.com/developers/sports-websocket/quickstart)

##### Real Time Data Stream

*   [RTDS Overview](https://docs.polymarket.com/developers/RTDS/RTDS-overview)
*   [RTDS Crypto Prices](https://docs.polymarket.com/developers/RTDS/RTDS-crypto-prices)
*   [RTDS Comments](https://docs.polymarket.com/developers/RTDS/RTDS-comments)

##### Gamma Structure

*   [Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview)
*   [Gamma Structure](https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure)
*   [Fetching Markets](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)

##### Gamma Endpoints

*   Gamma Status 
*   Sports 
*   Tags 
*   Events 
*   Markets 
*   Series 
*   Comments 
*   Profiles 
*   Search 

##### Data-API

*   Data API Status 
*   Misc 
*   Core 
*   Builders 

##### Bridge & Swap

*   [Overview](https://docs.polymarket.com/developers/misc-endpoints/bridge-overview)
*   Bridge 

##### Subgraph

*   [Overview](https://docs.polymarket.com/developers/subgraph/overview)

##### Resolution

*   [Resolution](https://docs.polymarket.com/developers/resolution/UMA)

##### Conditional Token Frameworks

*   [Overview](https://docs.polymarket.com/developers/CTF/overview)
*   [Splitting USDC](https://docs.polymarket.com/developers/CTF/split)
*   [Merging Tokens](https://docs.polymarket.com/developers/CTF/merge)
*   [Reedeeming Tokens](https://docs.polymarket.com/developers/CTF/redeem)
*   [Deployment and Additional Information](https://docs.polymarket.com/developers/CTF/deployment-resources)

##### Proxy Wallets

*   [Proxy wallet](https://docs.polymarket.com/developers/proxy-wallet)

##### Negative Risk

*   [Overview](https://docs.polymarket.com/developers/neg-risk/overview)

On this page
*   [sport_result Message](https://docs.polymarket.com/developers/sports-websocket/message-format#sport_result-message)
*   [Structure](https://docs.polymarket.com/developers/sports-websocket/message-format#structure)
*   [Example Messages](https://docs.polymarket.com/developers/sports-websocket/message-format#example-messages)
*   [Slug Format](https://docs.polymarket.com/developers/sports-websocket/message-format#slug-format)
*   [Period Values](https://docs.polymarket.com/developers/sports-websocket/message-format#period-values)
*   [Handling Updates](https://docs.polymarket.com/developers/sports-websocket/message-format#handling-updates)

Sports Websocket

Message Format
==============

Structure of sports result update messages

Once connected to the Sports WebSocket, clients receive JSON messages whenever a sports event updates. Messages are broadcast to all connected clients automatically.

* * *

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#sport_result-message)

sport_result Message
----------------------------------------------------------------------------------------------------------------------

Emitted when:
*   A match goes live
*   The score changes
*   The period changes (e.g., halftime, overtime)
*   A match ends
*   Possession changes (NFL and CFB only)

### [​](https://docs.polymarket.com/developers/sports-websocket/message-format#structure)

Structure

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-game-id)

gameId

number

Unique identifier for the game

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-league-abbreviation)

leagueAbbreviation

string

League identifier (e.g., `"nfl"`, `"nba"`, `"cs2"`)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-home-team)

homeTeam

string

Home team name or abbreviation

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-away-team)

awayTeam

string

Away team name or abbreviation

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-status)

status

string

Game status (e.g., `"InProgress"`, `"finished"`)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-live)

live

boolean

`true` if the match is currently in progress

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-ended)

ended

boolean

`true` if the match has concluded

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-score)

score

string

Current score (format varies by sport)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-period)

period

string

Current period (e.g., `"Q4"`, `"2H"`, `"2/3"`)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-elapsed)

elapsed

string

Time elapsed in current period (e.g., `"05:09"`)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-finished-timestamp)

finishedTimestamp

string

Timestamp when the match ended (only present when `ended: true`)

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#param-turn)

turn

string

Team abbreviation with possession (NFL/CFB only)

The `turn` field is only present for NFL and CFB games and indicates which team currently has the ball.

### [​](https://docs.polymarket.com/developers/sports-websocket/message-format#example-messages)

Example Messages

**NFL (in progress):**

Copy

Ask AI

```
{
  "gameId": 19439,
  "leagueAbbreviation": "nfl",
  "homeTeam": "LAC",
  "awayTeam": "BUF",
  "status": "InProgress",
  "score": "3-16",
  "period": "Q4",
  "elapsed": "5:18",
  "live": true,
  "ended": false,
  "turn": "lac"
}
```

**Esports - CS2 (finished):**

Copy

Ask AI

```
{
  "gameId": 1317359,
  "leagueAbbreviation": "cs2",
  "homeTeam": "ARCRED",
  "awayTeam": "The glecs",
  "status": "finished",
  "score": "000-000|2-0|Bo3",
  "period": "2/3",
  "live": false,
  "ended": true
}
```

* * *

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#slug-format)

Slug Format
----------------------------------------------------------------------------------------------------

The `slug` field follows a consistent naming convention:

Copy

Ask AI

```
{league}-{team1}-{team2}-{date}
```

**Examples:**
*   `nfl-buf-kc-2025-01-26` — NFL: Buffalo Bills vs Kansas City Chiefs
*   `nba-lal-bos-2025-02-15` — NBA: LA Lakers vs Boston Celtics
*   `mlb-nyy-bos-2025-04-01` — MLB: NY Yankees vs Boston Red Sox

* * *

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#period-values)

Period Values
--------------------------------------------------------------------------------------------------------

| Period | Description |
| --- | --- |
| `1H` | First half |
| `2H` | Second half |
| `1Q`, `2Q`, `3Q`, `4Q` | Quarters (NFL, NBA) |
| `HT` | Halftime |
| `FT` | Full time (match ended in regulation) |
| `FT OT` | Full time with overtime |
| `FT NR` | Full time, no result (draw or canceled) |
| `End 1`, `End 2`, etc. | End of inning (MLB) |
| `1/3`, `2/3`, `3/3` | Map number in Bo3 series (Esports) |
| `1/5`, `2/5`, etc. | Map number in Bo5 series (Esports) |

* * *

[​](https://docs.polymarket.com/developers/sports-websocket/message-format#handling-updates)

Handling Updates
--------------------------------------------------------------------------------------------------------------

When processing messages, use the `gameId` field as the unique identifier to update your local state:

Copy

Ask AI

```
// Update or insert based on gameId
setSportsData(prev => {
  const existing = prev.find(item => item.gameId === data.gameId);
  if (existing) {
    return prev.map(item => 
      item.gameId === data.gameId ? data : item
    );
  }
  return [...prev, data];
});
```

[Overview](https://docs.polymarket.com/developers/sports-websocket/overview)[Quickstart](https://docs.polymarket.com/developers/sports-websocket/quickstart)

⌘I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)
