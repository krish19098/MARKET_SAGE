# Immutable Prediction Ledger, Accountability and Self-Evaluation

## Core principle

Every prediction is a timestamped commitment. The system is judged using information available at the time of its decision. Later market data must never rewrite the original prediction or its evidence.

## Immutable prediction record

Persist at minimum:
- Unique prediction ID and instrument.
- Exchange and exact creation timestamp (IST display plus canonical timestamp).
- Latest market data timestamp and feature cutoff.
- Price and data snapshot at prediction time.
- BUY/HOLD/EXIT/AVOID and predicted direction.
- Entry range, stop/invalidation, targets and expected holding horizon.
- Forecast probabilities, uncertainty and confidence/calibration status.
- Technical, fundamental, market-regime and historical-analogue evidence.
- Thesis and invalidation conditions.
- Model, feature and strategy versions.
- Data source provenance.

Make original records append-only. Store subsequent updates, alerts, recommendations and outcomes as linked events. Keep reproducible feature snapshots. Corrections to data must be new, audited correction events, not silent overwrites.

## Evaluation horizons

Evaluate at appropriate horizons: intraday, 1, 3, 5, 10 and 20 trading sessions, plus actual trade closure. Do not force a forecast into an irrelevant horizon.

## Score dimensions

Keep separate measures for:
- Directional accuracy.
- Entry timing.
- Exit timing.
- Target estimation.
- Stop/invalidation quality.
- Early-warning lead time.
- False-positive and false-negative alert rates.
- Probability calibration.
- Net strategy/decision performance.

Use proper probabilistic scores such as Brier score or log loss when suitable. Include sample size and confidence intervals where possible. Do not create a single flattering score that hides weaknesses.

## Exit recommendation evaluation

For every exit, record:
- Original entry and recommended exit.
- User-confirmed actual fill, if known.
- Price path after exit.
- Maximum adverse movement avoided.
- Potential upside missed.
- Net impact after costs.
- Whether an earlier warning was possible using then-available data.
- Whether partial exit or trailing-stop logic would have improved the decision.

Example: entry ₹250, exit recommendation ₹246, later price ₹225. Potential price decline avoided relative to ₹246 is ₹21/share before costs and assuming execution at ₹246. This is a counterfactual estimate, not confirmed user savings unless the actual execution is known.

If price rises after an exit before later falling, evaluate the missed upside and the risk reduction separately. A correct final direction does not automatically make the exit well-timed. A loss-making exit is not automatically a bad decision.

## Self-evaluation and error analysis

For each completed forecast:
1. Compare forecast with outcome.
2. Identify correct assumptions.
3. Identify incorrect assumptions.
4. Find missed signals.
5. Diagnose late/early entry or exit.
6. Compare historical analogue expectations with actual outcome.
7. Classify error cause (data, feature, regime, model, execution, risk, event, or unknown).
8. Record a structured lesson.
9. Identify recurring weaknesses.
10. Propose a candidate improvement.

Do not claim a specific missed signal was available unless it existed in the timestamped data.

## Controlled learning

Collect completed outcomes into versioned evaluation datasets. Candidate models are trained separately and tested on chronological unseen data with walk-forward validation. Compare against production and baseline models for calibration, stability, drawdown and net performance. Promote only if predefined acceptance criteria pass. Preserve prior model and rollback capability. Never blindly retrain after each trade or evaluate a model on data it trained on.

## Analyst Performance screen

Show:
- Overall decision quality with transparent components.
- Directional accuracy.
- Entry and exit timing.
- Calibration.
- Early-warning lead time.
- False-alert percentage.
- Potential losses avoided.
- Potential profits missed.
- Net simulated value added.
- Performance by regime, horizon, instrument category and model version.
- Examples of correct and failed predictions.

Clearly label simulated/counterfactual values separately from confirmed user P&L.
