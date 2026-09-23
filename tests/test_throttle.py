from __future__ import annotations

from listinglens.ingestion.throttle import TokenBucketThrottle
from tests.conftest import FakeClock


def test_acquire_does_not_sleep_while_tokens_available() -> None:
    clock = FakeClock()
    throttle = TokenBucketThrottle(rate=5.0, burst=5.0, clock=clock)
    for _ in range(5):
        throttle.acquire()
    assert clock.slept == []


def test_acquire_sleeps_for_the_correct_duration_once_exhausted() -> None:
    clock = FakeClock()
    throttle = TokenBucketThrottle(rate=5.0, burst=5.0, clock=clock)
    for _ in range(5):
        throttle.acquire()
    throttle.acquire()
    assert clock.slept == [0.2]


def test_burst_cap_limits_accumulated_tokens() -> None:
    clock = FakeClock()
    throttle = TokenBucketThrottle(rate=5.0, burst=5.0, clock=clock)
    clock.now = 1000.0
    for _ in range(5):
        throttle.acquire()
    assert clock.slept == []
    throttle.acquire()
    assert clock.slept == [0.2]
