# Validation, Backtesting, QA and Acceptance Criteria

## Research validity

Every strategy/model must use chronological splits and walk-forward validation. Include:
- Out-of-sample tests.
- Realistic brokerage, STT, exchange fees, GST, stamp duty, taxes as applicable.
- Slippage, spread, liquidity and gap risk.
- Corporate actions.
- Survivorship-bias controls.
- Look-ahead-bias controls.
- Point-in-time fundamentals and announcements.
- Baseline comparisons.
- Multiple market regimes.
- Parameter sensitivity and robustness.

Measure win rate, profit factor, expectancy, maximum drawdown, Sharpe/Sortino where appropriate, average win/loss, calibration, precision/recall for alerts, net returns and performance by regime/horizon. Include sample size and uncertainty. Do not optimise only for historical return or accuracy.

## Paper trading

Run a paper-trading phase before real-money reliance. Simulate realistic order timing, fills, costs, liquidity and missed fills. Compare predicted entry/exit with executable assumptions. Preserve all paper predictions and outcomes.

## Mandatory functional acceptance tests

1. Create a BUY prediction and preserve all original fields and data cutoff.
2. New market data creates linked events without modifying the original prediction.
3. An early deterioration warning is generated before a defined breakdown when the evidence and model support it.
4. A confirmed trigger is distinguished from an early warning.
5. An EXIT recommendation retains its original timestamp, price and rationale.
6. If price declines after exit, calculate potential loss avoided using clearly stated counterfactual assumptions.
7. If price rises after exit, calculate potential upside missed separately.
8. Determine whether an earlier warning was possible using only information available then.
9. Evaluate at multiple horizons and at actual trade closure.
10. Produce honest self-evaluation with separate direction, timing and calibration scores.
11. Candidate model trains on completed outcomes but is evaluated on unseen chronological data.
12. A candidate that fails acceptance thresholds is rejected and production model remains intact.
13. Budget allocation calculates affordable quantities, costs, stop-risk and portfolio exposure.
14. System can leave capital unallocated.
15. Stale/missing data suppresses recommendations that depend on it.
16. Monitoring continues when browser and mobile app are closed.
17. Notification delivery attempts and failures are recorded.
18. User-entered positions are distinguished from model-generated hypothetical positions.
19. No API secrets are present in frontend bundles or source control.
20. Application, backend, ingestion, monitoring and tests have documented run procedures.

## Operational QA

Test provider outages, rate limits, partial data, missing candles, symbol changes, corporate actions, market holidays, restart/recovery, duplicate events, notification retries, database migrations, model rollback and timezone boundaries.

## Definition of done

A feature is complete only when implemented, tested, limitations documented and usable with real data or explicitly labelled test fixtures. Never present synthetic-data results as market validation or claim a live integration works without testing it.
