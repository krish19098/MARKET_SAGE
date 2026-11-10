# MARKET SAGE — Product Architecture and Implementation Roadmap

> **Status: PROPOSAL awaiting owner review.** Nothing described here is implemented yet.
> The live record of what actually exists is `PROJECT_STATE.md`. The authoritative
> requirements are in `.claude/skills/market-sage/references/`.

---

## 1. Product summary (as understood)

MARKET SAGE is an independent, evidence-driven decision-support system for Indian cash
equities (NSE first, supported BSE), primarily for swing trading with intraday exits when a
thesis fails or a target is hit. It must:

1. Build a licensed, point-in-time, provenance-tracked market data warehouse.
2. Investigate stocks like a disciplined senior analyst (structure, indicators, patterns,
   volume/liquidity, risk/execution, market/sector/fundamental context, historical analogues).
3. Produce calibrated probabilistic forecasts with defined targets, horizons and cutoffs,
   validated chronologically against baselines, net of costs.
4. Convert forecasts into BUY / HOLD / EXIT / AVOID decisions only through a separate
   risk/decision layer — with entry range, invalidation, targets, quantity, costs, R:R,
   horizon, uncertainty and thesis — and suppress them when data is stale or risk is
   incalculable.
5. Allocate any user budget across the strongest eligible opportunities (Balanced / Growth),
   with cash as a valid outcome.
6. Monitor markets and positions server-side continuously; alert with explicit
   early-warning / approaching / confirmed semantics.
7. Record every prediction immutably, link all later information as events, and score
   itself honestly across direction, timing, targets, stops, lead time, false alerts,
   calibration and net value — separating counterfactual from confirmed P&L.
8. Improve only through controlled, walk-forward-validated candidate models with a
   promotion gate and rollback.
9. Run without any conversational AI service, behind a five-screen responsive PWA:
   Home, Invest, My Trades, Analyst, Performance.

Hard constraints carried into every design decision: no fabricated data/performance, no
guaranteed returns (₹500/day is an evaluation aspiration only), advisory-only with
user-confirmed execution in the initial release, no leverage/derivatives/shorting in scope,
IST for display and UTC canonical storage, secrets never in source or frontend.

---

## 2. Current environment (inspected 2026-11-11 IST)

| Item | Finding | Implication |
|---|---|---|
| Repository | Single commit; only `README.md`. No code, tests, CI, or dependencies. | Greenfield. Nothing to preserve except README. |
| Branches | `main`, `claude/modest-keller-hl6arn` (working branch). | Work lands on the feature branch. |
| Python | 3.13.18, `uv` 0.11, `poetry` 2.4 available; pandas 3.0 / numpy 2.5 present system-wide. | Use `uv` with a project-local virtualenv and lockfile. |
| Node | v22, npm 10, pnpm 10. | Sufficient for a React/Vite PWA. |
| PostgreSQL | v16 client + server binaries installed; cluster exists but stopped. | Usable locally for dev/tests. |
| Redis | 7.0 available. | Not required initially (see §5.9). |
| Docker | 29.x client present. | `docker-compose` for reproducible Postgres in other environments. |
| Network | PyPI reachable. **`www.nseindia.com` and `nsearchives.nseindia.com` blocked (proxy 403)** in this cloud environment. | Real NSE ingestion cannot be tested here until those hosts are allowed. Development continues with clearly labelled fixtures. |
| Credentials | None configured. | All broker/data APIs are open dependencies. |

---

## 3. Architecture overview

