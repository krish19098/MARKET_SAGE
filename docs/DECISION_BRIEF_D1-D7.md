# MARKET SAGE — Decision Brief D1–D7

> **Status: awaiting owner's final decisions. M0 has not started.**
> Prepared 2026-11-11 (IST). Scope confirmed by owner: **personal use, analysis,
> recommendations and paper trading only. Real-money order execution disabled.**
> Owner's broker: **Angel One**.

## Evidence quality — read first

- Angel One's documentation hosts (`smartapi.angelone.in`, `smartapi.angelbroking.com`,
  `www.angelone.in`) **could not be fetched from this cloud environment** (network policy).
  Angel One facts below come from web-search extracts of Angel One's docs, FAQ, forum
  moderator posts and third-party guides. Each figure is tagged:
  - **[Official]** — Angel/broker's own docs/FAQ/notice as extracted by search.
  - **[Forum]** — broker staff/moderator forum post (may be dated).
  - **[3rd-party]** — blogs/reviews; weakest.
- Several published figures **conflict between sources** (noted inline). All must be
  re-verified against live docs and **by test calls with your credentials** in M1 before
  any code depends on them. Prices exclude GST unless stated and may have changed.

---

## D1 — Market data and broker integration

### D1.1 Angel One SmartAPI evaluation (initial integration candidate)

