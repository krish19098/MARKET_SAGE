# Continuous Monitoring and Predictive Alerts

## Architecture

An always-on backend service consumes licensed market feeds, updates features, evaluates active positions and watchlists, and sends notifications. The browser or mobile device must not be responsible for continuous analysis. Monitoring must continue when the user's device is offline.

Use streaming feeds where available and rate-limited polling as fallback. Track provider latency, stale data, reconnects, dropped events and candle finalisation.

## Alert classes

- New BUY opportunity.
- Early bullish development.
- Early bearish development.
- Early deterioration of an active thesis.
- Approaching entry trigger.
- Approaching stop/invalidation.
- Confirmed stop/exit trigger.
- Target achieved.
- Partial-profit or trailing-stop suggestion.
- Market/sector regime change.
- Material corporate event.
- Data-provider failure or stale feed.

## Predictive timing

Distinguish:
1. **Early warning:** risk/opportunity is developing; trigger not confirmed.
2. **Approaching trigger:** price or evidence is near a defined level/condition.
3. **Confirmed trigger:** the pre-defined event condition has occurred.

Never label an already completed event as a prediction. For each alert record creation time, data cutoff, event forecast, probability/confidence, supporting evidence, invalidation condition, and later event time. Measure lead time and false-alert rate.

## Trade monitoring

For every active or user-entered position assess:
- Original thesis remains valid?
- Trend, momentum, volume and sector context changed?
- Stop, target or invalidation approached/triggered?
- Is reward/risk still acceptable?
- Is there a justified partial or full exit?
- Is an intraday risk condition overriding the expected swing horizon?

Avoid repeated alerts for insignificant price fluctuations. Use state transitions, cooldowns and deduplication without suppressing material changes.

## Delivery

Support browser push/PWA notifications initially and future native mobile integration if needed. Log notification creation, delivery acknowledgement where available, retries and failure. Do not promise guaranteed instant delivery across all operating systems. Provide in-app alert history as the reliable record.

## Fail-safe

If feed is stale, market calendar is uncertain, provider disconnects, or critical features cannot be calculated, display the issue and suppress recommendations dependent on that data. Never continue to label stale analysis as live.
