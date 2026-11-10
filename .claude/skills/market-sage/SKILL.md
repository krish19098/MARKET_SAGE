---
name: market-sage
description: Build, research, validate, debug, and maintain MARKET SAGE, an independent Indian equity market intelligence and swing-trading decision-support application. Use when working on its architecture, market data, analyst intelligence, predictions, portfolio allocation, trade monitoring, alerts, prediction accountability, self-evaluation, UI, testing, or deployment.
---

# MARKET SAGE — Project Skill

## Mission

Build MARKET SAGE as an independent, evidence-driven Indian equity research and swing-trading decision-support system. It must anticipate opportunities where evidence supports a forecast, explain its reasoning, allocate user capital responsibly, monitor positions, preserve every original prediction, evaluate outcomes honestly, and improve through controlled model validation.

This is a serious financial software project, not a stock screener, indicator dashboard, casual prototype, or guaranteed-profit product.

## Non-negotiable principles

1. **Predict before events, never rewrite history.** Every prediction is timestamped and immutable. Later information is stored as a new event, never used to alter the original record.
2. **Evidence before recommendation.** Separate observed facts, analytical inferences, model estimates, and unknowns.
3. **No fabricated data or performance.** Never claim live data, accuracy, backtest results, broker integration, or notification delivery unless verified.
4. **No guaranteed returns.** ₹500 average daily profit is an aspirational evaluation objective, never a promised outcome or reason to force trades.
5. **Capital protection is integral.** Every trade needs a defined invalidation condition, position sizing, downside calculation, and realistic costs.
6. **Independent operation.** The running product must not depend on Claude, ChatGPT, or an external conversational AI.
7. **Controlled learning.** Never blindly retrain after each trade. Candidate models must pass chronological out-of-sample and walk-forward validation before promotion.
8. **Simple UI.** Keep five primary screens: Home, Invest, My Trades, Analyst, Performance. Prioritise speed and clarity over decoration.
9. **Backend does the monitoring.** The server monitors markets while browsers and phones are closed; mobile is an alert and decision interface.
10. **Respect Indian market rules.** Start with advisory recommendations and user-confirmed execution. Review applicable SEBI, exchange, broker, data licensing, privacy, and security requirements before execution or distribution.

## How to use this Skill

Do not load every reference file for every task. First identify the task and read only the relevant reference(s):

- Overall product requirements or scope: `references/MASTER_SPECIFICATION.md`
- Market data or provider integration: `references/MARKET_DATA.md`
- Analyst methodology and technical research: `references/ANALYST_INTELLIGENCE.md`
- Forecasting and model development: `references/PREDICTION_ENGINE.md`
- Budget-based allocation and risk: `references/PORTFOLIO_ALLOCATION.md`
- Immutable predictions, scoring, and learning: `references/SELF_EVALUATION.md`
- Monitoring and alerts: `references/MONITORING_ALERTS.md`
- UI and user experience: `references/UI_REQUIREMENTS.md`
- Backtesting, QA, and acceptance: `references/VALIDATION_TESTING.md`
- Build, research, debug, or release procedure: corresponding file in `workflows/`

For cross-cutting work, read the smallest set of references that fully covers the task. Read the master specification when the task changes product scope or when a conflict between requirements needs resolution.

## Development operating procedure

1. Inspect the existing repository, runtime, dependencies, tests, and `PROJECT_STATE.md` before changing anything.
2. Preserve existing working code. Make the smallest safe changes consistent with the repository's conventions.
3. Identify dependencies, data availability, credentials, licensing, and operational blockers.
4. Implement a vertical slice that can be run and tested; do not stop at architecture or mock UI.
5. Add or update automated tests for the changed behaviour.
6. Run relevant tests, linters, type checks, and build commands. Report actual results.
7. Update `PROJECT_STATE.md` with completed work, decisions, blockers, tests, and the next concrete task.
8. Never claim a task is complete if an acceptance criterion is untested or an external dependency is unresolved.

Do not ask the user for approval at every ordinary engineering step. Make reasonable reversible decisions. Ask only when a missing decision materially affects capital risk, paid services, credentials, legal/regulatory exposure, destructive operations, or a product requirement that cannot safely be inferred.

## Persistent project state

At the repository root, maintain `PROJECT_STATE.md`. If absent, create it from `templates/PROJECT_STATE_TEMPLATE.md`. Update it at the end of every meaningful work session. The Skill package is the reusable instruction set; `PROJECT_STATE.md` is the live record of the actual repository and must not be treated as proof that features work.

## Task-specific rules

- **Data work:** verify provider documentation, permitted usage, historical depth, interval coverage, rate limits, timestamps, symbol mapping, corporate actions, and gaps. Preserve raw source data and provenance.
- **Prediction work:** define the forecast target, horizon, event timestamp, feature availability cutoff, baseline, calibration, and validation protocol before training.
- **Trade recommendations:** provide entry range, stop/invalidation, targets, quantity, capital required, costs, risk/reward, expected holding horizon, confidence/uncertainty, and thesis. If data is stale or risk cannot be calculated, suppress the recommendation.
- **Allocation:** select and size positions based on validated opportunity quality, portfolio risk, liquidity, correlations, costs, and user settings. Unallocated cash is an acceptable recommendation.
- **Exit evaluation:** measure both potential loss avoided and upside missed. A correct direction does not automatically mean good timing or a good decision.
- **Learning:** evaluate using only information available at the original decision time. Keep model versions and immutable prediction snapshots.
- **Notifications:** distinguish early warning, approaching trigger, and confirmed trigger. Do not report a completed event as a prediction.
- **UI:** keep the five-screen structure simple. Put detail behind a stock or trade view, not on the home screen.
- **Security:** never hardcode API keys or commit secrets. Use environment variables or a secure secret store. Never place broker credentials in frontend code.

## Completion standard

A feature is complete only when it is implemented, tested, its limitations are documented, and it works with real or clearly labelled test data. See `references/VALIDATION_TESTING.md` for product-level acceptance criteria.
