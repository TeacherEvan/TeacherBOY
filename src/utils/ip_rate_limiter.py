import time
from collections import defaultdict
class IpRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests; self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
    def allow(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[ip] if t > window_start]
        if len(hits) >= self.max_requests: self._hits[ip] = hits; return False
        hits.append(now); self._hits[ip] = hits; return True
    def clear(self) -> None: self._hits.clear()
