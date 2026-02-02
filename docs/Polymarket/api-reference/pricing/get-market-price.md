---
source_url: https://docs.polymarket.com/api-reference/pricing/get-market-price
scraped_at: 2026-02-01T06:08:08.382504
scraper: DocsScraper/1.0
---

Title: Get market price - Polymarket Documentation

URL Source: https://docs.polymarket.com/api-reference/pricing/get-market-price

Markdown Content:
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

*   
    *           *   [GET Get market price](https://docs.polymarket.com/api-reference/pricing/get-market-price)
        *   [GET Get multiple market prices](https://docs.polymarket.com/api-reference/pricing/get-multiple-market-prices)
        *   [POST Get multiple market prices by request](https://docs.polymarket.com/api-reference/pricing/get-multiple-market-prices-by-request)
        *   [GET Get midpoint price](https://docs.polymarket.com/api-reference/pricing/get-midpoint-price)
        *   [GET Get price history for a traded token](https://docs.polymarket.com/api-reference/pricing/get-price-history-for-a-traded-token)

##### Websocket

*   [WSS Overview](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview)
*   [WSS Quickstart](https://docs.polymarket.com/quickstart/websocket/WSS-Quickstart)
*   [WSS Authentication](https://docs.polymarket.com/developers/CLOB/websocket/wss-auth)
*   [User Channel](https://docs.polymarket.com/developers/CLOB/websocket/user-channel)
*   [Market Channel](https://docs.polymarket.com/developers/CLOB/websocket/market-channel)

##### Real Time Data Stream

*   [RTDS Overview](https://docs.polymarket.com/developers/RTDS/RTDS-overview)
*   [RTDS Crypto Prices](https://docs.polymarket.com/developers/RTDS/RTDS-crypto-prices)
*   [RTDS Comments](https://docs.polymarket.com/developers/RTDS/RTDS-comments)

##### Gamma Structure

*   [Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview)
*   [Gamma Structure](https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure)
*   [Fetching Markets](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)

##### Gamma Endpoints

##### Data-API

##### Bridge & Swap

*   [Overview](https://docs.polymarket.com/developers/misc-endpoints/bridge-overview)

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

Get market price

```
curl --request GET \
  --url https://clob.polymarket.com/price
```

`{  "price": "1800.50"}`

Pricing

Retrieves the market price for a specific token and side

GET

/

price

Get market price

```
curl --request GET \
  --url https://clob.polymarket.com/price
```

`{  "price": "1800.50"}`

#### Query Parameters

[​](https://docs.polymarket.com/api-reference/pricing/get-market-price#parameter-token-id)

token_id

string

required

The unique identifier for the token

[​](https://docs.polymarket.com/api-reference/pricing/get-market-price#parameter-side)

side

enum<string>

required

The side of the market (BUY or SELL)

Available options

:

`BUY`,

`SELL`

#### Response

Successful response

[​](https://docs.polymarket.com/api-reference/pricing/get-market-price#response-price)

price

string

required

The market price (as string to maintain precision)

Example:

`"1800.50"`

[Get multiple order books summaries by request](https://docs.polymarket.com/api-reference/orderbook/get-multiple-order-books-summaries-by-request)[Get multiple market prices](https://docs.polymarket.com/api-reference/pricing/get-multiple-market-prices)

Ctrl+I