```
                    ┌────────────────────────── Licensed sources ──────────────────────────┐
                    │ NSE/BSE archives (EOD)   Broker API (intraday/live)   Filings/fundamentals│
                    └───────────────┬──────────────────────┬───────────────────────┬────────┘
                                    │                      │                       │
                         ┌──────────▼──────────┐ ┌─────────▼─────────┐  ┌──────────▼─────────┐
                         │ Ingestion adapters  │ │ Live feed service │  │ Filings ingestion  │
                         │ (batch, backfill)   │ │ (stream/poll)     │  │ (pub. timestamps)  │
                         └──────────┬──────────┘ └─────────┬─────────┘  └──────────┬─────────┘
                                    ▼                      ▼                       ▼
     ┌─────────────────────────── Warehouse ─────────────────────────────────────────────┐
     │ L0 raw immutable files (+checksum, provenance) → L1 canonical → L2 adjusted series │
     │ → L3 point-in-time feature snapshots.  Postgres (metadata/ops) + Parquet (series)   │
     │ Quality engine: gaps, duplicates, OHLC checks, staleness, reconciliation            │
     └───────────────┬─────────────────────────────────────────────────────────┬────────┘
                     ▼                                                         ▼
     ┌──────────── Analysis engines ────────────┐              ┌──── Model platform ────────┐
     │ technical · patterns · volume/liquidity  │──features──▶ │ targets · baselines ·      │
     │ fundamentals · market context · regime   │              │ training · walk-forward ·  │
     │ historical analogues                     │              │ calibration · registry     │
     └───────────────┬──────────────────────────┘              └────────────┬───────────────┘
                     └──────────────────┬───────────────────────────────────┘
                                        ▼
                   ┌──────────── Decision & risk layer ─────────────┐
                   │ thesis builder · suppression gate · trade plan │
                   │ cost model · sizing · portfolio allocator      │
                   └──────────────────┬─────────────────────────────┘
                                      ▼
            ┌──────────── Prediction ledger (append-only, hash-chained) ────────────┐
            │ predictions · prediction_events · alerts · outcomes · corrections     │
            └───────┬─────────────────────┬──────────────────────────┬──────────────┘
                    ▼                     ▼                          ▼
          ┌──────────────────┐  ┌───────────────────┐     ┌──────────────────────────┐
          │ Monitoring svc   │  │ Evaluation engine │     │ Controlled learning      │
          │ state machine,   │  │ multi-horizon,    │────▶│ candidate train, gate,   │
          │ alert generation │  │ exit counterfact. │     │ promote/rollback         │
          └────────┬─────────┘  └───────────────────┘     └──────────────────────────┘
                   ▼
          ┌──────────────────┐        ┌─────────────────────────────────────────────┐
          │ Notification svc │───────▶│ FastAPI (REST + WebSocket) → React PWA      │
          │ Web Push + log   │        │ Home · Invest · My Trades · Analyst · Perf. │
          └──────────────────┘        └─────────────────────────────────────────────┘
```

All boxes run as backend processes. The browser/phone only reads state and receives alerts.

---

## 4. Proposed technology stack (for review)

| Concern | Proposal | Rationale / alternatives |
|---|---|---|
| Backend language | Python 3.13, `uv`-managed, single package `market_sage` | Matches spec; available locally. |
| API | FastAPI + Pydantic v2, Uvicorn | Spec; typed contracts shared with frontend via OpenAPI. |
| Operational DB | PostgreSQL 16, SQLAlchemy 2 + Alembic migrations | Spec; triggers enforce ledger immutability. |
| Time-series store | Parquet (pyarrow), partitioned `exchange/interval/year/...`; **DuckDB** for analytical reads | DuckDB queries Parquet in-process without a server — avoids an extra service. |
| Numerics / ML | pandas, NumPy, scikit-learn; LightGBM/XGBoost only after baselines; `hmmlearn` only if regime HMM is validated | Spec; "evaluate, not adopt by fashion". |
| Scheduling | APScheduler inside a dedicated worker process (EOD ingestion, evaluations, reports) | Lighter than Celery; no broker needed. |
| Live monitoring | Separate asyncio service consuming broker WebSocket / polling fallback | Isolated from API; restarts independently. |
| Event fan-out | PostgreSQL `LISTEN/NOTIFY` initially; Redis Streams only if throughput requires it | Spec: Redis "only where justified". |
| Frontend | React + TypeScript + Vite PWA (service worker, Web Push) | No SSR need; simpler than Next.js against a FastAPI backend. Next.js is the alternative if you prefer. |
| Charts | Lightweight charting only in the Analyst stock view | Home stays chart-free per UI spec. |
| Quality tooling | pytest, hypothesis (property tests for ledger/costs), ruff, mypy; ESLint + Vitest + Playwright for UI | Acceptance tests are executable. |
| Packaging/deploy | docker-compose (postgres, api, worker, monitor, web) on an always-on host | Backend must run when devices are offline. |
| Secrets | Environment variables / `.env` (git-ignored) locally; a secret manager in deployment | Never in source or frontend bundles. |
| Optional local LLM | Deferred; explanation-only, fed verified outputs | Must not originate any number. |

