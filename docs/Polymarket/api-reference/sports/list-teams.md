---
source_url: https://docs.polymarket.com/api-reference/sports/list-teams
scraped_at: 2026-02-01T06:09:39.595307
scraper: DocsScraper/1.0
---

Title: List teams - Polymarket Documentation

URL Source: https://docs.polymarket.com/api-reference/sports/list-teams

Markdown Content:
List teams - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/api-reference/sports/list-teams#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

Ctrl K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Sports

List teams

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
    *   [GET List teams](https://docs.polymarket.com/api-reference/sports/list-teams)
    *   [GET Get sports metadata information](https://docs.polymarket.com/api-reference/sports/get-sports-metadata-information)
    *   [GET Get valid sports market types](https://docs.polymarket.com/api-reference/sports/get-valid-sports-market-types)

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

List teams

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://gamma-api.polymarket.com/teams
```

200

Copy

Ask AI

```
[
  {
    "id": 123,
    "name": "<string>",
    "league": "<string>",
    "record": "<string>",
    "logo": "<string>",
    "abbreviation": "<string>",
    "alias": "<string>",
    "createdAt": "2023-11-07T05:31:56Z",
    "updatedAt": "2023-11-07T05:31:56Z"
  }
]
```

Sports

List teams
==========

GET

/

teams

Try it

List teams

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://gamma-api.polymarket.com/teams
```

200

Copy

Ask AI

```
[
  {
    "id": 123,
    "name": "<string>",
    "league": "<string>",
    "record": "<string>",
    "logo": "<string>",
    "abbreviation": "<string>",
    "alias": "<string>",
    "createdAt": "2023-11-07T05:31:56Z",
    "updatedAt": "2023-11-07T05:31:56Z"
  }
]
```

#### Query Parameters

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-limit)

limit

integer

Required range: `x >= 0`

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-offset)

offset

integer

Required range: `x >= 0`

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-order)

order

string

Comma-separated list of fields to order by

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-ascending)

ascending

boolean

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-league)

league

string[]

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-name)

name

string[]

[​](https://docs.polymarket.com/api-reference/sports/list-teams#parameter-abbreviation)

abbreviation

string[]

#### Response

200 - application/json

List of teams

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-id)

id

integer

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-name-one-of-0)

name

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-league-one-of-0)

league

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-record-one-of-0)

record

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-logo-one-of-0)

logo

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-abbreviation-one-of-0)

abbreviation

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-alias-one-of-0)

alias

string | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-created-at-one-of-0)

createdAt

string<date-time> | null

[​](https://docs.polymarket.com/api-reference/sports/list-teams#response-items-updated-at-one-of-0)

updatedAt

string<date-time> | null

[Gamma API Health check](https://docs.polymarket.com/api-reference/gamma-status/gamma-api-health-check)[Get sports metadata information](https://docs.polymarket.com/api-reference/sports/get-sports-metadata-information)

Ctrl+I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)

Assistant

Responses are generated using AI and may contain mistakes.
