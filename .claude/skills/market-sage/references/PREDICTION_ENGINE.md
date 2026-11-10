# Predictive Intelligence and Early Opportunity Engine

## Objective

Forecast future outcomes using information available at the forecast timestamp. The engine must not merely describe an event after it has happened.

## Define forecasts before training

For every model/forecast define:
- Instrument universe.
- Prediction timestamp and feature cutoff.
- Target variable and exact calculation.
- Forecast horizon.
- Event/price convention (close, high/low, executable price, etc.).
- Costs and slippage assumptions.
- Baseline model.
- Training and validation windows.
- Probability calibration method.
- Conditions under which no forecast is issued.

Potential horizons: intraday, 1, 3, 5, 10 and 20 trading sessions. Use horizons only where data quality and strategy justify them.

Forecast up/down/neutral or threshold events, expected movement distribution, uncertainty, volatility and potential adverse movement. Do not output a probability without calibration evidence.

## Candidate methods

Evaluate methods rather than adopting them by fashion:
- Logistic regression and statistical baselines.
- Random Forest.
- Gradient boosting, XGBoost and LightGBM.
- Time-series/statistical models.
- Regime detection and Hidden Markov Models where appropriate.
- Ensemble and regime-conditioned models.

Use feature engineering from price structure, momentum, volume, volatility, market breadth, sector strength, fundamentals, events and historical analogues.

## Market regime adaptation

Detect bull, bear, sideways, high-volatility, low-volatility and transition regimes using validated methods. Assess whether a model's performance changes by regime. Do not assume one model is best in every regime. A regime label itself has uncertainty and must be timestamp-correct.

## Early opportunity discovery

Detect:
- Relative-strength improvement.
- Volatility contraction/expansion.
- Developing breakouts and breakdowns.
- Early momentum shifts.
- Volume anomalies.
- Support-zone reversals.
- Sector leadership changes.
- Event-driven opportunities.
- Historical conditions associated with favourable outcomes.

Classify a setup as early, developing, confirmed or invalidated. An early warning must be explicitly probabilistic and must not be presented as a confirmed event. Measure alert lead time and false-alert rate.

## Model discipline

- Chronological train/test splits.
- Walk-forward validation.
- Out-of-sample testing.
- Feature availability checks.
- No future leakage.
- No random split that mixes time.
- Probability calibration.
- Baselines and ablation tests.
- Regime-specific evaluation.
- Transaction costs and slippage.
- Model/version tracking.
- Drift monitoring and rollback.

Evaluate directional metrics, Brier score/log loss where appropriate, calibration curves, precision/recall for event alerts, economic utility, drawdown, expectancy and net returns. Do not equate classification accuracy with trading profitability.

## Decision output

Prediction is not a trade decision by itself. Pass model outputs into a separate decision/risk layer. Recommendations must include entry, stop, targets, size, costs, thesis, invalidation, expected horizon and uncertainty. Suppress the recommendation if data is stale or the setup cannot be executed realistically.

## No LLM-generated market facts

An optional local language model may explain verified outputs. It must not invent current prices, model probabilities, historical results, technical levels or announcements. The quantitative system remains the source of truth.