---

## 5. Module design

Proposed repository layout (created only after review):

```
backend/
  pyproject.toml  uv.lock  alembic/
  src/market_sage/
    core/           config, clock & IST/UTC handling, exchange calendar, ids, provenance
    data/
      providers/    adapter per source behind broker-independent protocols
                    (nse_archive, bse_archive, angelone, fixture; dhan/kite/upstox/vendor later)
      raw/          L0 immutable landing + checksums
      canonical/    L1 normalisation, instrument master, symbol history
      adjust/       L2 corporate-action adjustment
      quality/      gap/dup/OHLC/volume/staleness checks, reconciliation, reports
    features/       point-in-time feature computation and snapshot store (L3)
    analysis/       technical, patterns, volume, fundamentals, context, regime, analogues
    models/         targets, baselines, training, walk_forward, calibration, registry
    decision/       thesis, suppression gate, trade plan, recommendation
    portfolio/      costs, sizing, allocator, exposure/correlation
    execution/      PaperBroker only (simulated fills); no live-order adapter exists
    ledger/         append-only predictions, events, alerts, outcomes, corrections
    monitoring/     feed consumer, position/watchlist state machines, alert rules
    notifications/  web push, delivery log, retries
    evaluation/     horizon scoring, exit counterfactuals, error analysis, reports
    learning/       candidate datasets, promotion gate, rollback
    api/            FastAPI routers + WebSocket
    workers/        entrypoints: scheduler, monitor, notifier
  tests/            unit · integration · acceptance (the 20 mandatory tests) · fixtures
frontend/           React PWA (5 screens + stock/trade detail views)
infra/              docker-compose, env templates
docs/               this document, provider research, model cards, runbooks
```

### 5.1 Core: time, calendar, provenance
- All persisted timestamps `TIMESTAMPTZ` in UTC; conversion to `Asia/Kolkata` only at the API/UI edge.
- Every observation carries `source_ts` (exchange/event time) and `received_ts`.
- Exchange calendar: trading days, holidays, special/Muhurat sessions, pre-open
  (09:00–09:15) vs continuous session, closures. Sourced from exchange circulars and stored
  as versioned data, not code constants. An unknown calendar state is a suppression reason.
- A `Clock` abstraction so tests and backtests replay time deterministically (the basis of
  "no look-ahead" testing).

### 5.2 Market data & warehouse
- **Instrument master** with stable internal `instrument_id` independent of symbol/ISIN
  changes; `symbol_history` with validity intervals; delisting records (survivorship control).
- **Layers:** L0 raw files exactly as received (never modified, checksummed, with provider,
  URL/endpoint, licence tag, fetch time) → L1 canonical bars → L2 adjusted research series
  (adjustment factors stored and versioned; unadjusted always retained) → L3 feature snapshots.
- **Postgres tables (initial):** `instruments`, `symbol_history`, `corporate_actions`,
  `providers`, `ingestion_runs`, `raw_files`, `data_quality_issues`, `calendar_sessions`,
  `fundamental_filings` (with `published_at`), `announcements` (with `published_at`).
- **Parquet:** `bars/{exchange}/{interval}/{year}/{instrument_id}.parquet` (layout tuned
  after measuring data volume).
- **Quality engine:** duplicates, missing intervals vs calendar, out-of-order timestamps,
  OHLC consistency, non-negative/abnormal volume, corporate-action reconciliation,
  cross-provider reconciliation, retry/backoff/rate limiting, run logs. Gaps are flagged,
  never silently filled; each feature declares how it handles gaps.
- **Live vs final:** live ticks/candles stored separately from finalised candles; post-session
  reconciliation against provider history; feed latency and staleness recorded.

### 5.2a Broker-independent provider layer and execution policy (D1)
Full rationale is in `docs/DECISION_BRIEF_D1-D7.md` §D1.4.
- Analytical engines consume only canonical objects (`Bar`, `Quote`, `Tick`,
  `CorporateAction`, `Holding`) keyed by internal `instrument_id` with UTC timestamps.
  They never see broker tokens, payloads or limits.
