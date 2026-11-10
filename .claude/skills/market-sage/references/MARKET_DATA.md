# Market Data and Historical Warehouse

## Objective

Build a reliable, licensed, timestamp-aware Indian equity data foundation. Historical data quality is a prerequisite for meaningful predictions. Do not train production models on tiny, randomly generated, or unverified samples.

## Provider investigation

Evaluate, rather than assume, the suitability of:
- NSE official historical reports and bhavcopy/archive products.
- BSE official historical reports.
- DhanHQ APIs.
- Zerodha Kite Connect.
- Upstox APIs.
- Licensed commercial providers for deeper intraday/tick data.

For each provider document:
- Supported exchanges and instruments.
- Daily and intraday historical depth.
- Supported candle intervals and timezone semantics.
- OHLCV, OI, delivery, depth and corporate event availability.
- Real-time versus delayed status.
- API pricing and subscription requirements.
- Rate limits, pagination, retention and outages.
- Redistribution, storage, display and commercial-use permissions.
- Adjustment methodology and symbol/instrument mapping.

Do not assume an API subscription grants unrestricted historical storage or redistribution. Verify current provider documentation and licensing before implementation.

## Target datasets

Collect as available and licensed:
- Daily OHLCV, aiming for 10–20 years where available.
- Intraday 1m, 5m, 15m, hourly candles, aiming for 3–5 years where available.
- Weekly and monthly bars.
- Volume and delivery quantity/percentage.
- Indices, sector indices and market breadth.
- Corporate actions and adjusted/unadjusted price series.
- Financial statements and quarterly results.
- Corporate announcements and event timestamps.
- Bulk/block deals and institutional holding disclosures.
- Historical constituents, delisted securities and symbol changes where available.
- Market calendar and trading-session metadata.

These are target depths, not guaranteed provider coverage.

## Warehouse design

Use PostgreSQL for instruments, symbols, corporate actions, provider metadata, predictions, positions, event records and operational state. Use Parquet for large time-series partitions where appropriate.

Keep:
1. Raw immutable source data.
2. Normalised canonical data.
3. Corporate-action-adjusted research series.
4. Point-in-time feature snapshots.
5. Data provenance and quality status.

Partition efficiently by exchange, instrument, interval and date. Maintain stable instrument identifiers across symbol changes.

## Ingestion and quality controls

Implement:
- Initial historical backfill.
- Incremental daily ingestion.
- Intraday updates and candle finalisation.
- Duplicate detection.
- Missing interval detection.
- Out-of-order and timestamp validation.
- OHLC consistency checks.
- Volume sanity checks.
- Corporate action reconciliation.
- Symbol mapping and delisting handling.
- Provider-to-provider reconciliation where feasible.
- Retry/backoff and rate-limit handling.
- Ingestion logs, checksums and quality reports.

Store exchange/event timestamp and received timestamp separately. Use Asia/Kolkata consistently for display and explicit UTC or canonical timestamps internally.

Do not silently fill missing market observations. Mark gaps and decide whether a feature/prediction is safe to compute.

## Point-in-time correctness

Financial statements, corporate announcements, holdings and other fundamentals must only become features from the time they were publicly available. Store publication/availability timestamps, not just reporting-period dates.

Avoid:
- Look-ahead bias.
- Survivorship bias.
- Incorrect adjusted-price use.
- Using revised financial data before its revision date.
- Training on future constituents only.
- Treating delayed data as live.

## Live data and monitoring

Keep live feed events separate from completed historical candles. Reconcile final candles against provider history after the session. Record feed latency and stale-data status. If the provider disconnects or data is stale, suppress decisions that require fresh data and alert the user to the outage.

## Deliverables

Provider comparison, licensing notes, credentials checklist, ingestion adapters, schema, data-quality dashboard/report, coverage matrix, and documented gaps.
