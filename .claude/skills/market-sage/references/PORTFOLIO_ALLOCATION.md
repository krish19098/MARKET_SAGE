# Budget-Based Portfolio Allocation and Risk

## Objective

The user enters available capital; the system investigates the eligible universe and proposes a portfolio allocation. It must not require the user to manually choose stocks first.

## Allocation process

1. Validate available capital, risk preference, current holdings and constraints.
2. Scan eligible securities.
3. Rank opportunities using validated risk-adjusted evidence, not arbitrary scores.
4. Check data freshness, liquidity, spreads and execution feasibility.
5. Calculate entry, stop/invalidation and target levels.
6. Size positions from risk budget and affordable quantity.
7. Assess correlations, sector concentration and portfolio exposure.
8. Include brokerage, STT, exchange charges, GST, stamp duty, slippage and applicable taxes as appropriate.
9. Keep cash reserve where useful.
10. Explain selected stocks and rejected alternatives.

## Example format

For ₹20,000, an illustrative result could be:
- Stock A: ₹8,000.
- Stock B: ₹6,000.
- Stock C: ₹4,000.
- Reserve: ₹2,000.

These figures are examples only. Actual allocations must be computed from current validated opportunities, share prices, lot/quantity constraints, risk limits and costs. Do not hardcode this distribution.

## Modes

- **Balanced:** prioritise diversification and lower portfolio volatility within the user's risk constraints.
- **Growth-oriented:** seek higher expected risk-adjusted returns while respecting the same hard risk controls.

Explain trade-offs. The system may recommend holding some or all capital in cash if opportunities are poor.

## Position sizing

Calculate quantity using:
- Capital available.
- Risk budget per position.
- Entry-to-stop distance.
- Costs and slippage.
- Liquidity and spread.
- Existing portfolio exposure.
- Correlation and sector concentration.
- Maximum concurrent positions and daily loss limits.

Show estimated maximum loss at stop and portfolio-level downside. Do not assume the stop will always fill at its exact price; gap and liquidity risks must be disclosed.

## User-entered positions

Allow the user to enter symbol, exchange, average purchase price, quantity, date and any relevant costs. Clearly distinguish actual user execution data from hypothetical model prices. Do not assume a recommendation was executed unless the user confirms or a permitted broker integration verifies it.

## Safety

No investment is risk-free. Do not force the entire budget into the market. Do not chase ₹500 daily profit. Do not use leverage or derivatives by default. Do not recommend a stock solely because it is cheap or affordable. If risk cannot be calculated, do not allocate.
