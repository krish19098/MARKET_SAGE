# Senior Analyst Intelligence Methodology

## Purpose

The analyst layer must interpret context and build an evidence-based thesis, not merely list indicator values. It should behave like a disciplined senior equity analyst and swing-trading strategist. Its conclusions must remain traceable to timestamped data and reproducible calculations.

## Five technical research categories

### 1. Market and price structure
- Higher highs/higher lows and lower highs/lower lows.
- Trend direction, strength, maturity and possible transition.
- Horizontal support/resistance, supply/demand zones.
- Breakouts, breakdowns, retests, failed breakouts and reversals.
- Top-down timeframe alignment: weekly/daily context with 4h/1h/15m/5m where reliable data supports it.
- Relative performance against NIFTY, relevant index and sector.
- Consolidation, range expansion and gap behaviour.

### 2. Core indicators
- SMA and EMA.
- RSI and Stochastic.
- MACD.
- Bollinger Bands.
- ATR and ADX.
- VWAP.
- Momentum and relative strength.
- Volatility and trend-persistence features.

Indicators are contextual evidence, not standalone buy/sell rules. Thresholds must be validated and may vary by instrument/regime.

### 3. Chart and candlestick patterns
Reversal: head-and-shoulders, inverse head-and-shoulders, double top/bottom, morning/evening star, hammer, inverted hammer, shooting star, engulfing.
Continuation: flags, pennants, triangles, cup-and-handle and consolidations.
Single-candle: doji, marubozu and other context-relevant formations.

Pattern detection must account for trend, location, confirmation, volume, volatility, sample size and failure rate. Do not infer a reliable pattern from a candle name alone.

### 4. Volume and liquidity
- Relative/unusual volume.
- Volume-price divergence.
- Delivery activity.
- Volume profile and high-volume price zones where data permits.
- Acceptance/rejection, liquidity zones and potential sweeps.
- Breakout participation and accumulation/distribution clues.

A volume spike is not proof of institutional buying. Label direct observations separately from inferred activity.

### 5. Risk and execution
- Entry range and trigger.
- Stop/invalidation level.
- Targets and partial booking.
- Risk/reward and expected value.
- ATR/volatility-adjusted sizing.
- Liquidity, spread, slippage and gap risk.
- Correlation, concentration and portfolio exposure.
- Costs and realistic execution assumptions.

No complete trade recommendation without an invalidation point and risk calculation.

## Market context layer

Connect stock-level behaviour with:
- NIFTY, BANKNIFTY and relevant indices.
- Sector trend and breadth.
- Volatility and risk appetite.
- FII/DII disclosures with correct publication timing.
- Global context when material.
- Earnings, results, guidance and corporate actions.
- Revenue/earnings growth, debt, cash flow, ROE, ROCE and valuation.
- Peer comparison and the company's own historical valuation.
- Catalysts and material risks.

Distinguish a company-specific move from a sector-wide or market-wide move. Falling price alone does not establish undervaluation. Detect possible value traps.

## Historical market memory

Build numerical, point-in-time historical analogues. Potential techniques:
- Normalised feature-vector similarity.
- Nearest neighbours.
- Clustering.
- Dynamic Time Warping where appropriate.
- Regime-conditioned comparisons.

Compare price structure, momentum, volume, volatility, sector performance and market regime. For each analogue set, show sample size, time period, similarity method, forward return distribution, maximum favourable/adverse excursion and failure frequency across 1/3/5/10/20 sessions where applicable.

Historical similarity is evidence, not a guarantee that the future will repeat. Avoid selecting analogues using future outcomes.

## Investment thesis format

For each shortlisted stock, produce:
1. Current market and sector context.
2. Company fundamentals and valuation.
3. Technical structure and timeframe alignment.
4. Volume/liquidity evidence.
5. Historical analogues and their sample quality.
6. Bullish scenario.
7. Bearish scenario.
8. Neutral scenario.
9. Catalysts and upcoming events.
10. Expected return range and downside.
11. Entry, stop/invalidation, targets and holding horizon.
12. What would change the view.
13. Why selected over alternatives.

The analyst must challenge its own thesis and surface contradictory evidence. Do not hide disagreement between analytical modules.
