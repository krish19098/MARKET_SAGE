# MARKET SAGE — Project State

> This file records the actual repository state. Update it at the end of every meaningful work session. Do not treat planned work as completed work.

## Current milestone
- Name: M12 — Paper trading on real data, operational hardening, deployment
- Status: **Blocked on external dependencies** (network access to NSE/Angel One hosts, Angel One credentials, a VM). All code milestones M0–M11 are implemented and tested on synthetic/sample data.
- Last updated (IST): 2026-11-11

## Product and architecture
- Frontend: React 18 + TypeScript + Vite installable PWA (`frontend/`). Five screens plus alert history. Bottom nav on phones, icon rail on tablets, sidebar on desktop. Service worker (precache + Web Push).
- Backend: Python 3.13, FastAPI (`backend/src/market_sage`). Single-user auth (argon2 + optional TOTP, httpOnly JWT cookie).
- Database/storage: PostgreSQL 16 (production) / SQLite (local), Alembic migrations, append-only ledger tables enforced by DB triggers + hash chain. Parquet bar store; immutable raw-file store with checksums.
- Market data providers: broker-independent adapters. NSE archives (EOD, delivery, corporate actions, universe) and Angel One SmartAPI (live WS, intraday, tokens, read-only holdings) implemented but **not yet verified against the live services**. Synthetic fixture for development.
- Prediction/model stack: point-in-time feature store (fs1), regime classifier, kNN analogues, triple-barrier target, model ladder (climatology → momentum → logistic → RF → HistGradientBoosting), purged walk-forward, isotonic calibration, registry with promotion/rollback, early-setup lifecycle detectors.
- Decision/risk: suppression gate, model-skill requirement, EV after costs, 13-part thesis, versioned risk settings, cost model (unverified schedule), risk-based sizing, allocator (balanced/growth, cash allowed).
- Monitoring/notifications: always-on worker (APScheduler, IST), live session with reconnect, position state machine, 12 alert classes with stages, dedupe/cooldown, feed-stale fail-safe, Web Push with delivery log.
- Evaluation/learning: multi-horizon scoring, exit counterfactuals, earlier-warning replay, lessons with error causes, alert outcomes (lead time, false-alert rate), performance summary with CIs, controlled learning cycle with predefined gates and holdout, drift check, versioned evaluation datasets.
- Execution: **paper only**. `PaperBroker` daily-bar simulation; config refuses non-paper modes; a test forbids order endpoints in the code.
- Deployment: `infra/docker-compose.yml` (db, api+PWA, worker) + `docs/DEPLOYMENT.md`. **Not yet built or deployed.**

## Completed and verified
| Item | Evidence / test | Date |
|---|---|---|
| M0 foundation (uv project, config, clock/IST, calendar, schema, migrations, CI, infra skeleton) | `test_foundation.py`; migrations on SQLite + PostgreSQL | 2026-11-11 |
| M2 data layer (raw store, Parquet bars, registry, quality checks, CA adjustment, NSE parsers, Angel adapter, fixture) | `test_data_layer.py`, `test_operational.py` (sample files / fakes) | 2026-11-11 |
| M3–M5 features, analyst engine, analogues (PIT) | `test_features_analysis.py` (PIT equivalence, reference RSI, analogue look-ahead exclusion) | 2026-11-11 |
| M6 prediction engine | `test_prediction_decision.py` (purging, skill selection, no-skill path) | 2026-11-11 |
| M7 decision/risk/allocation | acceptance 13, 14, 15 | 2026-11-11 |
| M8 immutable ledger | acceptance 1, 2, 5; tamper detection | 2026-11-11 |
| M9 monitoring + notifications | acceptance 3, 4, 16, 17 | 2026-11-11 |
| M10 evaluation + controlled learning + paper broker | acceptance 6–12, 18 | 2026-11-11 |
| M11 API + PWA | `test_api.py`, vitest, Playwright screenshots on phone/tablet/desktop | 2026-11-11 |
| Synthetic end-to-end demo (`market-sage demo`) | gated model promoted on planted-signal synthetic data; 40 sessions replayed; 3,864 evaluations; ledger integrity 0 problems | 2026-11-11 |
| Docs: README run procedures, data sources, decisions, deployment, test report | `README.md`, `docs/*` | 2026-11-11 |

