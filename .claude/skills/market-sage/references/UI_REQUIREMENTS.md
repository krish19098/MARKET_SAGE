# Simple UI and Product Experience

## Product rule

Simple UI, serious intelligence. Do not spend development time on decorative polish at the expense of analytical correctness.

## Five primary screens

### 1. Home
- Market status and regime.
- Available budget and portfolio summary.
- Best current opportunities.
- Active alerts.
- Important risks and data freshness.

### 2. Invest
- Budget input.
- Balanced/growth-oriented preference.
- Proposed stocks and allocation amounts.
- Quantity, entry, stop, targets, costs and risk.
- Reserve cash.
- Why each stock was selected and why alternatives were rejected.
- Clear confirmation that recommendations are advisory.

### 3. My Trades
- User-entered or confirmed positions.
- Quantity, entry, current price and P&L.
- Stop, target, HOLD/EXIT assessment.
- Thesis status and latest alert.
- Distinguish actual fills from hypothetical prices.

### 4. Analyst
- Stock investigation.
- Price structure and timeframe context.
- Technical and volume evidence.
- Fundamental and sector context.
- Historical analogues.
- Bullish, bearish and neutral scenarios.
- Thesis, entry, invalidation and targets.

### 5. Performance
- Prediction ledger summaries.
- Directional and probability scores.
- Entry/exit timing.
- Early-warning lead time.
- False alerts.
- Potential losses avoided and upside missed.
- Model version and learning reports.

## Interaction requirements

- Responsive desktop/mobile layout.
- Fast loading and accessible typography.
- Minimal navigation and consistent terminology.
- Do not overload Home with technical charts.
- Detailed charts appear in focused analysis views.
- Clearly distinguish live, delayed, stale, simulated and historical data.
- Make BUY/HOLD/EXIT/AVOID status clear without implying certainty.
- Provide alert history and prediction timestamps.
- Never use colour alone to communicate risk or status.

## PWA and mobile

Start with a responsive PWA. Backend performs monitoring and analysis. Use Web Push where supported, while acknowledging platform delivery limitations. A native Android app is a later decision based on actual need, not an initial requirement.
