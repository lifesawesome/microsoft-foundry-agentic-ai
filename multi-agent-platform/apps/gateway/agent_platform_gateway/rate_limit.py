"""A minimal in-process token-bucket rate limiter keyed by principal."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """Allows up to `capacity` requests, refilling `refill_per_second` tokens."""

    def __init__(self, *, capacity: int = 30, refill_per_second: float = 0.5) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self._capacity - 1, updated_at=now)
            return True

        elapsed = now - bucket.updated_at
        bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill)
        bucket.updated_at = now
        if bucket.tokens < 1:
            return False
        bucket.tokens -= 1
        return True