| Area | Findings | Confidence |
|---|---|---|
| **Pricing** | SmartAPI is free, including historical data; requires an Angel One account (you have one). | [Official] FAQ |
| **Historical candles** | `getCandleData`; intervals 1/3/5/10/15/30 min, 1 hour, 1 day. Per-request window: 1-min **30 days** (consistent across sources); hourly 400 days; daily 2000 days. 3/5/10-min reported as 60/90/100 days and 15/30-min as 200 days — **sources conflict**. One extract mentions a cap of ~8,000 records per request; an older forum post says 500. | [Official]/[Forum], conflicting |
| **Historical depth** | Moderator posts: NSE equity intraday from 2016-01-01, daily from 1990; BSE equity intraday from 2015, daily from 1990. One user reported failures before April 2021 (unresolved). **Expired F&O not provided** (irrelevant for cash equities). | [Forum], unverified |
| **Exchanges** | Historical endpoint covers indices, NSE, BSE, NFO, BFO, MCX, CDS per release note. | [Official] release note |
| **Volume / OI** | Candles are OHLCV; OI for derivatives. **No delivery quantity/%.** | [Official] / inferred |
| **Adjustment for splits/bonus** | **Not documented in anything found.** Must be tested empirically against NSE bhavcopy around known corporate actions. | Unknown |
| **Historical rate limits** | Reported 3 req/s; per-minute reduced from 150 to 120 (forum); ~5,000/hour. A 2026 guide says 2 req/s. **Conflicting.** General limit: 10 req/s per client code, excess → HTTP 403. | [Official]/[Forum]/[3rd-party] |
| **Backfill feasibility** | 500 stocks × ~2.5 years of 1-min (30-day chunks ≈ 30 requests each) ≈ 15,000 requests → ~2–3 h at a conservative 2 req/s; daily history for 2,000 stocks ≈ 2,000–4,000 requests. Feasible over one or two nights. | Calculated |
| **Live feed (WebSocket 2.0)** | Modes: LTP, Quote, Snap Quote (+ 20-level depth beta). **Max 3 concurrent connections per client code; 1,000 tokens per session**; tokens above the limit receive no ticks. | [Official] + moderator |
| **Market quote REST** | `getMarketData` (LTP/OHLC/FULL) — useful as a polling fallback; per-request token cap to verify. | [Official], cap unverified |
| **Authentication** | Login with client code + PIN + **TOTP** → `jwtToken`, `refreshToken`, `feedToken`. **Sessions are invalidated daily at midnight**; a fresh login is needed each trading day. | [Official] |
| **Static IP / SEBI retail-algo rules** | From **1 Apr 2026** (transition from Aug 2025), a registered static IP is required **only for order place/modify/cancel and GTT**. Login, quotes, historical and WebSocket work from any IP. | [Official] notice + forum |
| **Instrument master** | `OpenAPIScripMaster.json` at `margincalculator.angelbroking.com` (fields: token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size). Tokens stay fixed for an instrument's life. **Current instruments only — no delisted history** (survivorship risk). Occasional outages (returned null). | [Forum] |
| **Portfolio APIs** | `getHolding`, `getAllHolding` (holdings + summary), `getPosition`, funds/RMS. Reported data defects (null symbol/token on a holding; a holding the user didn't own). | [Official]/[Forum] |
| **Usage restrictions** | Free API for the account holder. Redistribution of exchange data is governed by exchange policy. Market data must not be republished; fine for personal use. | Inferred; verify terms |
| **What it does NOT provide** | Delivery data, corporate actions/adjustment metadata, fundamentals, announcements, FII/DII data, delisted/symbol-change history, guaranteed tick-by-tick data. | — |

**Assessment.** Angel One is a good **initial** source for: live quotes for up to ~1,000
instruments (3,000 across 3 connections), recent intraday history, current instrument
tokens and (optionally) read-only holdings, all at ₹0. It is **not sufficient alone** for:
authoritative long daily history, delivery %, corporate actions, survivorship-free universes,
or point-in-time fundamentals. Those must come from exchange sources.

### D1.2 Provider comparison

| | **Angel One SmartAPI** | **Zerodha Kite Connect** | **DhanHQ** | **Upstox API** | **Commercial vendors (TrueData, Global Datafeeds, etc.)** | **NSE/BSE official archives** |
|---|---|---|---|---|---|---|
| Account needed | Yes (you have it) | Zerodha account | Dhan account | Upstox account | No broker account | No |
| Cost (data) | **₹0** [Official] | **₹500/month** for data; free "Personal" tier has **no** market/historical data [Official] | **₹499 + GST/month** Data API (an older waiver for ≥25 trades per 30 days may have ended) [Official/3rd-party] | APIs reported free; V3 WebSocket reportedly **Plus plan only** [Forum, conflicting] | Quote-based; TrueData ≈ ₹2,600–4,000/month in a 2024 Fyers notice, plus exchange fees [3rd-party] | Free to download; NSE Data Usage Policy applies |
| Daily history | ~1990 onward (reported) | Since 1990 for some NSE stocks, BSE since 2008 [Forum] | Yes | Since Jan 2000 (V3) [Official] | Vendor-dependent, typically deep | Bhavcopy archives, many years (**authoritative**) |
| Intraday history | 1-min, 30 days per request; reported from 2016 | Minute data reported from ~2015; 60 days per request [Forum] | **5 years of intraday for all NSE/BSE instruments** (active contracts) [Official] | Intraday from Jan 2022 (V3) [Official] | 1-min/tick, deeper; licensed | Not available free |
| Live feed | WS 2.0, 1,000 tokens × 3 connections | WS, limits to verify (forum figures conflict) | WS feed; limits not found | WS V3 (plan-gated per forum) | Authorized real-time feeds | None |
| Delivery % | No | No | No | No | Some vendors | **Yes** (`sec_bhavdata_full`) |
| Corporate actions | No | No | No | No | Some vendors | **Yes** (exchange corporate-action data) |
| Fundamentals | No | No | No | No | Some vendors (separate products) | Filings/XBRL with broadcast timestamps |
| Licensing clarity | Personal use OK; no redistribution | Same | Same | Same | **Best** (authorized vendor contracts) | Personal/research OK under policy; redistribution restricted |
| Fit for MARKET SAGE | **Primary live + recent intraday (free)** | Good alternative, ₹500/month, needs a new account | **Best add-on for intraday depth** (5 years) | Weaker fit (2022 intraday floor, plan ambiguity) | Later, only if a validated strategy needs ticks/licensed depth | **Authoritative EOD, delivery, corporate actions** |

### D1.3 Recommendation

**Use multiple sources, each assigned a role. Total initial cost: ₹0.**

| Data role | Primary source | Secondary / reconciliation | Notes |
|---|---|---|---|
| EOD daily OHLCV (research truth) | **NSE bhavcopy** (UDiFF / `sec_bhavdata_full`) | Angel daily candles | Exchange file is the source of record. |
| Delivery qty/% | **NSE `sec_bhavdata_full`** | — | No broker supplies this. |
| Corporate actions & adjustment | **NSE/BSE corporate-action data** | Empirical check of Angel candles | Adjustment factors computed by us and versioned. |
| Instrument universe, symbol history, delistings | **NSE/BSE security lists + bhavcopy history** | Angel scrip master (token map) | Prevents survivorship bias. |
| Intraday history | **Angel SmartAPI** | DhanHQ (later, if 5-year depth is needed) | Depth limited; backfill within limits. |
| Live quotes/ticks | **Angel WebSocket 2.0** | Angel `getMarketData` polling fallback | Monitoring service only. |
| Holdings/positions | **Manual entry / CSV import** first | Angel `getHolding` (read-only), optional | See key-scope note below. |
| Fundamentals/announcements | NSE/BSE filings (D3) | — | Point-in-time by broadcast timestamp. |

**Postpone** Kite Connect, DhanHQ, Upstox and commercial vendors. Add DhanHQ (₹499/month) only
if Angel's intraday depth proves insufficient for a model that has *already* shown value on daily data.

**Key-scope safeguard.** Use Angel keys for market data / historical only, if the SmartAPI dashboard
offers separate app types (to verify in M1). A trading-scope key would technically permit orders.
Holdings sync is optional because manual entry satisfies the spec ("user-confirmed positions").

### D1.4 Broker-independent data adapter (long-term architecture)

Analytical engines never see broker tokens, broker JSON or broker limits. They consume only
canonical objects keyed by MARKET SAGE `instrument_id`.

```
analysis / features / models / monitoring
                │  canonical Bar, Quote, Tick, CorporateAction, Holding (instrument_id, UTC ts)
     ┌──────────▼──────────────────────────────┐
     │ MarketDataService (router by data role) │  ← provider_roles config
     │  • capability-aware chunk planner       │
     │  • per-provider rate limiter            │
     │  • quality checks + provenance stamping │
     │  • cross-provider reconciliation        │
     └───┬──────────┬──────────┬──────────┬────┘
         ▼          ▼          ▼          ▼
   NseArchive   AngelOne    Fixture    (DhanHQ / Kite / Upstox / vendor later)
   Adapter      Adapter     Adapter
```

Interfaces (Python `Protocol`s, defined in M0/M2):

- `ProviderCapabilities` — exchanges, intervals, max days per request per interval, earliest
  date per interval, live modes, max subscriptions/connections, rate limits, data roles,
  `realtime | delayed | eod`. **Declared as data and validated by tests**, so limits are changed
  in one place.
- `InstrumentSource.list_instruments()` → provider instruments, mapped by a
  `provider_instrument_map` table (`provider, provider_token, exchange, symbol, isin,
  valid_from, valid_to → instrument_id`). Changing broker = new mapping rows, no engine change.
- `HistoricalBarSource.fetch_bars(instrument_id, interval, start, end)` → canonical bars with
  `source_ts`, `received_ts`, `provider`, `raw_file_id`, `adjusted=false`.
  Adjustment is always done by our own L2 layer, never assumed from a provider.
- `LiveFeedSource.subscribe(instrument_ids, mode)` → async stream of canonical `Quote/Tick`
  plus `FeedStatus` (connected, latency, stale) events.
- `AccountSource` (read-only) → holdings, positions, funds.
- `SessionManager` per provider — Angel: TOTP login before market open, re-login after
  the midnight invalidation, token refresh, health checks; secrets read from a secret store only.

**Execution is disabled by design:**
- No live-order adapter exists in the codebase. The only `ExecutionVenue` implementation is
  `PaperBroker` (simulated fills with costs, slippage, missed fills).
- Config `EXECUTION_MODE` accepts only `paper`; startup fails on any other value.
- An automated test fails the build if order endpoints (e.g. `placeOrder`, `modifyOrder`,
  `cancelOrder`, GTT) are referenced anywhere in the codebase.

### D1.5 Long-term impact
- The adapter layer and `provider_instrument_map` are designed in M0–M2. Adding DhanHQ/Kite
  later is an adapter plus a capability declaration, with no engine changes.
- Because exchange files are the research source of record, models are not tied to one
  broker's adjustment or history quirks.
- Angel's 1,000-token-per-connection limit bounds the live-monitored universe (≈1,000–3,000
  instruments). Enough for a liquid universe plus positions; the backend universe-selection
  layer must respect it.
