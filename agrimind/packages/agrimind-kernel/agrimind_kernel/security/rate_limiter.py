"""In-memory sliding-window rate limiter (Redis in production)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._store: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        q = self._store[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_requests:
            return False
        q.append(now)
        return True

    def retry_after(self, key: str) -> float:
        q = self._store[key]
        if not q:
            return 0.0
        return max(0.0, self.window - (time.time() - q[0]))