## In progress
| Item | Current state | Next action |
|---|---|---|
| M1 provider verification | Adapters built from researched specs; `capabilities.verified=False` | Allow hosts / run on owner machine; test calls; set verified flags and correct limits |
| M12 paper trading on real data | Paper broker + worker ready | Deploy, ingest real history, run ≥ 3 months of paper trading before any reliance |
| Fundamentals ingestion (D3) | PIT accessor + `filings` schema done; analyst shows "unknown" | Build NSE filings/XBRL adapter with broadcast timestamps |

## Decisions and rationale
See `docs/DECISIONS.md` (ADR-01…ADR-18) and `docs/DECISION_BRIEF_D1-D7.md`. Key points: paper-only execution; Angel One + NSE official files behind broker-independent adapters; no probabilities or BUYs without a validated out-of-sample edge; ledger never back-dated.

## Data and external dependencies
| Provider/service | Configured? | Credentials/subscription/licensing | Limitations |
|---|---|---|---|
| NSE archives | Code ready; **host blocked in dev env** | Free; personal non-commercial use | Formats/URLs unverified live |
| Angel One SmartAPI | Code ready; **no credentials** | Free with owner account; TOTP secret needed for automation | Limits unverified; daily midnight session reset |
| Fundamentals (NSE/BSE filings) | Not built | Free | Parsing effort; PIT via broadcast timestamps |
| Web Push (VAPID) | Code ready; keys not generated | `market-sage vapid-keys` | Needs HTTPS deployment; best-effort delivery |
| Hosting VM | Not provisioned | Oracle Always Free (₹0) or Lightsail 4 GB (~$24/mo) | Owner action required |
| Docker | Client present; image **not built** here | — | — |

## Tests and validation
- Commands run: `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest` (SQLite and PostgreSQL), `npm run lint`, `npm test`, `npm run build`, Playwright screenshot script against the running app.
- Results: backend 56 passed (SQLite); full suite passed on PostgreSQL; lint/types clean; frontend 3 tests passed, build OK; UI verified on phone/tablet/desktop.
- Failed tests: none at the last run.
- Backtest/paper-trading evidence: **none on real data.** Walk-forward and paper results exist only for SYNTHETIC data and are not market evidence.
- What is synthetic or mocked: fixture market (optionally with planted signal); SAMPLE NSE files; fake NSE client; synthetic WS packets built to the researched layout.

## Known bugs and risks
| Issue | Severity | Workaround / next step |
|---|---|---|
| Live provider formats/limits unverified (NSE URLs, Angel WS binary layout, rate limits) | High | M1 verification with real access before relying on live data |
| Cost schedule unverified | Medium | Reconcile `charges_v1.json` with an Angel One contract note |
| Holiday calendar empty for 2026+ | Medium | Fill `holidays.csv` from NSE circular (past holidays are inferred) |
| Paper simulation uses daily bars (no intraday path) | Medium | Documented; intraday simulation once intraday data is verified |
| No validated edge on real data yet | High (product) | System will show AVOID/cash until a model passes the gates on real data |
| Fundamentals absent | Medium | D3 adapter |
| Per-cutoff analysis ~2 s per 16 stocks | Low | Fine for EOD; optimise analogue search for 500+ stocks if needed |

## Next concrete tasks
1. Owner: allow NSE/BSE/Angel documentation hosts in the cloud dev environment (or run on own machine) and provide Angel One credentials on the VM only. Then verify adapters (M1) and set `verified=True` with corrected limits.
2. Ingest real NSE history (≥ 5 years), fill the holiday calendar, reconcile the cost schedule, run the learning cycle on real data and report the honest result.
3. Provision the VM, `docker compose up`, configure the heartbeat, VAPID and private HTTPS. Start the real-data paper-trading period.
4. Build the NSE filings/XBRL fundamentals adapter (D3).

## Important safeguards
- Original predictions are immutable: ✅ DB triggers on 10 tables + SHA-256 hash chain, `market-sage verify-ledger`, tamper-detection test.
- Data freshness checks: ✅ EOD staleness vs calendar, live feed staleness → suppression + `data_stale` alert.
- Model version and rollback: ✅ registry, predefined promotion gates, `market-sage rollback-model`.
- Secrets management: ✅ env vars / `.env` (git-ignored), argon2 password hash, httpOnly cookie, secret-scan test; no keys in the frontend.
- No unverified performance claims: ✅ synthetic labels everywhere; counterfactuals labelled; the Performance screen separates confirmed from simulated P&L.