- Provider protocols: `ProviderCapabilities` (limits declared as data), `InstrumentSource`,
  `HistoricalBarSource`, `LiveFeedSource`, `AccountSource` (read-only), `SessionManager`.
- `provider_instrument_map` (`provider, provider_token, exchange, symbol, isin, valid_from,
  valid_to → instrument_id`) isolates symbol/token schemes. Adding DhanHQ/Kite/Upstox later
  means adding an adapter plus mapping rows.
- `MarketDataService` routes by **data role** (EOD, delivery, corporate actions, universe,
  intraday, live, holdings, fundamentals) using a config table. It applies capability-aware
  chunking, per-provider rate limiting, provenance stamping and cross-provider reconciliation.
- Provider candles are stored unadjusted. Adjustment is always computed by L2 from exchange
  corporate-action data.
- **Execution disabled:** the only `ExecutionVenue` is `PaperBroker`. `EXECUTION_MODE` must be
  `paper` or startup fails. A build test fails if order/GTT endpoints are referenced in the
  codebase. Broker keys are requested with data-only scope where the broker supports it.

### 5.3 Analysis engines (analyst intelligence)
Each engine returns typed **evidence objects**: `{kind: fact|inference|estimate|unknown,
value, as_of, inputs, method_version}` so the thesis can keep the spec's
fact/inference/estimate/unknown separation and show disagreements.
- **Technical structure:** swing-point detection, HH/HL/LH/LL, trend strength/maturity,
  S/R and supply/demand zones, breakout/breakdown/retest/failure, gaps, range expansion,
  multi-timeframe alignment, relative strength vs NIFTY/sector.
- **Indicators:** SMA/EMA, RSI, Stochastic, MACD, Bollinger, ATR, ADX, VWAP (intraday only),
  momentum, volatility, trend persistence — implemented in-house with reference tests
  (no opaque TA dependency), thresholds treated as validated parameters.
- **Patterns:** candlestick and chart patterns with context (trend, location, volume,
  confirmation) and an empirically measured base rate / failure rate from history.
- **Volume & liquidity:** relative volume, volume-price divergence, delivery %, volume
  profile, acceptance/rejection, liquidity filters (turnover, impact cost proxy).
  Inferred institutional activity always labelled as inference.
- **Fundamentals:** growth, debt, cash flow, ROE/ROCE, valuation vs peers and own history,
  value-trap checks — strictly point-in-time by `published_at`.
- **Market context & regime:** index/sector trend and breadth, volatility, FII/DII by
  publication date; regime classifier (bull/bear/sideways/high-vol/low-vol/transition) with
  uncertainty and timestamp correctness.
- **Historical analogues:** normalised feature vectors, kNN (and DTW/clustering if validated),
  regime-conditioned; output sample size, period, method, forward-return distribution,
  MFE/MAE and failure frequency at 1/3/5/10/20 sessions. Search restricted to data strictly
  before the query date.

### 5.4 Prediction engine
- **Forecast contract** (persisted per model): universe, prediction timestamp, feature cutoff,
  target definition, horizon, price convention, costs/slippage, baseline, train/validation
  windows, calibration method, no-forecast conditions.
- **First target (proposal):** daily-bar, decision at post-close cutoff, liquid universe;
  label = which of {ATR-scaled upper barrier, ATR-scaled lower barrier, time-out} is hit
  first within 5 sessions, executable at next session's open (triple-barrier). Additional
  horizons (1/3/10/20, intraday) added only when data supports them.
- **Model ladder:** no-trade baseline → simple rule baselines (momentum/trend) → logistic
  regression → random forest → gradient boosting → regime-conditioned/ensemble. Each step
  must beat the previous net of costs out-of-sample to be kept.
- **Validation:** chronological splits, expanding/rolling walk-forward with purging and
  embargo, regime-sliced metrics, ablations, calibration (isotonic/Platt) with reliability
  curves and Brier/log-loss. Probabilities are shown to users only with calibration evidence;
  otherwise displayed as uncalibrated ranks.
- **Early opportunity discovery:** setup detectors (RS improvement, volatility contraction,
  developing breakout/breakdown, momentum shift, volume anomaly, support reversal, sector
  leadership change, event-driven) with lifecycle `early → developing → confirmed →
  invalidated`; lead time and false-alert rate measured per detector.