- The daily TOTP login means the server holds the TOTP secret. This is a sensitive credential
  that needs secret-store handling, least-privilege access and an audit log. It can be avoided
  by doing the daily login yourself, at the cost of automation.

---

## D2 — Network access and data-fetch location

**Situation.** This cloud development environment blocks NSE, BSE and Angel One hosts.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| A. Allow specific hosts in this cloud dev environment | Lets me verify docs and test public NSE/BSE downloads during M1–M2 | Broker credentials would sit in a cloud dev environment | ₹0 |
| B. Run all real fetching on your machine/VM only; cloud sessions use fixtures | Credentials never leave your infrastructure | Slower verification loop; I can't confirm live behaviour myself | ₹0 |
| C. Hybrid (**recommended**) | Public, credential-free sources (NSE/BSE archives, Angel docs, public scrip master) allowed in cloud dev; **Angel login/feeds tested only on your VM/machine** | Two environments to keep aligned | ₹0 |

Hosts to allow for option C (exact list confirmed in M1): `www.nseindia.com`,
`nsearchives.nseindia.com`, `www.bseindia.com`, `api.bseindia.com`,
`smartapi.angelone.in`, `smartapi.angelbroking.com`, `margincalculator.angelbroking.com`.

**Risk.** NSE is known to throttle/block automated and datacenter traffic. The NSE adapter needs
polite rate limits, retries, session/cookie handling and a fallback (BSE files / Angel daily
candles flagged as secondary).

