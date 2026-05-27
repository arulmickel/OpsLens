"""Sliding window rate limiter tests."""
from __future__ import annotations

import pytest

from src.security.rate_limiter import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock):
    rl = SlidingWindowRateLimiter(max_attempts=5, window_seconds=900)
    rl._clock = clock
    return rl


def test_allows_up_to_max_attempts(limiter):
    for _ in range(5):
        assert limiter.record("user@example.com").allowed
    blocked = limiter.record("user@example.com")
    assert not blocked.allowed
    assert blocked.retry_after_seconds > 0


def test_lockout_clears_after_window(limiter, clock):
    for _ in range(5):
        limiter.record("alice")
    assert not limiter.record("alice").allowed
    clock.advance(901)
    assert limiter.record("alice").allowed


def test_keys_are_isolated(limiter):
    for _ in range(5):
        limiter.record("alice")
    # Bob is not affected by alice being locked out.
    assert limiter.record("bob").allowed


def test_check_does_not_consume(limiter):
    for _ in range(4):
        limiter.record("eve")
    assert limiter.check("eve").allowed
    # After check, we can still record one more attempt.
    assert limiter.record("eve").allowed
    assert not limiter.record("eve").allowed


def test_reset(limiter):
    for _ in range(5):
        limiter.record("frank")
    assert not limiter.record("frank").allowed
    limiter.reset("frank")
    assert limiter.record("frank").allowed
