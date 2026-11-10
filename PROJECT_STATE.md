# MARKET SAGE — Project State

> This file records the actual repository state. Update it at the end of every meaningful work session. Do not treat planned work as completed work.

## Current milestone
- Name: M0 — Repository/environment inspection, skill installation, architecture proposal
- Status: In progress — architecture accepted by owner; final decisions D1–D7 pending (no application code yet; M0 not started)
- Last updated (IST): 2026-11-11

## Product and architecture
All entries below are **proposed** in `docs/ARCHITECTURE_AND_ROADMAP.md`; none are implemented.
- Frontend: Proposed React + TypeScript + Vite PWA (not started)
- Backend: Proposed Python 3.13 + FastAPI, `uv`-managed package `market_sage` (not started)
- Database/storage: Proposed PostgreSQL 16 (ops/ledger) + Parquet/DuckDB (time series) (not started)
- Market data providers: None configured. Proposed (D1, pending approval): Angel One SmartAPI (live, intraday, tokens) + NSE/BSE official files (EOD, delivery, corporate actions, universe), behind broker-independent adapters
- Execution: Real-money order execution disabled by design; paper trading only (owner requirement)
- Prediction/model stack: Proposed scikit-learn baselines → gradient boosting only if validated (not started)
- Monitoring/notifications: Proposed asyncio monitoring service + Web Push (not started)
- Deployment: Not decided (always-on host required)

## Completed and verified
| Item | Evidence / test | Date |
|---|---|---|
| Repository inspected | Only `README.md` and one commit (`feba977 Initial commit`) existed; no code/tests/deps | 2026-11-11 |
| Environment inspected | Python 3.13.18, uv 0.11, Node 22, PostgreSQL 16 (stopped), Redis 7, Docker client; PyPI reachable; NSE hosts blocked (proxy 403) | 2026-11-11 |
| MARKET SAGE skill installed as project skill | `.claude/skills/market-sage/` — `diff -r` against source skill: identical; SKILL.md frontmatter `name: market-sage` | 2026-11-11 |
| Architecture & roadmap drafted | `docs/ARCHITECTURE_AND_ROADMAP.md` (proposal, not implementation); owner accepted overall design | 2026-11-11 |
| Decision brief D1–D7 prepared | `docs/DECISION_BRIEF_D1-D7.md` (desk research; Angel docs could not be fetched directly — figures marked for M1 verification) | 2026-11-11 |

## In progress
| Item | Current state | Next action |
|---|---|---|
| Final decisions D1–D7 | Brief written with recommendations | Owner approves/adjusts D1, D2 (D3, D5–D7 may be postponed); then owner approves M0 start |

## Decisions and rationale
| Decision | Rationale | Date |
|---|---|---|
| Skill installed by copying into `.claude/skills/market-sage/` unchanged | Project-level skills load from `.claude/skills/<name>/SKILL.md`; keeps instructions versioned with the repo | 2026-11-11 |
| Architecture is a proposal pending review | Owner requested review before major architectural changes | 2026-11-11 |
| Scope: personal use + paper trading; no real-money execution (D4) | Owner instruction | 2026-11-11 |
| Angel One SmartAPI = initial broker integration candidate | Owner's broker; free API; owner instruction. Not assumed to cover history depth, delivery, corporate actions or fundamentals | 2026-11-11 |
| Broker-independent provider adapter layer | Owner instruction; allows adding DhanHQ/Kite/others without changing engines | 2026-11-11 |

## Data and external dependencies
| Provider/service | Configured? | Credentials/subscription/licensing | Limitations |
|---|---|---|---|
| NSE archives (bhavcopy, reports) | No | Licensing/usage terms to verify in M1 | Hosts blocked in current cloud environment |
| BSE archives | No | To verify in M1 | Not yet tested |
| Angel One SmartAPI | No | Free with owner's Angel account; client code + PIN + TOTP; daily midnight session reset; static IP only needed for orders (not used) | Limits/depth figures conflict across sources — verify in M1; no delivery/corporate actions/fundamentals; WS 1,000 tokens/session, 3 connections |
| DhanHQ / Kite Connect / Upstox | No | Not needed initially; DhanHQ (~₹499/month) is the first add-on candidate | Postponed |
| Fundamentals with publication timestamps | No | Source undecided (D3) | — |
| Web Push (VAPID) | No | Keys to be generated and stored as secrets | OS-level delivery not guaranteed |
| Hosting | No | Pending (D5) | — |

## Tests and validation
- Commands run: environment/tool version checks; `diff -r` of installed skill vs source
- Results: skill copy identical; no application tests exist yet
- Failed tests: none (no test suite yet)
- Backtest/paper-trading evidence: none
- What is synthetic or mocked: nothing yet

## Known bugs and risks
| Issue | Severity | Workaround / next step |
|---|---|---|
| NSE, BSE and Angel One hosts unreachable from cloud environment | High (blocks real ingestion and doc verification here) | Hybrid network option (D2) |
| Angel One API figures unverified/conflicting | Medium | Verify via live docs and test calls in M1 before coding against them |
| No data provider or credentials selected | High | M1 provider research + owner decision (D1, D3) |
| Regulatory scope undefined | Medium | Confirm personal-use scope (D4) |

## Next concrete tasks
1. Owner's final decisions on `docs/DECISION_BRIEF_D1-D7.md` and explicit approval to start M0.
2. M0 foundation: backend/frontend skeleton, uv project, ruff/mypy/pytest, CI, docker-compose Postgres, Alembic baseline, config/secrets, Clock/IST utilities, secret-scan test.
3. M1 provider research document with licensing and coverage matrix.

## Important safeguards
- Original predictions are immutable: designed (append-only tables, DB triggers, hash chain) — not implemented
- Data freshness checks: designed (suppression gate, staleness tracking) — not implemented
- Model version and rollback: designed (model registry, promotion gate) — not implemented
- Secrets management: env vars / secret store; none committed — `.gitignore` to be added in M0
- No unverified performance claims: no performance exists or is claimed
