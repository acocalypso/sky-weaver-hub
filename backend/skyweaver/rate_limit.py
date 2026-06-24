from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic


@dataclass(frozen=True)
class RateLimitStatus:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = RLock()

    def check(self, key: str) -> RateLimitStatus:
        now = monotonic()
        with self._lock:
            attempts = self._current_attempts(key, now)
            if len(attempts) < self.max_failures:
                return RateLimitStatus(allowed=True)
            retry_after = max(1, int((attempts[0] + self.window_seconds) - now))
            return RateLimitStatus(allowed=False, retry_after_seconds=retry_after)

    def record_failure(self, key: str) -> RateLimitStatus:
        now = monotonic()
        with self._lock:
            attempts = self._current_attempts(key, now)
            attempts.append(now)
            self._failures[key] = attempts
            if len(attempts) <= self.max_failures:
                return RateLimitStatus(allowed=True)
            retry_after = max(1, int((attempts[0] + self.window_seconds) - now))
            return RateLimitStatus(allowed=False, retry_after_seconds=retry_after)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _current_attempts(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        attempts = [attempt for attempt in self._failures.get(key, []) if attempt >= cutoff]
        self._failures[key] = attempts
        return attempts
