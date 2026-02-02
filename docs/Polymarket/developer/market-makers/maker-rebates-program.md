---
source_url: https://docs.polymarket.com/developers/market-makers/maker-rebates-program
scraped_at: 2026-01-31T22:34:02.022689
scraper: DocsScraper/1.0
---

Title: Maker Rebates Program - Polymarket Documentation

URL Source: https://docs.polymarket.com/developers/market-makers/maker-rebates-program

Markdown Content:
Maker Rebates Program - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

⌘K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Market Makers

Maker Rebates Program

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
*   [Fee Handling by Implementation Type](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-handling-by-implementation-type)
*   [Option 1: Official CLOB Clients (Recommended)](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#option-1%3A-official-clob-clients-recommended)
*   [Option 2: REST API / Custom Implementations](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#option-2%3A-rest-api-%2F-custom-implementations)
*   [Step 1: Fetch the Fee Rate](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-1%3A-fetch-the-fee-rate)
*   [Step 2: Include in Your Signed Order](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-2%3A-include-in-your-signed-order)
*   [Step 3: Sign and Submit](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-3%3A-sign-and-submit)
*   [Fee Behavior](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-behavior)
*   [Fee Table (100 shares)](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-table-100-shares)
*   [Maker Rebates](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#maker-rebates)
*   [How Rebates Work](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#how-rebates-work)
*   [Rebate Pool](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#rebate-pool)
*   [Which Markets Have Fees?](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#which-markets-have-fees)
*   [Related Documentation](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#related-documentation)

Market Makers

Maker Rebates Program
=====================

Technical guide for handling taker fees and earning maker rebates on Polymarket

Polymarket has enabled **taker fees** on **15-minute crypto markets**. These fees fund a **Maker Rebates** program that pays daily USDC rebates to liquidity providers.
[​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-handling-by-implementation-type)

Fee Handling by Implementation Type
--------------------------------------------------------------------------------------------------------------------------------------------------------

### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#option-1:-official-clob-clients-recommended)

Option 1: Official CLOB Clients (Recommended)

The official CLOB clients **automatically handle fees** for you. Update to the latest version:

[TypeScript Client ----------------- npm install @polymarket/clob-client@latest](https://github.com/Polymarket/clob-client)[Python Client ------------- pip install —upgrade py-clob-client](https://github.com/Polymarket/py-clob-client)

**What the client does automatically:**
1.   Fetches the fee rate for the market’s token ID
2.   Includes `feeRateBps` in the order structure
3.   Signs the order with the fee rate included

**You don’t need to do anything extra**. Just update your client and your orders will work on fee-enabled markets.

* * *

### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#option-2:-rest-api-/-custom-implementations)

Option 2: REST API / Custom Implementations

If you’re calling the REST API directly or building your own order signing, you must manually include the fee rate in your **signed order payload**.
#### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-1:-fetch-the-fee-rate)

Step 1: Fetch the Fee Rate

Query the fee rate for the token ID before creating your order:

Copy

Ask AI

```
GET https://clob.polymarket.com/fee-rate?token_id={token_id}
```

**Response:**

Copy

Ask AI

```
{
  "fee_rate_bps": 1000
}
```

*   **Fee-enabled markets** return a value like `1000`
*   **Fee-free markets** return `0`

#### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-2:-include-in-your-signed-order)

Step 2: Include in Your Signed Order

Add the `feeRateBps` field to your order object. This value is **part of the signed payload**, the CLOB validates your signature against it.

Copy

Ask AI

```
{
  "salt": "12345",
  "maker": "0x...",
  "signer": "0x...",
  "taker": "0x...",
  "tokenId": "71321045679252212594626385532706912750332728571942532289631379312455583992563",
  "makerAmount": "50000000",
  "takerAmount": "100000000",
  "expiration": "0",
  "nonce": "0",
  "feeRateBps": "1000",
  "side": "0",
  "signatureType": 2,
  "signature": "0x..."
}
```

#### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#step-3:-sign-and-submit)

Step 3: Sign and Submit

1.   Include `feeRateBps` in the order object **before signing**
2.   Sign the complete order
3.   POST to `/order` endpoint

**Important:** Always fetch `fee_rate_bps` dynamically, do not hardcode. The fee rate may vary by market or change over time. You only need to pass `feeRateBps`

See the [Create Order documentation](https://docs.polymarket.com/developers/CLOB/orders/create-order) for full signing details.

* * *

[​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-behavior)

Fee Behavior
----------------------------------------------------------------------------------------------------------

Fees are calculated in USDC and vary based on the share price. The effective rate **peaks at 50%** probability and decreases symmetrically toward the extremes.
### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#fee-table-100-shares)

Fee Table (100 shares)

| Price | Trade Value | Fee (USDC) | Effective Rate |
| --- | --- | --- | --- |
| $0.10 | $10 | $0.02 | 0.20% |
| $0.20 | $20 | $0.13 | 0.64% |
| $0.30 | $30 | $0.33 | 1.10% |
| $0.40 | $40 | $0.58 | 1.44% |
| $0.50 | $50 | $0.78 | **1.56%** |
| $0.60 | $60 | $0.86 | 1.44% |
| $0.70 | $70 | $0.77 | 1.10% |
| $0.80 | $80 | $0.51 | 0.64% |
| $0.90 | $90 | $0.18 | 0.20% |

The maximum effective fee rate is **1.56%** at 50% probability. Fees are the same for both buying and selling.

* * *

[​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#maker-rebates)

Maker Rebates
------------------------------------------------------------------------------------------------------------

### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#how-rebates-work)

How Rebates Work

*   **Eligibility:** Your orders must add liquidity (maker orders) and get filled
*   **Calculation:** Proportional to your share of executed maker volume in each eligible market
*   **Payment:** Daily in USDC, paid directly to your wallet

### [​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#rebate-pool)

Rebate Pool

The rebate pool for each market is funded by taker fees collected in that market. The payout percentage is subject to change:

| Period | Maker Rebate |
| --- | --- |
| Jan 9 – Jan 11, 2026 (Until Sunday Midnight UTC) | 100% |
| Jan 12 – Jan 18, 2026 | 20% |

The rebate percentage is at the sole discretion of Polymarket.

* * *

[​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#which-markets-have-fees)

Which Markets Have Fees?
---------------------------------------------------------------------------------------------------------------------------------

Currently, only **15-minute crypto markets** have fees enabled. Query the fee-rate endpoint to check:

Copy

Ask AI

```
GET https://clob.polymarket.com/fee-rate?token_id={token_id}

# Fee-enabled: { "fee_rate_bps": 1000 }
# Fee-free:    { "fee_rate_bps": 0 }
```

* * *

[​](https://docs.polymarket.com/developers/market-makers/maker-rebates-program#related-documentation)

Related Documentation
----------------------------------------------------------------------------------------------------------------------------

[Maker Rebates Program --------------------- User-facing overview with full fee tables](https://docs.polymarket.com/polymarket-learn/trading/maker-rebates-program)[Create CLOB Order via REST API ------------------------------ Full order structure and signing documentation](https://docs.polymarket.com/developers/CLOB/orders/create-order)

[Liquidity Rewards](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)[Data Feeds](https://docs.polymarket.com/developers/market-makers/data-feeds)

⌘I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)
