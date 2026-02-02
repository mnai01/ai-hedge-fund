---
source_url: https://docs.polymarket.com/developers/CLOB/trades/trades
scraped_at: 2026-01-31T22:32:29.018028
scraper: DocsScraper/1.0
---

Title: Get Trades - Polymarket Documentation

URL Source: https://docs.polymarket.com/developers/CLOB/trades/trades

Markdown Content:
Get Trades - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/developers/CLOB/trades/trades#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

⌘K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Trades

Get Trades

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
    *   [Trades Overview](https://docs.polymarket.com/developers/CLOB/trades/trades-overview)
    *   [Get Trades](https://docs.polymarket.com/developers/CLOB/trades/trades)

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

Python

Typescript

Copy

Ask AI

```
from py_clob_client.clob_types import TradeParams

resp = client.get_trades(
    TradeParams(
        maker_address=client.get_address(),
        market="0xbd31dc8a20211944f6b70f31557f1001557b59905b7738480ca09bd4532f84af",
    ),
)
print(resp)
print("Done!")
```

Trades

Get Trades
==========

 This endpoint requires a L2 Header. 

Get trades for the authenticated user based on the provided filters.**HTTP REQUEST**`GET /<clob-endpoint>/data/trades`
### [​](https://docs.polymarket.com/developers/CLOB/trades/trades#request-parameters)

Request Parameters

| Name | Required | Type | Description |
| --- | --- | --- | --- |
| id | no | string | id of trade to fetch |
| taker | no | string | address to get trades for where it is included as a taker |
| maker | no | string | address to get trades for where it is included as a maker |
| market | no | string | market for which to get the trades (condition ID) |
| before | no | string | unix timestamp representing the cutoff up to which trades that happened before then can be included |
| after | no | string | unix timestamp representing the cutoff for which trades that happened after can be included |

### [​](https://docs.polymarket.com/developers/CLOB/trades/trades#response-format)

Response Format

| Name | Type | Description |
| --- | --- | --- |
| null | Trade[] | list of trades filtered by query parameters |

A `Trade` object is of the form:

| Name | Type | Description |
| --- | --- | --- |
| id | string | trade id |
| taker_order_id | string | hash of taker order (market order) that catalyzed the trade |
| market | string | market id (condition id) |
| asset_id | string | asset id (token id) of taker order (market order) |
| side | string | buy or sell |
| size | string | size |
| fee_rate_bps | string | the fees paid for the taker order expressed in basic points |
| price | string | limit price of taker order |
| status | string | trade status (see above) |
| match_time | string | time at which the trade was matched |
| last_update | string | timestamp of last status update |
| outcome | string | human readable outcome of the trade |
| maker_address | string | funder address of the taker of the trade |
| owner | string | api key of taker of the trade |
| transaction_hash | string | hash of the transaction where the trade was executed |
| bucket_index | integer | index of bucket for trade in case trade is executed in multiple transactions |
| maker_orders | MakerOrder[] | list of the maker trades the taker trade was filled against |
| type | string | side of the trade: TAKER or MAKER |

A `MakerOrder` object is of the form:

| Name | Type | Description |
| --- | --- | --- |
| order_id | string | id of maker order |
| maker_address | string | maker address of the order |
| owner | string | api key of the owner of the order |
| matched_amount | string | size of maker order consumed with this trade |
| fee_rate_bps | string | the fees paid for the taker order expressed in basic points |
| price | string | price of maker order |
| asset_id | string | token/asset id |
| outcome | string | human readable outcome of the maker order |
| side | string | the side of the maker order. Can be `buy` or `sell` |

Python

Typescript

Copy

Ask AI

```
from py_clob_client.clob_types import TradeParams

resp = client.get_trades(
    TradeParams(
        maker_address=client.get_address(),
        market="0xbd31dc8a20211944f6b70f31557f1001557b59905b7738480ca09bd4532f84af",
    ),
)
print(resp)
print("Done!")
```

[Trades Overview](https://docs.polymarket.com/developers/CLOB/trades/trades-overview)[WSS Overview](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview)

⌘I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)