**Can it be postponed?** Until M1 begins. Not needed for M0.

---

## D3 — Fundamentals and corporate events (point-in-time)

| Option | Pros | Cons | Cost |
|---|---|---|---|
| A. NSE/BSE filings: announcements, financial results (PDF + XBRL), shareholding, corporate actions | Primary source; broadcast timestamps give true point-in-time availability; free | XBRL parsing effort; format changed (Integrated Filing from Mar-2025 quarter); no revision history, so we must snapshot at ingestion | ₹0 + engineering |
| B. Scraping aggregator sites (Screener, Tijori, etc.) | Easy, clean ratios | No official API; terms-of-service risk; usually not point-in-time (restated values) — **violates PIT requirement** | ₹0 — **not recommended** |
| C. Licensed fundamentals (CMIE Prowess, ACE Equity, Capitaline, vendor APIs) | Clean history, PIT options in some products | Institutional pricing (typically far above personal budgets — quotes needed) | High / quote |

**Recommendation.** Option A, scoped to the liquid universe. Store raw filings and broadcast
timestamps from day one of ingestion. Early models use price/volume/delivery/regime features.
Fundamentals enter as features only once a PIT history exists and adds measurable value.
Revisit C only if the product ever becomes commercial.

**Postpone until M4.** **Long-term impact:** the `fundamental_filings` / `announcements` schemas
(with `published_at`) are created in M2. The analyst thesis shows "fundamentals: unknown" until
data exists, rather than inventing values.

---

## D4 — Intended audience and regulatory scope

**Decided by owner:** personal use + paper trading.

| Implication | Design consequence |
|---|---|
| No advice is distributed to others | SEBI Research Analyst / Investment Adviser registration is not triggered by personal use (legal review required before any sharing). |
| No orders placed | SEBI/NSE retail-algo rules (static IP, algo registration above ~10 orders/sec, daily 2FA) do not apply to order flow. Data login still uses TOTP. |
| Exchange data | Personal, non-redistributed use only. No public dashboards or sharing of raw/derived exchange data. |
| Still internet-exposed | Single-user authentication (strong password + TOTP, or private VPN/tunnel access), HTTPS, audit log. |
| Single user | Schemas stay multi-user-capable (`user_id` columns) at negligible cost, but no tenancy features. |

**Long-term impact:** enabling live execution or sharing with others later is a **separate
milestone** with legal review, static IP registration, algo-registration checks, an execution
adapter, kill-switches and order audit. The architecture leaves a slot for it but implements
nothing now.

---

## D5 — Hosting (always-on, cost-conscious)

The backend must run ~08:30–16:30 IST on trading days at minimum (pre-open login, session,
post-close reconciliation, EOD ingestion, evaluations). Running 24×7 is simpler and supports
nightly jobs and push delivery.

