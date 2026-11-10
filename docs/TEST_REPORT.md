# Test report

**Run:** 2026-11-11 (IST), commit on branch `claude/modest-keller-hl6arn`.

| Suite | Command | Result |
|---|---|---|
| Backend, SQLite | `uv run pytest` | **56 passed** |
| Backend, PostgreSQL 16 | `MARKET_SAGE_TEST_DATABASE_URL=… uv run pytest` | **passed** (full suite; earlier 55-test run also passed) |
| Lint / types | `ruff check src tests` · `mypy src` | clean · clean (76 files) |
| Frontend | `npm run lint` (tsc) · `npm test` (vitest, 3) · `npm run build` | clean · passed · built (SW + manifest generated) |
| Browser E2E (Playwright, manual script) | phone (Pixel 7), tablet (820×1180), desktop (1366×900) against the SYNTHETIC demo | login, Home, Invest, Analyst, Performance, My Trades all render; service worker registered; only console errors are the expected pre-login 401s |

**Data used:** all automated tests use SYNTHETIC fixtures or SAMPLE files that follow the published file layouts. **No result here is
market validation.** The "skilled model" tests deliberately plant a learnable signal in synthetic data to exercise the BUY path. On
signal-free synthetic data, the system correctly finds **no edge** and issues no BUY.

## Mandatory acceptance tests (VALIDATION_TESTING.md)

| # | Requirement | Test(s) | Status |
|---|---|---|---|
| 1 | BUY prediction preserves all original fields + data cutoff | `test_prediction_decision.py::test_end_to_end_buy_recorded_immutably_and_events_linked` | ✅ |
| 2 | New data creates linked events; original unchanged | same test + `test_foundation.py::test_ledger_tables_are_append_only`, `test_ledger_detects_tampering` | ✅ |
| 3 | Early deterioration warning before a defined breakdown | `test_monitoring_evaluation.py::test_early_warning_precedes_confirmed_stop` | ✅ (synthetic replay) |
| 4 | Confirmed trigger distinguished from early warning | `test_state_machine_distinguishes_stages`, test 3 | ✅ |
| 5 | EXIT keeps original timestamp, price, rationale | `test_exit_counterfactuals_loss_avoided_and_upside_missed`, test 1 | ✅ |
| 6 | Loss avoided after exit (stated counterfactual assumptions) | `test_exit_counterfactuals…`, `test_spec_example_loss_avoided` (₹250/246/225 → ₹21) | ✅ |
| 7 | Upside missed computed separately | `test_exit_counterfactuals…` | ✅ |
| 8 | Earlier warning possible using only then-available data | `Evaluator.earlier_warning_possible` exercised in `test_exit_counterfactuals…` | ✅ |
| 9 | Multiple horizons + trade closure | `test_multi_horizon_evaluation_and_lessons` (1/3/5/10/20); closure via paper/actual exits | ✅ (closure scored through paper P&L and exit evaluation) |
| 10 | Separate direction, timing, calibration scores | `test_multi_horizon_evaluation_and_lessons`, `PerformanceService.summary` | ✅ |
| 11 | Candidate trains on completed outcomes, evaluated on unseen chronological data | `test_learning_cycle_rejects_no_skill_candidate_and_keeps_production`, `test_walk_forward_purges_and_selects_honestly`, `test_dataset_has_no_future_labels` | ✅ |
| 12 | Failing candidate rejected; production intact | `test_learning_cycle_rejects…`, `test_model_rollback_preserves_previous` | ✅ |
| 13 | Allocation: affordable qty, costs, stop-risk, exposure | `test_allocation_affordable_quantities_and_cash`, `test_risk_sizing_and_costs` | ✅ |
| 14 | Capital can stay unallocated | `test_allocation_affordable_quantities_and_cash` | ✅ |
| 15 | Stale/missing data suppresses recommendations | `test_stale_data_suppresses_recommendations`, `test_data_status_stale_vs_fresh` | ✅ |
| 16 | Monitoring continues with browser/app closed | `test_monitoring_runs_without_any_client…` (backend-only feed consumption); worker architecture | ✅ (in-process; 24×7 deployment not yet run) |
| 17 | Notification attempts and failures recorded | `test_monitoring_runs_without_any_client_and_records_delivery_failures` | ✅ |
| 18 | User-entered vs model/paper positions distinguished | `test_paper_trading_entry_rules_and_user_vs_paper`, `test_api.py::test_positions_actual_vs_paper` | ✅ |
| 19 | No secrets in frontend bundles or source control | `test_foundation.py::test_no_secrets_committed`; auth via httpOnly cookie, no keys in frontend | ✅ |
| 20 | Documented run procedures | `README.md`, `docs/DEPLOYMENT.md` | ✅ |

## Operational QA covered
Provider outage recorded (`test_provider_outage_is_recorded_not_hidden`), holiday inference and idempotent re-ingestion
(`test_nse_ingestion_infers_holidays_and_is_idempotent`), restart recovery, IST/UTC session boundaries, duplicate-alert
cooldown, notification retries, migrations on SQLite + PostgreSQL, model rollback, point-in-time feature equivalence,
analogue look-ahead exclusion, the reference RSI implementation, failed-breakout logic.

## Not yet verified (requires external access)
- Live NSE archive downloads and Angel One SmartAPI calls (hosts blocked in the dev environment; credentials not provided).
- Real Web Push delivery to an Android device (needs VAPID keys + HTTPS deployment).
- Docker image build and the 24×7 VM deployment.
- Any performance on real market data. A paper-trading period on real data has not started.
