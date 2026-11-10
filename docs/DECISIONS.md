# Technical decision records

| # | Decision | Rationale | Date |
|---|---|---|---|
| ADR-01 | Monorepo: `backend/` (Python, uv), `frontend/` (React+TS+Vite PWA), `infra/` | One deployable system; one PWA codebase for desktop, Android and tablet | 2026-11-11 |
| ADR-02 | PostgreSQL for operational data and ledger; SQLite supported for local use and tests; suite runs on both | Easy local start without giving up production parity (CI runs both) | 2026-11-11 |
| ADR-03 | Ledger immutability enforced by DB triggers **and** a SHA-256 hash chain | Triggers prevent edits; the chain makes any out-of-band tampering detectable (`verify-ledger`) | 2026-11-11 |
| ADR-04 | Parquet bar store (one file per exchange/interval/instrument); raw source files kept immutable with checksums | Cheap, fast, reproducible; provenance per bar (`raw_file_id`) | 2026-11-11 |
| ADR-05 | No Redis/Celery: APScheduler worker + in-process asyncio monitor | Avoids unnecessary infrastructure (spec: Redis only where justified) | 2026-11-11 |
| ADR-06 | Indicators implemented in-house and reference-tested (Wilder RSI) | Transparency, no opaque TA dependency, causal windows guaranteed | 2026-11-11 |
| ADR-07 | First forecast target: 5-session triple barrier (+1.5 ATR / −1.0 ATR, entry at next open) | Directly maps to an executable trade plan; label availability date is explicit | 2026-11-11 |
| ADR-08 | Model ladder climatology → momentum rule → logistic → random forest → HistGradientBoosting; LightGBM/XGBoost not added | sklearn HGB covers gradient boosting without extra dependencies; add others only if validated | 2026-11-11 |
| ADR-09 | Walk-forward purged by label-availability date with embargo; isotonic calibration on the last 20% of each training window | No future leakage; calibration never uses test data | 2026-11-11 |
| ADR-10 | Probabilities shown only if the production model has OOS Brier skill over climatology **and** positive net utility; otherwise all actions AVOID with the reason | Honest "no validated edge" behaviour instead of noise-driven BUYs | 2026-11-11 |
| ADR-11 | Promotion gate with predefined criteria + untouched holdout; production compared only if it never saw the holdout | Controlled learning without in-sample comparisons | 2026-11-11 |
| ADR-12 | Allocation is computed from immutable ledger records, not recomputed analysis | What the user is shown is exactly what was recorded and will be evaluated | 2026-11-11 |
| ADR-13 | Paper trading on daily bars: no chasing gaps, stop fills at worse of stop/open, 50% at T1 + trail, time stop | Realistic, conservative simulation; documented limitation: daily granularity | 2026-11-11 |
| ADR-14 | Replays/demos write the real wall-clock `created_at`, with provenance `SYNTHETIC_REPLAY` | Ledger timestamps are never back-dated | 2026-11-11 |
| ADR-15 | Single-user auth: argon2 + optional TOTP, httpOnly SameSite=strict JWT cookie; no secrets in frontend | Personal use (D4); internet-exposed backend still protected | 2026-11-11 |
| ADR-16 | Service worker via vite-plugin-pwa `injectManifest` (precache + push handlers); simple SVG chart instead of a charting library | Installable, offline shell, Web Push; minimal dependencies | 2026-11-11 |
| ADR-17 | Cost schedule and holiday calendar are versioned data files carrying a `verified` flag surfaced in the UI | Never present unverified constants as facts | 2026-11-11 |
| ADR-18 | Synthetic fixture gets optional `planted_signal` (off by default) and price mean reversion | Exercise both the "no edge" and "skilled model" paths; results on it are never evidence | 2026-11-11 |
