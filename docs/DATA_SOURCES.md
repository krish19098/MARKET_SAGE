# Data sources, roles and verification status

Decision D1 (see `DECISION_BRIEF_D1-D7.md`): every data role has its own source, and everything sits behind
broker-independent adapters (`backend/src/market_sage/data/providers/`). A provider's limits are declared as
data (`ProviderCapabilities`). `verified=True` is set only after confirmation against live documentation **and**
test calls.

| Role | Primary source | Adapter | Implemented | Verified against live service | Notes |
|---|---|---|---|---|---|
| EOD OHLCV (source of record) | NSE `sec_bhavdata_full` | `nse_archive` | ✅ parser, client, buffered ingestion, holiday inference | ✅ 2026-11-11 live files parsed; UDiFF vs full bhavcopy: 0 close mismatches / 3,435 rows | A non-trading date's URL served the previous session's file; date-mismatch guard added |
| Delivery qty/% | NSE `sec_bhavdata_full` | `nse_archive` | ✅ | ✅ 3,191/3,435 rows with delivery on 09-Nov-2026 | Brokers do not supply delivery data |
| Corporate actions | NSE corporate-actions API | `nse_archive` | ✅ subject parser (split/bonus/dividend/rights/demerger) + storage + L2 adjustment | ✅ live API: 991 records Aug–Nov 2026, no split/bonus misclassified; `caBroadcastDate` stored as published_at | Rights/demerger flagged, not price-adjusted (limitation) |
| Index closes (regime, RS) | NSE `ind_close_all` | `nse_archive` | ✅ | ✅ 167 indices on 09-Nov-2026 | Sector membership of stocks not yet mapped |
| Universe / symbols / ISIN | NSE `EQUITY_L.csv` + bhavcopy history | `nse_archive` | ✅ parser; symbol change via ISIN | ✅ 2,633 rows | Survivorship control: instruments are never deleted |
| Intraday history | Angel One SmartAPI `getCandleData` | `angelone` | ✅ chunk planner, rate limiter, parser | ❌ needs owner credentials | Conservative per-request windows (sources conflict) |
| Live quotes | Angel One WebSocket 2.0 (+ REST quote fallback) | `angelone` | ✅ session, subscription, binary parser, heartbeat | ❌ needs credentials | 1,000 tokens/session, 3 connections |
| Holdings (read-only) | Angel One `getHolding` | `angelone` | ✅ | ❌ | Manual position entry is the default |
| Fundamentals | NSE/BSE filings (XBRL, broadcast timestamps) | — | ✅ point-in-time accessor + schema; ingestion adapter **not yet built** | ❌ | Analyst reports "fundamentals unknown" until filings exist |
| Development/testing | Synthetic market | `fixture` | ✅ | n/a | Labelled SYNTHETIC everywhere; optional planted signal for pipeline tests |

## Licensing notes
- NSE archive files: personal, non-commercial use under the NSE Data Usage Policy. No redistribution, no public dashboards.
- Angel One SmartAPI: free for the account holder. Market data must not be republished. A static IP is required only for order
  APIs, which MARKET SAGE never calls.

## Credentials checklist (owner)
| Credential | Where | Needed for |
|---|---|---|
| `MARKET_SAGE_ANGEL_API_KEY` (market-data scope if offered) | SmartAPI dashboard | live quotes, intraday history |
| `MARKET_SAGE_ANGEL_CLIENT_CODE`, `MARKET_SAGE_ANGEL_PIN` | Angel One account | daily login |
| `MARKET_SAGE_ANGEL_TOTP_SECRET` | SmartAPI TOTP enablement | automated daily login (sensitive: keep it on the server only) |
| VAPID key pair | `market-sage vapid-keys` | Web Push |
| Auth password hash (+ optional TOTP) | `market-sage hash-password` / `totp-secret` | PWA login |

## Coverage gaps (documented, not hidden)
- Intraday depth via Angel One is limited and unverified. DhanHQ (5-year intraday) is the first add-on candidate.
- No tick-by-tick data, FII/DII flows or bulk/block deals ingestion yet.
- Charge schedule (`resources/costs/charges_v1.json`) is **unverified**. Reconcile it against an Angel One contract note.
- Exchange holiday list (`resources/calendar/holidays.csv`) is empty. Fill it from NSE circulars; past holidays are inferred from missing bhavcopies.
