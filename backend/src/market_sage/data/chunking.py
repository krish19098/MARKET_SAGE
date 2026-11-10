"""Plan historical requests within a provider's per-request window."""

from __future__ import annotations

from datetime import datetime, timedelta

from market_sage.data.models import Interval
from market_sage.data.providers.base import ProviderCapabilities


def plan_chunks(
    caps: ProviderCapabilities, interval: Interval, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    if interval not in caps.max_days_per_request:
        raise ValueError(f"{caps.provider} does not declare a request window for {interval}")
    if end <= start:
        return []
    earliest = caps.earliest_date.get(interval)
    if earliest is not None:
        floor = datetime.combine(earliest, start.timetz())
        start = max(start, floor)
    step = timedelta(days=caps.max_days_per_request[interval])
    chunks, cur = [], start
    while cur < end:
        nxt = min(cur + step, end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks
