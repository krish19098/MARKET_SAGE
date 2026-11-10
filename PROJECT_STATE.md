# MARKET SAGE — Project State

> This file records the actual repository state. Update it at the end of every meaningful work session. Do not treat planned work as completed work.

## Current milestone
- Name: M0 — Repository/environment inspection, skill installation, architecture proposal
- Status: In progress — architecture and roadmap awaiting owner review (no application code yet)
- Last updated (IST): 2026-11-11 02:30

## Product and architecture
All entries below are **proposed** in `docs/ARCHITECTURE_AND_ROADMAP.md`; none are implemented.
- Frontend: Proposed React + TypeScript + Vite PWA (not started)
- Backend: Proposed Python 3.13 + FastAPI, `uv`-managed package `market_sage` (not started)
- Database/storage: Proposed PostgreSQL 16 (ops/ledger) + Parquet/DuckDB (time series) (not started)
- Market data providers: None configured. Candidates under evaluation: NSE/BSE archives, DhanHQ, Kite Connect, Upstox, commercial
- Prediction/model stack: Proposed scikit-learn baselines → gradient boosting only if validated (not started)
- Monitoring/notifications: Proposed asyncio monitoring service + Web Push (not started)
- Deployment: Not decided (always-on host required)

## Completed and verified
| Item | Evidence / test | Date |
|---|---|---|
| Repository inspected | Only `README.md` and one commit (`feba977 Initial commit`) existed; no code/tests/deps | 2026-11-11 |
| Environment inspected | Python 3.13.18, uv 0.11, Node 22, PostgreSQL 16 (stopped), Redis 7, Docker client; PyPI reachable; NSE hosts blocked (proxy 403) | 2026-11-11 |
| MARKET SAGE skill installed as project skill | `.claude/skills/market-sage/` — `diff -r` against source skill: identical; SKILL.md frontmatter `name: market-sage` | 2026-11-11 |
| Architecture & roadmap drafted | `docs/ARCHITECTURE_AND_ROADMAP.md` (proposal, not implementation) | 2026-11-11 |

## In progress
| Item | Current state | Next action |
|---|---|---|
| Architecture review | Proposal written | Owner reviews `docs/ARCHITECTURE_AND_ROADMAP.md` and answers decisions D1–D7 |

## Decisions and rationale
| Decision | Rationale | Date |
|---|---|---|
| Skill installed by copying into `.claude/skills/market-sage/` unchanged | Project-level skills load from `.claude/skills/<name>/SKILL.md`; keeps instructions versioned with the repo | 2026-11-11 |
| Architecture is a proposal pending review | Owner requested review before major architectural changes | 2026-11-11 |

## Data and external dependencies
| Provider/service | Configured? | Credentials/subscription/licensing | Limitations |
|---|---|---|---|
| NSE archives (bhavcopy, reports) | No | Licensing/usage terms to verify in M1 | Hosts blocked in current cloud environment |
| BSE archives | No | To verify in M1 | Not yet tested |
| DhanHQ / Kite Connect / Upstox | No | Requires owner's account; pricing/terms to verify | Choice pending (D1) |
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
| NSE hosts unreachable from cloud environment | High (blocks real ingestion here) | Allow hosts or ingest from owner's machine (D2) |
| No data provider or credentials selected | High | M1 provider research + owner decision (D1, D3) |
| Regulatory scope undefined | Medium | Confirm personal-use scope (D4) |

## Next concrete tasks
1. Owner review of `docs/ARCHITECTURE_AND_ROADMAP.md`; resolve D1–D7.
2. M0 foundation: backend/frontend skeleton, uv project, ruff/mypy/pytest, CI, docker-compose Postgres, Alembic baseline, config/secrets, Clock/IST utilities, secret-scan test.
3. M1 provider research document with licensing and coverage matrix.

## Important safeguards
- Original predictions are immutable: designed (append-only tables, DB triggers, hash chain) — not implemented
- Data freshness checks: designed (suppression gate, staleness tracking) — not implemented
- Model version and rollback: designed (model registry, promotion gate) — not implemented
- Secrets management: env vars / secret store; none committed — `.gitignore` to be added in M0
- No unverified performance claims: no performance exists or is claimed
