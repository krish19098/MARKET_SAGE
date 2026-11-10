"""Thread-safe multi-window rate limiter (per second / minute / hour)."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from market_sage.data.providers.base import RateLimit


class RateLimiter:
    def __init__(
        self,
        limit: RateLimit,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._windows: list[tuple[float, int]] = [(1.0, max(1, int(limit.per_second)))]
        if limit.per_minute:
            self._windows.append((60.0, limit.per_minute))
        if limit.per_hour:
            self._windows.append((3600.0, limit.per_hour))
        self._min_gap = 1.0 / limit.per_second if limit.per_second < 1 else 0.0
        self._calls: deque[float] = deque()
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._clock()
                horizon = max(w for w, _ in self._windows)
                while self._calls and now - self._calls[0] >= horizon:
                    self._calls.popleft()
                wait = 0.0
                for window, cap in self._windows:
                    in_window = [t for t in self._calls if now - t < window]
                    if len(in_window) >= cap:
                        wait = max(wait, window - (now - in_window[-cap]))
                if self._min_gap and self._calls:
                    wait = max(wait, self._min_gap - (now - self._calls[-1]))
                if wait <= 0:
                    self._calls.append(now)
                    return
                self._sleep(wait)
