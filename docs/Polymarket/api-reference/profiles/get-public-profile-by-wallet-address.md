---
source_url: https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address
scraped_at: 2026-02-01T06:08:23.745362
scraper: DocsScraper/1.0
---

Title: Get public profile by wallet address - Polymarket Documentation

URL Source: https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address

Markdown Content:
Get public profile by wallet address - Polymarket Documentation
===============

[Skip to main content](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#content-area)

[Polymarket Documentation home page![Image 1: light logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-black.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=aff81820f1f3d577fecb3956a8a3bee1)![Image 2: dark logo](https://mintcdn.com/polymarket-292d1b1b/HmeJ4Y1FlVRRp8nd/images/logo-white.svg?fit=max&auto=format&n=HmeJ4Y1FlVRRp8nd&q=85&s=3bc6857b5dbe8b74b9a7d40975c19b2b)](https://docs.polymarket.com/)

Search...

⌘K Ask AI

*   [Main Site](https://polymarket.com/)
*   [Main Site](https://polymarket.com/)

Search...

Navigation

Profiles

Get public profile by wallet address

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
    *   [GET Get public profile by wallet address](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address)

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

Get public profile by wallet address

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://gamma-api.polymarket.com/public-profile
```

200

400

404

Copy

Ask AI

```
{
  "createdAt": "2023-11-07T05:31:56Z",
  "proxyWallet": "<string>",
  "profileImage": "<string>",
  "displayUsernamePublic": true,
  "bio": "<string>",
  "pseudonym": "<string>",
  "name": "<string>",
  "users": [
    {
      "id": "<string>",
      "creator": true,
      "mod": true
    }
  ],
  "xUsername": "<string>",
  "verifiedBadge": true
}
```

Profiles

Get public profile by wallet address
====================================

GET

/

public-profile

Try it

Get public profile by wallet address

cURL

Copy

Ask AI

```
curl --request GET \
  --url https://gamma-api.polymarket.com/public-profile
```

200

400

404

Copy

Ask AI

```
{
  "createdAt": "2023-11-07T05:31:56Z",
  "proxyWallet": "<string>",
  "profileImage": "<string>",
  "displayUsernamePublic": true,
  "bio": "<string>",
  "pseudonym": "<string>",
  "name": "<string>",
  "users": [
    {
      "id": "<string>",
      "creator": true,
      "mod": true
    }
  ],
  "xUsername": "<string>",
  "verifiedBadge": true
}
```

#### Query Parameters

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#parameter-address)

address

string

required

The wallet address (proxy wallet or user address)

#### Response

200

application/json

Public profile information

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-created-at-one-of-0)

createdAt

string<date-time> | null

ISO 8601 timestamp of when the profile was created

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-proxy-wallet-one-of-0)

proxyWallet

string | null

The proxy wallet address

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-profile-image-one-of-0)

profileImage

string<uri> | null

URL to the profile image

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-display-username-public-one-of-0)

displayUsernamePublic

boolean | null

Whether the username is displayed publicly

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-bio-one-of-0)

bio

string | null

Profile bio

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-pseudonym-one-of-0)

pseudonym

string | null

Auto-generated pseudonym

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-name-one-of-0)

name

string | null

User-chosen display name

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-users-one-of-0)

users

object[] | null

Array of associated user objects

Show child attributes

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-x-username-one-of-0)

xUsername

string | null

X (Twitter) username

[​](https://docs.polymarket.com/api-reference/profiles/get-public-profile-by-wallet-address#response-verified-badge-one-of-0)

verifiedBadge

boolean | null

Whether the profile has a verified badge

[Get comments by user address](https://docs.polymarket.com/api-reference/comments/get-comments-by-user-address)[Search markets, events, and profiles](https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles)

⌘I

[github](https://github.com/polymarket)

[Powered by](https://www.mintlify.com/?utm_campaign=poweredBy&utm_medium=referral&utm_source=polymarket-292d1b1b)
