# MARKET SAGE — Complete Product Specification

## 1. Product identity and mission

MARKET SAGE is an independent Indian stock-market intelligence, prediction, portfolio-allocation, swing-trading decision-support, monitoring, and self-evaluation application.

It should emulate the disciplined research process of a senior equity analyst and swing-trading strategist with extensive market-cycle experience. This is an engineering objective, not a claim that software literally has 20 years of human experience.

It must go beyond displaying publicly available indicators. It independently investigates price behaviour, company fundamentals, market regime, sector context, volume, liquidity, historical analogues, catalysts, risk, and competing scenarios.

The application must:
- Scan eligible NSE stocks and supported BSE stocks.
- Find potential bullish and bearish opportunities.
- Discover overlooked and potentially undervalued companies without confusing price decline with value.
- Forecast future price movement probabilistically.
- Recommend BUY, HOLD, EXIT, or AVOID.
- Suggest budget-based allocations automatically.
- Monitor the market and active positions throughout supported market sessions.
- Alert users before or as defined conditions develop, not retrospectively.
- Preserve every prediction and subsequent change.
- Score its own predictions and decisions.
- Identify what it missed and improve only through controlled validation.
- Operate without Claude, ChatGPT, or another conversational AI service.

Primary style is swing trading, but a trade may need to be exited intraday if its thesis fails or a target is reached. Do not force a fixed holding period.

## 2. Market and operating scope

Initial market: Indian cash equities, principally NSE and supported BSE instruments. Begin with liquid, sufficiently documented securities. Avoid automatically recommending illiquid, manipulated, penny, or poorly documented securities.

Initial mode: advisory signals and user-confirmed execution. Do not place live orders automatically in the initial release.

Use Asia/Kolkata for all user-facing market timestamps. Support exchange calendars, holidays, trading sessions, special sessions, pre-open distinctions, and market closures. Every data point must have source time and received time. Never label delayed data as live.

Short selling, futures, options, and other leveraged products are separate future scopes with their own risk, margin, data, and regulatory requirements.

## 3. Product experience

The UI must be simple, responsive, and usable on desktop and mobile. Use five primary sections:

1. **Home:** market condition, available budget, best opportunities, portfolio summary, active alerts, material risks.
2. **Invest:** user enters capital; application proposes allocations, quantities, entry/stop/targets, costs, and reserve cash.
3. **My Trades:** user-entered or confirmed positions, quantity, entry, current price, P&L, stop, target, and HOLD/EXIT assessment.
4. **Analyst:** detailed evidence, market context, historical comparisons, bullish/bearish/neutral cases, thesis and invalidation.
5. **Performance:** prediction scores, timing quality, avoided losses, missed upside, false alerts, model/version results, and learning reports.

Do not create a complex UI, excessive charts on the home screen, unnecessary animations, or decorative features. Detailed charts belong in a focused stock-analysis view. Make key actions immediately understandable.

Use a responsive web application/PWA first. A native mobile app may be considered later if push reliability, platform integration, or user research justifies it. The backend—not the phone—must perform continuous analysis and monitoring.

## 4. User budget and investment objective

The user may enter any budget, e.g. ₹5,000, ₹10,000, ₹20,000, ₹25,000, ₹50,000, ₹1,00,000, or a custom amount.

The system should independently select and size the strongest eligible opportunities based on validated risk-adjusted quality, liquidity, correlation, portfolio exposure, costs, market regime, and user risk preferences.

Illustrative allocation only:
- Stock A: ₹8,000
- Stock B: ₹6,000
- Stock C: ₹4,000
- Unallocated reserve: ₹2,000

The example is not a fixed allocation rule. Actual amounts and quantities must be calculated from current, verified data and position-sizing constraints.

For every proposed holding show:
- Company and symbol.
- Investment amount and quantity.
- Current price and proposed entry range.
- Stop-loss/invalidation.
- Target 1 and Target 2.
- Expected holding period.
- Estimated transaction costs.
- Potential loss at stop.
- Reward/risk and uncertainty.
- Reason selected and why competing candidates ranked lower.

Do not force the full budget into the market. Cash is a valid allocation when no suitable opportunity exists. Do not recommend a stock solely because it fits the budget. Support configurable balanced and growth-oriented modes, with explicit trade-offs. The system must not describe equities as safe or risk-free.

₹500 average daily profit is an aspirational evaluation goal only. It is not guaranteed and must never cause forced trades or excessive risk. Show the capital and return assumptions needed to pursue any target, including costs and downside.

## 5. Independent operation and architecture

Suggested stack, subject to repository inspection and evidence:
- Python backend and FastAPI.
- Pandas, NumPy, scikit-learn.
- XGBoost/LightGBM where validated.
- PostgreSQL for structured operational data.
- Parquet for large historical datasets.
- Redis only where caching/queues justify it.
- React or Next.js frontend.
- WebSockets for live updates.
- Independent background workers and notification service.
- Versioned model artefacts and experiment records.

Separate modules/services for ingestion, warehouse, technical analysis, fundamentals, regime detection, historical analogues, predictive modelling, allocation, risk, monitoring, prediction ledger, evaluation, model improvement, and notifications.

A locally hosted language model may assist with explanations if it demonstrably adds value. It must not invent or independently determine unverified prices, probabilities, targets, or risk limits. Quantitative engines and verified data remain authoritative.

## 6. Product principles

- Anticipate, do not merely narrate after an event.
- Timestamp every forecast and record the data cutoff.
- Never revise an original forecast using later information.
- Preserve both successful and failed calls.
- Explain why the recommendation exists and what would invalidate it.
- Separate facts, inferences, forecasts, and uncertainty.
- Suppress recommendations when data is stale, incomplete, or risk cannot be calculated.
- Never fabricate sources, institutional activity, financial events, results, backtests, or performance.
- Compare against simple baselines and account for costs.
- Do not optimise solely for historical returns or win rate.
- Keep a stable production model and support rollback.
- Operate independently of AI coding assistants after deployment.

## 7. Delivery stages

Build in validated vertical slices:
1. Repository and environment inspection; state tracking.
2. Data provider research and data warehouse.
3. Market calendar, instrument master, historical ingestion and quality.
4. Technical/fundamental/market context engines.
5. Historical pattern memory.
6. Prediction targets, features, baselines and validation.
7. Risk and budget allocation.
8. Immutable prediction ledger and monitoring.
9. Self-evaluation and controlled model improvement.
10. Simple responsive UI and alerts.
11. Paper trading, operational hardening and deployment.

Do not claim completion based on a prototype, mock data, or architecture document. External API credentials and paid subscriptions must be documented as dependencies. Continue implementation with clearly labelled fixtures where live access is not yet configured.
