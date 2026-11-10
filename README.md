# MARKET SAGE

Evidence-driven Indian equity research and swing-trading **decision support**: market data warehouse,
analyst evidence engine, calibrated forecasts, budget allocation with risk controls, continuous backend
monitoring and alerts, an immutable prediction ledger, honest self-evaluation and controlled model learning.
It ships as one responsive, installable PWA for Windows/desktop browsers, Android and tablets.

> **Safety scope.** Personal use. Advisory recommendations and **paper trading only**. Real-money order
> execution does not exist in this codebase: the config refuses anything but `paper`, and a test fails the
> build if broker order endpoints appear anywhere. No returns are promised. ₹500/day is an aspirational
> evaluation metric only and never a reason to trade.

Live status: see [`PROJECT_STATE.md`](PROJECT_STATE.md). Architecture: [`docs/ARCHITECTURE_AND_ROADMAP.md`](docs/ARCHITECTURE_AND_ROADMAP.md).

## Repository layout

```
backend/    Python 3.12+ package `market_sage` (FastAPI, workers, engines), Alembic migrations, tests
frontend/   React + TypeScript + Vite PWA (Home, Invest, My Trades, Analyst, Performance)
infra/      Dockerfile, docker-compose (PostgreSQL + API/PWA + worker), .env.example
docs/       Architecture, decisions, data sources, deployment runbook, test report
.claude/skills/market-sage/   Project skill (product specification and workflows)
```

## Run procedures

### Prerequisites
- Python ≥ 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 22, and optionally PostgreSQL 16 (SQLite works for local use).
- On Windows: use PowerShell or WSL. The commands are the same apart from how environment variables are set.

### Backend (API)
```bash
cd backend
uv sync
```
```bash
uv run market-sage migrate
```
```bash
uv run market-sage hash-password      # paste the output into MARKET_SAGE_AUTH_PASSWORD_HASH (single-quoted in .env)
```
```bash
uv run market-sage serve --port 8000  # API at /api, serves the built PWA at /
```
Configuration comes from environment variables or `backend/.env`. See `infra/.env.example`. Never commit `.env`.

### Frontend (PWA)
```bash
cd frontend
npm ci
```
```bash
npm run dev       # http://localhost:5173, proxies /api to :8000
```
```bash
npm run build     # production build in frontend/dist, served by the API
```
To install the app: open it in Chrome/Edge (desktop or Android) and choose **Install app**. For Web Push,
generate VAPID keys with `uv run market-sage vapid-keys`, set them in the environment, then tap **Enable alerts** on Home.

### Data ingestion
- Real data (NSE official archives: OHLCV + delivery). Requires network access to `nsearchives.nseindia.com`:
```bash
uv run market-sage ingest-nse 2025-01-01 2026-11-10
```
- Synthetic demo (clearly labelled; never real market data):
```bash
MARKET_SAGE_DATA_MODE=fixture uv run market-sage demo
```

### Monitoring / worker (always-on)
```bash
uv run market-sage worker
```
The worker runs the live monitoring session (Angel One WebSocket when credentials are configured), the
18:30 IST post-close pipeline (ingest → paper fills → decisions → alerts → position assessment → evaluation),
the weekly controlled-learning cycle and a dead-man's-switch heartbeat. It does not depend on any browser or phone.

Manual one-off runs:
```bash
uv run market-sage post-close
```
```bash
uv run market-sage learn
```
```bash
uv run market-sage verify-ledger
```

### Tests
```bash
cd backend && uv run ruff check src tests && uv run mypy src && uv run pytest
```
```bash
cd backend && MARKET_SAGE_TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@localhost/DB uv run pytest
```
```bash
cd frontend && npm run lint && npm test && npm run build
```

### Deployment
See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): a single Mumbai VM running `infra/docker-compose.yml`,
with backups, heartbeat monitoring and private HTTPS access.
