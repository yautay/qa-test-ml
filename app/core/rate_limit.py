from __future__ import annotations

import threading
import time
from collections import deque


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_sec: int) -> bool:
        if limit <= 0 or window_sec <= 0:
            return True

        now = time.monotonic()
        cutoff = now - float(window_sec)

        with self._lock:
            bucket = self._events.get(key)
            if bucket is None:
                bucket = deque()
                self._events[key] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now)
            return True


rate_limiter = InMemoryRateLimiter()
