"""Lightweight in-memory metrics for admin stats.

This is intentionally process-local (no persistence). It tracks basic counters and
recent timestamps useful for operational visibility.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class MetricsSnapshot:
    started_at: datetime
    translation_requests_total: int
    translation_google_total: int
    translation_libre_total: int
    news_requests_total: int
    last_friend_added_at: datetime | None
    last_friend_added_user_id: str | None
    friends_follow_events_total: int
    friends_unfollow_events_total: int
    # New metrics
    rate_limited_requests: int
    failed_translations: int
    admin_commands_total: int
    unique_users_count: int
    unique_groups_count: int
    peak_hour: int | None
    peak_hour_requests: int
    cache_hits_total: int
    cache_misses_total: int
    # Provider latency metrics
    provider_latency_ms_total: dict[str, float] = field(default_factory=dict)
    provider_latency_ms_count: dict[str, int] = field(default_factory=dict)


class _BoundedSet:
    """Set with maximum size using FIFO eviction."""

    def __init__(self, max_size: int = 10000):
        self._max_size = max_size
        self._set: set[str] = set()
        self._queue: deque[str] = deque()

    def add(self, item: str) -> None:
        if item in self._set:
            return
        if len(self._set) >= self._max_size:
            oldest = self._queue.popleft()
            self._set.discard(oldest)
        self._set.add(item)
        self._queue.append(item)

    def __len__(self) -> int:
        return len(self._set)

    def __contains__(self, item: str) -> bool:
        return item in self._set


@dataclass
class MetricsService:
    _started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    _translation_requests_total: int = 0
    _translation_google_total: int = 0
    _translation_libre_total: int = 0

    _news_requests_total: int = 0

    _last_friend_added_at: datetime | None = None
    _last_friend_added_user_id: str | None = None

    _friends_follow_events_total: int = 0
    _friends_unfollow_events_total: int = 0

    # New metrics tracking
    _rate_limited_requests: int = 0
    _failed_translations: int = 0
    _admin_commands_total: int = 0

    # Bounded sets to prevent unbounded memory growth
    _unique_users: _BoundedSet = field(default_factory=lambda: _BoundedSet(10000))
    _unique_groups: _BoundedSet = field(default_factory=lambda: _BoundedSet(10000))
    _hourly_requests: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    _cache_hits_total: int = 0
    _cache_misses_total: int = 0

    # Provider latency tracking
    _provider_latency_ms_total: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _provider_latency_ms_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record_translation(self, provider: str, chat_id: str | None = None) -> None:
        self._translation_requests_total += 1
        provider_lower = (provider or "").lower()
        if provider_lower == "google":
            self._translation_google_total += 1
        elif provider_lower == "libre":
            self._translation_libre_total += 1

        # Track hourly usage
        current_hour = datetime.now(UTC).hour
        self._hourly_requests[current_hour] += 1

        # Track unique users/groups with bounded storage
        if chat_id:
            if chat_id.startswith("user_"):
                self._unique_users.add(chat_id)
            elif chat_id.startswith("group_"):
                self._unique_groups.add(chat_id)

    def record_news_request(self, chat_id: str | None = None) -> None:
        self._news_requests_total += 1

        # Track hourly usage
        current_hour = datetime.now(UTC).hour
        self._hourly_requests[current_hour] += 1

        # Track unique users/groups with bounded storage
        if chat_id:
            if chat_id.startswith("user_"):
                self._unique_users.add(chat_id)
            elif chat_id.startswith("group_"):
                self._unique_groups.add(chat_id)

    def record_friend_added(self, user_id: str | None) -> None:
        self._last_friend_added_at = datetime.now(UTC)
        self._last_friend_added_user_id = user_id
        self._friends_follow_events_total += 1

    def record_friend_removed(self, user_id: str | None) -> None:
        # LINE does not provide a way to query total friend count; this is a
        # process-local best-effort counter based on follow/unfollow events.
        self._friends_unfollow_events_total += 1

    def record_rate_limited(self) -> None:
        """Record a rate-limited request."""
        self._rate_limited_requests += 1

    def record_failed_translation(self) -> None:
        """Record a failed translation attempt."""
        self._failed_translations += 1

    def record_admin_command(self) -> None:
        """Record an admin command execution."""
        self._admin_commands_total += 1

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits_total += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._cache_misses_total += 1

    def record_provider_latency(self, provider: str, latency_ms: float) -> None:
        """Record latency for a provider in milliseconds."""
        self._provider_latency_ms_total[provider] += latency_ms
        self._provider_latency_ms_count[provider] += 1

    def get_provider_latency_avg(self, provider: str) -> float:
        """Get average latency for a provider in milliseconds."""
        count = self._provider_latency_ms_count.get(provider, 0)
        if count == 0:
            return 0.0
        return self._provider_latency_ms_total[provider] / count

    def get_started_at(self) -> datetime:
        return self._started_at

    def get_uptime(self) -> timedelta:
        return datetime.now(UTC) - self._started_at

    def snapshot(self) -> MetricsSnapshot:
        # Calculate peak hour
        peak_hour = None
        peak_hour_requests = 0
        if self._hourly_requests:
            peak_hour = max(self._hourly_requests, key=lambda k: self._hourly_requests[k])
            peak_hour_requests = self._hourly_requests[peak_hour]

        return MetricsSnapshot(
            started_at=self._started_at,
            translation_requests_total=self._translation_requests_total,
            translation_google_total=self._translation_google_total,
            translation_libre_total=self._translation_libre_total,
            news_requests_total=self._news_requests_total,
            last_friend_added_at=self._last_friend_added_at,
            last_friend_added_user_id=self._last_friend_added_user_id,
            friends_follow_events_total=self._friends_follow_events_total,
            friends_unfollow_events_total=self._friends_unfollow_events_total,
            rate_limited_requests=self._rate_limited_requests,
            failed_translations=self._failed_translations,
            admin_commands_total=self._admin_commands_total,
            unique_users_count=len(self._unique_users),
            unique_groups_count=len(self._unique_groups),
            peak_hour=peak_hour,
            peak_hour_requests=peak_hour_requests,
            cache_hits_total=self._cache_hits_total,
            cache_misses_total=self._cache_misses_total,
            provider_latency_ms_total=dict(self._provider_latency_ms_total),
            provider_latency_ms_count=dict(self._provider_latency_ms_count),
        )


metrics_service = MetricsService()
