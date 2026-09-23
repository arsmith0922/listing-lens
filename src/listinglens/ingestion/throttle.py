from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class TokenBucketThrottle:
    def __init__(self, rate: float, burst: float, clock: Clock) -> None:
        self._rate = rate
        self._burst = burst
        self._clock = clock
        self._tokens = burst
        self._last_check = clock.monotonic()

    def acquire(self) -> None:
        now = self._clock.monotonic()
        elapsed = now - self._last_check
        self._last_check = now
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)

        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self._rate
            self._clock.sleep(wait)
            self._last_check = self._clock.monotonic()
            self._tokens = 0.0
        else:
            self._tokens -= 1.0
