from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable

Clock = Callable[[], float]


class TokenBuckets:
    def __init__(
        self, rate: float, burst: float, clock: Clock = time.monotonic, max_keys: int = 10_000
    ) -> None:
        self.rate = rate
        self.burst = burst
        self.clock = clock
        self.max_keys = max_keys
        self._state: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = self.clock()
        tokens, last = self._state.pop(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        self._state[key] = (tokens, now)
        while len(self._state) > self.max_keys:
            self._state.popitem(last=False)
        return allowed


class FailedAuthThrottle:
    def __init__(
        self,
        limit: int = 10,
        window: float = 60.0,
        clock: Clock = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self.max_keys = max_keys
        self._hits: OrderedDict[str, list[float]] = OrderedDict()

    def _recent(self, key: str) -> list[float]:
        cutoff = self.clock() - self.window
        return [t for t in self._hits.get(key, []) if t > cutoff]

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.limit

    def record_failure(self, key: str) -> None:
        hits = self._recent(key)
        hits.append(self.clock())
        self._hits.pop(key, None)
        self._hits[key] = hits
        while len(self._hits) > self.max_keys:
            self._hits.popitem(last=False)


class InflightCap:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.current = 0

    def acquire(self) -> bool:
        if self.current >= self.limit:
            return False
        self.current += 1
        return True

    def release(self) -> None:
        self.current = max(0, self.current - 1)
