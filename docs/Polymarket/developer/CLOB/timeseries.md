---
source_url: https://docs.polymarket.com/developers/CLOB/timeseries
scraped_at: 2026-01-31T22:32:27.408200
scraper: DocsScraper/1.0
---

Title: Historical Timeseries Data - Polymarket Documentation

URL Source: https://docs.polymarket.com/developers/CLOB/timeseries

Markdown Content:
Historical Timeseries Data - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/developers/CLOB/timeseries#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

⌘K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Historical Timeseries Data

Historical Timeseries Data

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
    *   [GET Historical Timeseries Data](https://docs.polymarket.com/developers/CLOB/timeseries)

*   Order Management 
*   Trades 

##### Websocket

*   [WSS Overview](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview)
*   [WSS Quickstart](https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart)
*   [WSS Authentication](https://docs.polymarket.com/developers/CLOB/websocket/wss-auth)
*   [User Channel](https://docs.polymarket.com/developers/CLOB/websocket/user-channel)
*   [Market Channel](https://docs.polymarket.com/developers/CLOB/websocket/market-channel)
*   Sports Websocket 

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

Get price history for a traded token

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://clob.polymarket.com/prices-history
```

200

400

404

500

Copy

Ask AI

```
{
  "history": [
    {
      "t": 1697875200,
      "p": 1800.75
    }
  ]
}
```

Historical Timeseries Data

Historical Timeseries Data
==========================

Fetches historical price data for a specified market token.

GET

/

prices-history

Try it

Get price history for a traded token

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://clob.polymarket.com/prices-history
```

200

400

404

500

Copy

Ask AI

```
{
  "history": [
    {
      "t": 1697875200,
      "p": 1800.75
    }
  ]
}
```

The CLOB provides detailed price history for each traded token.**HTTP REQUEST**`GET /<clob-endpoint>/prices-history`

We also have a Interactive Notebook to visualize the data from this endpoint available [here](https://colab.research.google.com/drive/1s4TCOR4K7fRP7EwAH1YmOactMakx24Cs?usp=sharing#scrollTo=mYCJBcfB9Zu4).

#### Query Parameters

[​](https://docs.polymarket.com/developers/CLOB/timeseries#parameter-market)

market

string

required

The CLOB token ID for which to fetch price history

[​](https://docs.polymarket.com/developers/CLOB/timeseries#parameter-start-ts)

startTs

number

The start time, a Unix timestamp in UTC

[​](https://docs.polymarket.com/developers/CLOB/timeseries#parameter-end-ts)

endTs

number

The end time, a Unix timestamp in UTC

[​](https://docs.polymarket.com/developers/CLOB/timeseries#parameter-interval)

interval

enum<string>

A string representing a duration ending at the current time. Mutually exclusive with startTs and endTs

Available options:

`1m`,

`1w`,

`1d`,

`6h`,

`1h`,

`max`

[​](https://docs.polymarket.com/developers/CLOB/timeseries#parameter-fidelity)

fidelity

number

The resolution of the data, in minutes

#### Response

200

application/json

A list of timestamp/price pairs

[​](https://docs.polymarket.com/developers/CLOB/timeseries#response-history)

history

object[]

required

Show child attributes

[Get bid-ask spreads](https://docs.polymarket.com/api-reference/spreads/get-bid-ask-spreads)[Orders Overview](https://docs.polymarket.com/developers/CLOB/orders/orders)

⌘I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)
