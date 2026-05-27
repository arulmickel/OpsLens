"""Sliding window rate limiter.

Thread-safe in a single process. Tracks (key, timestamp) attempts and
expires entries older than the window. The same primitive backs both
login lockout (counts only failures) and LLM/pipeline trigger limits
(counts every attempt).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        if max_attempts <= 0 or window_seconds <= 0:
            raise ValueError("max_attempts and window_seconds must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._clock = time.monotonic

    def _prune(self, q: Deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

    def check(self, key: str) -> RateLimitResult:
        with self._lock:
            now = self._clock()
            q = self._attempts[key]
            self._prune(q, now)
            count = len(q)
            allowed = count < self.max_attempts
            retry_after = 0
            if not allowed:
                retry_after = max(0, int(self.window_seconds - (now - q[0])))
            return RateLimitResult(
                allowed=allowed,
                remaining=max(0, self.max_attempts - count),
                retry_after_seconds=retry_after,
            )

    def record(self, key: str) -> RateLimitResult:
        with self._lock:
            now = self._clock()
            q = self._attempts[key]
            self._prune(q, now)
            if len(q) >= self.max_attempts:
                retry_after = max(0, int(self.window_seconds - (now - q[0])))
                return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=retry_after)
            q.append(now)
            return RateLimitResult(
                allowed=True,
                remaining=max(0, self.max_attempts - len(q)),
                retry_after_seconds=0,
            )

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)


# Default limiters used by the app.
LOGIN_LIMITER = SlidingWindowRateLimiter(max_attempts=5, window_seconds=15 * 60)
ACTION_LIMITER = SlidingWindowRateLimiter(max_attempts=10, window_seconds=5 * 60)