- **Model registry:** artefact, training data hash, feature-set version, code version,
  metrics, status (`candidate|production|retired`), with one production model per target.

### 5.5 Decision & risk layer
- Consumes forecasts + evidence; never trusts a model output alone.
- **Suppression gate** (runs first): stale/missing data, unknown calendar state, illiquidity,
  uncomputable stop/risk, failed quality checks, uncalibrated model where probability needed.
  Suppressions are logged with reasons (they are evaluable decisions too).
- **Trade plan:** entry range/trigger, invalidation level & condition, T1/T2, partial-booking
  rule, expected holding range, R:R, expected value net of costs, gap/slippage disclosure.
- **Thesis:** the 13-section format from the analyst spec, including bull/bear/neutral cases,
  "what would change the view" and "why selected over alternatives".

### 5.6 Portfolio allocation
- Inputs: capital, mode (Balanced/Growth), current holdings, max positions, per-trade risk %,
  daily loss limit, sector caps.
- Process follows the 10-step spec: rank by validated risk-adjusted expectancy → feasibility
  → risk-budget sizing `qty = floor(risk_budget / (entry − stop + per-share costs/slippage))`
  capped by capital, liquidity (% of ADV) and exposure → correlation/sector constraints
  (greedy with penalty, upgradeable to an optimiser) → reserve cash.
- **Cost model:** versioned, effective-dated charge schedule (brokerage, STT, exchange
  transaction charges, SEBI fees, stamp duty, GST, DP charges, slippage) for delivery and
  intraday; values loaded from verified broker/exchange documents, never assumed.
- Outputs every field required by the spec, plus rejected candidates with reasons and
  portfolio-level downside. Empty allocation (100% cash) is a first-class result.
- **User positions:** manual entry of actual fills, clearly flagged `actual` vs
  `hypothetical`; recommendations are never assumed executed.

### 5.7 Prediction ledger (accountability core)
- `predictions` — one immutable row per decision with all fields required by the
  self-evaluation spec, the full input snapshot reference (feature snapshot ID + data
  cutoff), model/feature/strategy versions, provenance and a `content_hash`.
- `prediction_events` — append-only linked events (price updates, alerts, HOLD/EXIT
  reassessments, outcomes, user confirmations, corrections) each with `prev_hash`,
  forming a tamper-evident hash chain.
- **Enforcement:** Postgres triggers reject `UPDATE`/`DELETE` on ledger tables; the
  application role has `INSERT`/`SELECT` only; a verification job recomputes the chain.
- Corrections are new audited events referencing what they correct.

### 5.8 Monitoring service
- Always-on asyncio process: consumes broker stream (polling fallback), finalises candles,
  updates intraday features, evaluates active positions and watchlists.
- Per-position **state machine** (`normal → early_warning → approaching_stop/target →
  triggered → closed`) with hysteresis, cooldowns and deduplication so insignificant
  fluctuations do not alert, but transitions always do.
- All 12 alert classes from the spec; each alert records creation time, data cutoff, forecast,
  probability/confidence, evidence, invalidation and later event time (for lead-time scoring).
- Fail-safe: stale feed/disconnect/uncertain calendar → data-outage alert + suppression of
  dependent decisions; heartbeats and staleness exposed to the UI.

### 5.9 Notifications
- Web Push (VAPID) via the PWA service worker initially; in-app alert history is the reliable
  record. Every attempt logged with status, retries, failures and acknowledgement.
- Channel interface allows later native app / other channels without changing alert logic.

### 5.10 Evaluation engine
- Scores each prediction at applicable horizons (intraday, 1/3/5/10/20 sessions) and at trade
  closure, using only finalised data after the prediction.
- Separate metrics: direction, entry timing, exit timing, target estimation, stop quality,
  early-warning lead time, false positive/negative alert rates, calibration (Brier/log loss,
  reliability), net performance — with sample sizes and confidence intervals.
- **Exit counterfactuals:** loss avoided and upside missed computed separately with stated
  assumptions; confirmed savings only where actual fills exist.
- **Error analysis:** structured lesson record per completed forecast with error cause
  taxonomy (data/feature/regime/model/execution/risk/event/unknown); "earlier warning
  possible?" replayed using the point-in-time feature store only.