| Option | Spec | Approx. cost/month | Pros | Cons |
|---|---|---|---|---|
| Your PC/laptop | — | ₹0 | Free | Fails the requirement (off when you are away) |
| **Oracle Cloud Always Free (Mumbai)** | Up to 4 ARM OCPU / 24 GB RAM, 200 GB block storage | **₹0** | Very generous; Mumbai region | Mumbai capacity often unavailable; idle free instances can be reclaimed; Indian card sign-up issues reported; ARM (Python wheels generally available) |
| **AWS Lightsail (Mumbai)** | 2 GB / 60 GB → 4 GB / 80 GB | ≈ $12 → $24 (≈ ₹1,000–2,100) [3rd-party] | Predictable price, static IP, snapshots, Mumbai latency | Paid; 2 GB is tight for Postgres + workers |
| DigitalOcean (Bangalore BLR1) | 2–4 GB droplets | ≈ $12–24 | Simple, India region | Similar cost to Lightsail |
| Indian VPS providers | varies | ≈ ₹500–1,500 | UPI/GST billing | Variable reliability/support |
| Hetzner (EU) | 2–4 vCPU / 4–8 GB | ≈ €4–8 | Cheapest | No India region (~120–150 ms); fine for swing, less ideal for live feed |

**Resource estimate (planning, to be measured):** Postgres + Parquet for daily bars (~2,000
stocks × 20 years) is under 1–2 GB. 1-min bars for ~500 stocks × 2–5 years is a few GB to tens of
GB compressed. 4 GB RAM / 2 vCPU / 80 GB disk is enough for API + monitor + workers + Postgres.
Heavy model training can run on your laptop or temporarily on the VM.

**Recommended setup (phased):**
1. **M0–M8:** no always-on host needed. Develop in cloud sessions and on your machine.
2. **From M9 (monitoring):** one Mumbai VM running docker-compose (Postgres, API, worker,
   monitor, web). Try **Oracle Always Free** first (₹0). If capacity is unavailable or reliability
   is poor, use **Lightsail 4 GB (~$24)**.
3. **Reliability add-ons (₹0–₹100):** nightly encrypted `pg_dump` + Parquet sync to object
   storage. An external **dead-man's-switch heartbeat** (e.g. healthchecks.io / UptimeRobot free
   tiers) pages your phone if the monitor stops, because a silent monitor is the worst failure
   mode. Access via HTTPS behind a VPN/tunnel (e.g. Tailscale/Cloudflare Tunnel free tiers) or
   strong auth.

**Postpone until M9.** **Long-term impact:** everything is containerised and configured by
environment variables from M0, so moving between providers is a redeploy, not a rewrite.
A fixed VM IP can later double as the registered static IP if execution is ever approved.

---

## D6 — Frontend framework

| Option | Pros | Cons |
|---|---|---|
| **React + TypeScript + Vite PWA** | Simple static build served by FastAPI/nginx; strong PWA/Web Push support; no extra server | Client-side rendering only (fine for a single-user app) |
| Next.js | SSR, routing conventions | Extra Node server or export constraints; unnecessary alongside FastAPI |
| Server-rendered (Jinja/HTMX) | Minimal JS, very simple | Weaker for live WebSocket views, PWA/push and rich stock charts |
| Flutter / native | Native push | Spec says PWA first; much more effort |

**Recommendation:** React + TypeScript + Vite PWA. **Can be postponed to M11.** M0 only creates
a placeholder `frontend/` folder (or none). **Long-term impact:** the API is the contract
(OpenAPI-generated TS types), so a native app could be added later without backend changes.

---

## D7 — Risk defaults (paper trading)

Proposed defaults, all user-configurable and stored as versioned settings with each
recommendation (so evaluation knows which rules applied):

| Parameter | Proposed default | Rationale |
|---|---|---|
| Risk per trade (loss at stop incl. costs/slippage) | **1% of capital** (Balanced 0.75%, Growth 1%) | Standard capital-preservation sizing |
| Max concurrent positions | **5** | Keeps monitoring/attention manageable |
| Max capital per position | **30%** (Balanced 25%) | Concentration control |
| Max per sector | **40%** | Correlation control |
| Daily loss limit (paper) | **2%** of capital → no new entries that day | Circuit breaker |
| Weekly drawdown limit | **5%** → new entries paused pending review | Circuit breaker |
| Min cash reserve | **10%** | Cash is a valid allocation |
| Liquidity floor | 20-day median turnover ≥ **₹5 crore**; position ≤ **1% of ADV**; price ≥ **₹20** | Avoid illiquid/penny/manipulated names |
| Minimum reward:risk to T1 (net of costs) | **1.5** | Filters poor setups |
| Leverage / derivatives / shorting | **Disabled** | Out of scope |

