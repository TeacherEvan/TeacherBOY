"""N+1 Query Detection for Convex and other services.

This module provides tools to detect and prevent N+1 query patterns
by tracking query counts per request/origin and alerting when thresholds
are exceeded.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueryStats:
    """Statistics for a query pattern."""

    table: str
    method: str
    count: int = 0
    total_latency_ms: float = 0.0
    distinct_keys: set[str] = field(default_factory=set)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.count if self.count > 0 else 0.0


class N1Detector:
    """Detects potential N+1 query patterns."""

    def __init__(
        self,
        threshold: int = 5,
        window_seconds: float = 60.0,
        enabled: bool = True,
    ):
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.enabled = enabled
        self._queries: dict[str, QueryStats] = {}
        self._call_stacks: dict[str, list[str]] = defaultdict(list)

    def _make_key(self, table: str, method: str, origin: str = "") -> str:
        """Create a key for tracking query patterns."""
        return f"{table}:{method}:{origin}"

    def record_query(
        self,
        table: str,
        method: str,
        key: str | None = None,
        latency_ms: float = 0.0,
        origin: str = "",
    ) -> None:
        """Record a query execution for N+1 detection."""
        if not self.enabled:
            return

        now = time.time()
        query_key = self._make_key(table, method, origin)
        stats = self._queries.get(query_key)

        if stats is None:
            stats = QueryStats(table=table, method=method)
            self._queries[query_key] = stats

        stats.count += 1
        stats.total_latency_ms += latency_ms
        stats.last_seen = now
        if key:
            stats.distinct_keys.add(key)

        # Check if we've exceeded threshold
        if stats.count >= self.threshold:
            logger.warning(
                "🔴 N+1 DETECTED: %s.%s called %d times in %.1fs (origin: %s, distinct keys: %d)",
                table,
                method,
                stats.count,
                stats.last_seen - stats.first_seen,
                origin or "unknown",
                len(stats.distinct_keys),
            )

    def record_convex_query(
        self,
        table: str,
        method: str,
        group_id: str,
        latency_ms: float = 0.0,
    ) -> None:
        """Convenience method for Convex queries with group_id as key."""
        self.record_query(table, method, key=group_id, latency_ms=latency_ms, origin="convex")

    def get_stats(self) -> dict[str, Any]:
        """Get current query statistics."""
        return {
            key: {
                "table": stats.table,
                "method": stats.method,
                "count": stats.count,
                "avg_latency_ms": stats.avg_latency_ms,
                "distinct_keys": len(stats.distinct_keys),
                "duration_seconds": stats.last_seen - stats.first_seen,
            }
            for key, stats in self._queries.items()
            if stats.count > 1
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self._queries.clear()
        self._call_stacks.clear()


# Global detector instance
n1_detector = N1Detector()


class QueryCache:
    """Simple in-memory cache with TTL for query results."""

    def __init__(self, ttl_seconds: float = 30.0, max_size: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: dict[str, tuple[Any, float]] = {}

    def _make_key(self, table: str, method: str, *args) -> str:
        return f"{table}:{method}:{':'.join(str(a) for a in args)}"

    def get(self, table: str, method: str, *args) -> Any | None:
        key = self._make_key(table, method, *args)
        if key in self._cache:
            value, expires_at = self._cache[key]
            if time.time() < expires_at:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, table: str, method: str, *args, value: Any) -> None:
        key = self._make_key(table, method, *args)
        if len(self._cache) >= self.max_size:
            # Remove oldest entry
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
        self._cache[key] = (value, time.time() + self.ttl_seconds)

    def invalidate(self, table: str, method: str, *args) -> None:
        key = self._make_key(table, method, *args)
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


# Global cache instance
query_cache = QueryCache()