### 5.11 Controlled learning
- Versioned evaluation datasets built from completed outcomes.
- Candidate training isolated from production; evaluated on chronologically later unseen
  data with walk-forward; compared with production and baselines on calibration, stability,
  drawdown and net performance.
- **Promotion gate** with thresholds defined *before* evaluation and stored with the run;
  failing candidates are rejected and production remains untouched; prior production
  retained for one-step rollback. No per-trade retraining.

### 5.12 API & UI
- REST for screens, WebSocket for live status/alerts; every payload carries data-status
  (`live | delayed | stale | simulated | historical`) and IST timestamps.
- Five screens exactly as specified; stock/trade detail views hold charts and the full thesis.
  Status never conveyed by colour alone; BUY/HOLD/EXIT/AVOID shown with uncertainty.
- Advisory disclaimer on Invest; no "safe"/"guaranteed" language anywhere.

---

## 6. Requirement traceability

| Requirement area | Modules | Milestone(s) | Acceptance tests (VALIDATION_TESTING §) |
|---|---|---|---|
| Market data, calendar, quality, point-in-time | core, data, features | M1–M3 | 15, 20 + operational QA |
| Analyst intelligence (5 categories, context, thesis) | analysis, decision | M4 | — (unit/reference tests) |
| Historical analogues | analysis.analogues | M5 | look-ahead tests |
| Predictive intelligence & early discovery | models, analysis | M6 | 3, 4 |
| Decision, risk, costs, allocation | decision, portfolio | M7 | 13, 14, 15 |
| Immutable ledger | ledger | M8 | 1, 2, 5 |
| Continuous monitoring & alerts | monitoring | M9 | 3, 4, 16 |
| Notifications | notifications | M9 | 17 |
| Self-evaluation & exit counterfactuals | evaluation | M10 | 6, 7, 8, 9, 10 |
| Controlled learning | learning, models | M10 | 11, 12 |
| UI (5 screens, PWA) | api, frontend | M11 (thin views earlier) | 18, 19 |
| Paper trading, hardening, deployment | all | M12 | 16, 19, 20 + release workflow |

---

## 7. Implementation roadmap

Each milestone is a **runnable, tested vertical increment**, not a mock. A milestone is only
marked complete in `PROJECT_STATE.md` with test evidence.

| # | Milestone | Key deliverables | Exit criteria | External dependency |
|---|---|---|---|---|
| **M0** | Foundation | Repo layout, `uv` project, lint/type/test tooling, CI, docker-compose Postgres, Alembic baseline, config & secrets handling, `Clock`/IST utilities | CI green; secret-scan test in place | None |
| **M1** | Data provider verification | Initial comparison done (`docs/DECISION_BRIEF_D1-D7.md`). M1 re-verifies Angel SmartAPI limits/depth/adjustment and NSE/BSE file formats against live docs **and test calls**; licensing notes, credentials checklist, coverage matrix | Verified capability declarations for Angel + NSE adapters | Hosts allowed (D2); Angel credentials on owner's machine |
| **M2** | Instrument master, calendar, EOD ingestion | Instrument/symbol history, calendar, NSE bhavcopy adapter (+ fixture adapter), L0/L1 storage, quality engine & report, corporate actions & L2 adjustment | Backfill of real EOD data with quality report; gaps flagged | Network access to NSE archives |
| **M3** | Point-in-time feature store | Feature definitions with availability rules, snapshot store, leakage tests | Replay test proves no future data in any feature | M2 data |
| **M4** | Analysis engines | Technical, indicators (reference-tested), patterns with base rates, volume/liquidity, market context/regime, fundamentals (PIT), evidence objects, thesis builder | Thesis generated for real instruments with traceable evidence | Fundamentals source (M1) |
| **M5** | Historical analogue memory | kNN analogue engine, outcome distributions, MFE/MAE, sample-size reporting | Analogue search provably excludes future data | M3 |
| **M6** | Prediction engine | Forecast contracts, first target, baselines, walk-forward framework, calibration, model registry, early-setup detectors | Out-of-sample report vs baselines net of costs (honest, even if negative) | M3–M5 |
| **M7** | Decision, risk & allocation | Suppression gate, trade plans, versioned cost model, sizing, allocator (Balanced/Growth), user positions | Acceptance tests 13, 14, 15 pass | Verified charge schedule |
| **M8** | Immutable ledger | Ledger tables, triggers, hash chain, event linking, correction events | Acceptance tests 1, 2, 5 pass; tamper test fails as expected | M7 |
| **M9** | Monitoring & notifications | Live feed adapter, candle finalisation, state machines, 12 alert classes, Web Push, delivery log, outage fail-safe | Tests 3, 4, 16, 17 pass on replayed/live feed | Broker API credentials |
| **M10** | Evaluation & controlled learning | Horizon scoring, exit counterfactuals, error analysis, reports, candidate training, promotion gate, rollback | Tests 6–12 pass | M8 history |
| **M11** | UI (PWA) | Home, Invest, My Trades, Analyst, Performance + detail views, WebSocket, data-status labelling | Tests 18, 19 pass; Playwright smoke | M7–M10 APIs |
| **M12** | Paper trading & hardening | Paper-trading simulator with realistic fills, operational QA (outages, holidays, restarts, migrations, rollback, timezones), deployment & runbooks, regulatory review | Paper-trading period recorded; release workflow checklist complete | Hosting; regulatory review |