**Important honesty point about the ₹500/day aspiration.** ₹500/day ≈ ₹1.2 lakh/year
(~245 sessions). On ₹20,000 that is ~600% a year; on ₹1,00,000 ~120%; on ₹5,00,000 ~24%.
At 1% risk per trade on ₹20,000 the maximum planned loss per trade is ₹200, and fixed delivery
costs (e.g. DP charges per sell) take a meaningful share of small trades. The Performance screen
will show this gap explicitly; the allocator will never raise risk to chase it.

**Can be finalised by M7** (defaults suffice before then). **Long-term impact:** risk settings
are versioned inputs to every recommendation in the ledger, so changing them never rewrites
history.

---

## Summary — what needs your decision now vs later

| Decision | Recommendation | Needed by | Postponable? |
|---|---|---|---|
| D1 Data/broker | Angel SmartAPI (live, intraday, tokens) + NSE/BSE official files (EOD, delivery, corporate actions, universe); manual holdings; no paid provider yet; broker-independent adapters; execution disabled | Before M1 | No — but M0 does not depend on it |
| D2 Network | Hybrid: allow public NSE/BSE/Angel-docs hosts in cloud dev; credentials only on your machine/VM | Before M1 | Yes, until M1 |
| D3 Fundamentals | NSE/BSE filings, PIT by broadcast time; no scraping | M4 | Yes |
| D4 Audience | Personal use + paper trading (**decided**) | — | Decided |
| D5 Hosting | None until M9; then Oracle Always Free Mumbai, else Lightsail 4 GB; heartbeat + backups | M9 | Yes |
| D6 Frontend | React + TS + Vite PWA | M11 | Yes |
| D7 Risk defaults | Table above | M7 | Yes (defaults OK) |

**M0 itself is provider-, host- and frontend-agnostic.** It can start as soon as you approve,
even with D3/D5/D6/D7 still open.

---

## Sources consulted (via web search; primary pages blocked from this environment)

- Angel One SmartAPI docs: https://smartapi.angelbroking.com/docs · FAQ: https://smartapi.angelbroking.com/faq · Exchange regulations: https://smartapi.angelbroking.com/exchange-regulations
- Angel One notice: https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- SmartAPI forum: historical limits https://smartapi.angelone.in/smartapi/forum/topic/4845/max-days-in-historical-data · rate limits https://smartapi.angelone.in/smartapi/forum/topic/4387/changes-in-api-rate-limit · WebSocket limits https://smartapi.angelone.in/smartapi/forum/topic/4391/websocket-streaming-size-and-max-connections · SEBI updates https://smartapi.angelone.in/smartapi/forum/topic/5254/important-updates-to-smartapi-in-compliance-with-sebi-guidelines · holdings https://smartapi.angelone.in/smartapi/forum/post/14240 · data depth https://smartapi.angelbroking.com/topic/4393/how-many-years-of-historical-data-we-get-for-nifty-and-stocks/8
- Zerodha: https://support.zerodha.com/category/trading-and-markets/kite-api/articles/what-are-the-charges-for-kite-apis · https://kite.trade/forum/discussion/15111/historical-data-limit-60-days · https://kite.trade/forum/discussion/8899/rate-limit-of-kite-connect-historical-data-api-and-lookback
- DhanHQ: https://dhanhq.co/docs/v2/historical-data/ · https://dhanhq.co/docs/v2/releases/ · https://madefortrade.in/t/enhanced-dhanhq-data-apis-with-more-data-and-higher-rate-limits/50328
- Upstox: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data · https://upstox.com/developer/api-documentation/announcements/enhanced-historical-candle-data-apis-v3
- TrueData: https://www.truedata.in/market-data-apis · https://fyers.in/notice-board/revision-in-truedata-subscription-pricing/
- NSE data policy: https://www.nseindia.com/market-data/nse-data-policy · https://github.com/chartiny/nse-sec-bhavdata-full
- SEBI retail algo framework coverage: https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/ · https://www.angelone.in/news/market-updates/sebi-introduces-new-regulations-for-retail-algo-trading-to-enhance-market-safety
- Hosting: https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm · https://vpscatalog.pages.dev/comparisons/aws-lightsail-vs-digitalocean/