**Sequencing note.** To avoid building layers in isolation, the first end-to-end path will be
the **EOD daily slice**: real bhavcopy data → features → baseline forecast → trade plan with
costs and sizing → ledger entry → horizon evaluation → API → minimal screens. Intraday and
live monitoring (M9) depend on a broker data feed and are layered on afterwards.

---

## 8. Dependencies, blockers and decisions needed from you

| # | Decision / dependency | Why it matters | Recommendation |
|---|---|---|---|
| D1 | **Data sources and broker integration** — *updated 2026-11-11, pending final approval* | Determines intraday depth, live feed, licensing, cost | **Angel One SmartAPI** (free; owner's broker) as the initial integration for live WebSocket quotes, recent intraday history, instrument tokens and optional read-only holdings. **NSE/BSE official files** as source of record for EOD OHLCV, delivery %, corporate actions and the survivorship-free universe. Holdings by manual entry first. No paid provider initially; DhanHQ (5-year intraday, ~₹499/month) is the first add-on candidate. Everything sits behind broker-independent adapters (§5.2a). Real-money execution disabled. Angel figures still need verification in M1. Details: `docs/DECISION_BRIEF_D1-D7.md`. |
| D2 | **Network access in this cloud environment** (see brief §D2: hybrid recommended) to `www.nseindia.com`, `nsearchives.nseindia.com` (and BSE equivalents) | Currently blocked (HTTP 403 from proxy); real ingestion cannot be tested here | Allow these hosts when we reach M2, or run ingestion from your own machine/server. |
| D3 | **Fundamentals source with publication timestamps** | Point-in-time fundamentals are required and hard to source free | Evaluate exchange filings (XBRL/announcements) vs a licensed provider in M1. |
| D4 | **Intended audience** — *decided: personal use + paper trading* | Distributing research may fall under SEBI RA/IA regulations; order flow falls under retail-algo rules | Personal decision support only; no order execution; legal review before any sharing or execution. |
| D5 | **Deployment host** for the always-on backend | Monitoring must run when devices are off | Small VPS / cloud VM with docker-compose; decide by M9. |
| D6 | **Frontend framework** | React + Vite vs Next.js | React + Vite PWA. |
| D7 | **Risk defaults** (per-trade risk %, max positions, daily loss limit, sector caps) | Directly affects capital at risk | Conservative defaults (e.g. ≤1% of capital at stop per trade), user-configurable; you confirm before M7. |

---

## 9. Key risks

- **Data licensing/availability** may limit intraday depth or storage rights — mitigated by
  M1 research before integration.
- **Overfitting / false confidence** — mitigated by walk-forward validation, baselines,
  calibration gates and publishing negative results honestly.
- **Survivorship and look-ahead bias** — mitigated by symbol history, delisting records,
  PIT feature store and replay tests.
- **Small evaluation samples** early on — performance shown with sample sizes and intervals;
  no claims from small samples.
- **Notification delivery limits** (OS-level Web Push) — in-app history is the record.
- **Regulatory exposure** if shared beyond personal use (D4).
