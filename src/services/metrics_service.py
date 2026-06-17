"""Lightweight in-memory metrics for admin stats.

This is intentionally process-local (no persistence). It tracks basic counters and
recent timestamps useful for operational visibility.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


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
    # Detailed provider latency (per model, per request type)
    provider_model_latency_total: dict[str, float] = field(default_factory=dict)
    provider_model_latency_count: dict[str, int] = field(default_factory=dict)
    provider_request_type_latency_total: dict[str, float] = field(default_factory=dict)
    provider_request_type_latency_count: dict[str, int] = field(default_factory=dict)
    # Agent RED metrics
    agent_requests_total: dict[str, int] = field(default_factory=dict)
    agent_errors_total: dict[str, int] = field(default_factory=dict)
    agent_latency_ms_total: dict[str, float] = field(default_factory=dict)
    agent_latency_ms_count: dict[str, int] = field(default_factory=dict)
    # Connection pool metrics
    connection_pool_max_connections: int = 0
    connection_pool_max_keepalive: int = 0
    connection_pool_active_connections: int = 0
    connection_pool_idle_connections: int = 0
    connection_pool_requests_queued: int = 0
    connection_pool_errors: int = 0

    # Date extraction metrics
    extraction_requests_total: int = 0
    extraction_success_total: int = 0
    extraction_fallback_total: int = 0
    extraction_errors_total: int = 0
    extraction_provider_usage: dict[str, int] = field(default_factory=dict)
    extraction_event_count_total: int = 0


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

    # Detailed provider latency (per model, per request type)
    _provider_model_latency_total: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _provider_model_latency_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _provider_request_type_latency_total: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _provider_request_type_latency_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Agent RED metrics
    _agent_requests_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _agent_errors_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _agent_latency_ms_total: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _agent_latency_ms_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Connection pool metrics
    _connection_pool_max_connections: int = 0
    _connection_pool_max_keepalive: int = 0
    _connection_pool_active_connections: int = 0
    _connection_pool_idle_connections: int = 0
    _connection_pool_requests_queued: int = 0
    _connection_pool_errors: int = 0

    # Date extraction metrics
    _extraction_requests_total: int = 0
    _extraction_success_total: int = 0
    _extraction_fallback_total: int = 0
    _extraction_errors_total: int = 0
    _extraction_provider_used: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _extraction_event_count_total: int = 0

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

    def record_provider_model_latency(self, provider: str, model: str, latency_ms: float) -> None:
        """Record latency for a specific provider model."""
        key = f"{provider}:{model}"
        self._provider_model_latency_total[key] += latency_ms
        self._provider_model_latency_count[key] += 1

    def record_provider_request_type_latency(self, provider: str, request_type: str, latency_ms: float) -> None:
        """Record latency for a specific provider request type."""
        key = f"{provider}:{request_type}"
        self._provider_request_type_latency_total[key] += latency_ms
        self._provider_request_type_latency_count[key] += 1

    def get_provider_latency_avg(self, provider: str) -> float:
        """Get average latency for a provider in milliseconds."""
        count = self._provider_latency_ms_count.get(provider, 0)
        if count == 0:
            return 0.0
        return self._provider_latency_ms_total[provider] / count

    def get_provider_model_latency_avg(self, provider: str, model: str) -> float:
        """Get average latency for a specific provider model."""
        key = f"{provider}:{model}"
        count = self._provider_model_latency_count.get(key, 0)
        if count == 0:
            return 0.0
        return self._provider_model_latency_total[key] / count

    def get_provider_request_type_latency_avg(self, provider: str, request_type: str) -> float:
        """Get average latency for a specific provider request type."""
        key = f"{provider}:{request_type}"
        count = self._provider_request_type_latency_count.get(key, 0)
        if count == 0:
            return 0.0
        return self._provider_request_type_latency_total[key] / count

    def record_agent_request(
        self, agent_name: str, message_type: str | None = None, duration_ms: float | None = None, success: bool = True
    ) -> None:
        """Record an agent request for RED metrics.

        Args:
            agent_name: Name of the agent
            message_type: Type of message (text, image, file)
            duration_ms: Latency in milliseconds
            success: Whether the request succeeded
        """
        key = f"{agent_name}:{message_type}" if message_type else agent_name
        self._agent_requests_total[key] += 1
        if not success:
            self._agent_errors_total[key] += 1
        if duration_ms is not None:
            self._agent_latency_ms_total[key] += duration_ms
            self._agent_latency_ms_count[key] += 1

    def get_agent_latency_avg(self, agent_name: str, message_type: str | None = None) -> float:
        """Get average latency for an agent in milliseconds."""
        key = f"{agent_name}:{message_type}" if message_type else agent_name
        count = self._agent_latency_ms_count.get(key, 0)
        if count == 0:
            return 0.0
        return self._agent_latency_ms_total[key] / count

    def get_agent_error_rate(self, agent_name: str, message_type: str | None = None) -> float:
        """Get error rate for an agent (0.0 to 1.0)."""
        key = f"{agent_name}:{message_type}" if message_type else agent_name
        total = self._agent_requests_total.get(key, 0)
        if total == 0:
            return 0.0
        return self._agent_errors_total.get(key, 0) / total

    def get_agent_requests_total(self, agent_name: str, message_type: str | None = None) -> int:
        """Get total request count for an agent."""
        key = f"{agent_name}:{message_type}" if message_type else agent_name
        return self._agent_requests_total.get(key, 0)

    def update_connection_pool_stats(
        self,
        max_connections: int,
        max_keepalive: int,
        active: int = 0,
        idle: int = 0,
        queued: int = 0,
        errors: int = 0,
    ) -> None:
        """Update connection pool statistics."""
        self._connection_pool_max_connections = max_connections
        self._connection_pool_max_keepalive = max_keepalive
        self._connection_pool_active_connections = active
        self._connection_pool_idle_connections = idle
        self._connection_pool_requests_queued = queued
        self._connection_pool_errors = errors

    def record_connection_pool_error(self) -> None:
        """Record a connection pool error."""
        self._connection_pool_errors += 1

    def record_extraction_request(self, provider: str | None, success: bool, event_count: int = 0, used_fallback: bool = False) -> None:
        """Record a date extraction request attempt.

        Args:
            provider: Which provider was used (gemini, openrouter, etc.)
            success: Whether the AI extraction succeeded
            event_count: Number of events extracted
            used_fallback: Whether regex fallback was used
        """
        self._extraction_requests_total += 1
        if success:
            self._extraction_success_total += 1
        else:
            self._extraction_errors_total += 1
        if used_fallback:
            self._extraction_fallback_total += 1
        if provider:
            self._extraction_provider_used[provider] += 1
        if event_count > 0:
            self._extraction_event_count_total += event_count

    def get_extraction_stats(self) -> dict[str, Any]:
        """Get extraction statistics."""
        return {
            "total_requests": self._extraction_requests_total,
            "success_total": self._extraction_success_total,
            "fallback_total": self._extraction_fallback_total,
            "errors_total": self._extraction_errors_total,
            "provider_usage": dict(self._extraction_provider_used),
            "total_events_extracted": self._extraction_event_count_total,
            "success_rate": (
                self._extraction_success_total / self._extraction_requests_total
                if self._extraction_requests_total > 0
                else 0.0
            ),
            "fallback_rate": (
                self._extraction_fallback_total / self._extraction_requests_total
                if self._extraction_requests_total > 0
                else 0.0
            ),
        }

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
            provider_model_latency_total=dict(self._provider_model_latency_total),
            provider_model_latency_count=dict(self._provider_model_latency_count),
            provider_request_type_latency_total=dict(self._provider_request_type_latency_total),
            provider_request_type_latency_count=dict(self._provider_request_type_latency_count),
            agent_requests_total=dict(self._agent_requests_total),
            agent_errors_total=dict(self._agent_errors_total),
            agent_latency_ms_total=dict(self._agent_latency_ms_total),
            agent_latency_ms_count=dict(self._agent_latency_ms_count),
            connection_pool_max_connections=self._connection_pool_max_connections,
            connection_pool_max_keepalive=self._connection_pool_max_keepalive,
            connection_pool_active_connections=self._connection_pool_active_connections,
            connection_pool_idle_connections=self._connection_pool_idle_connections,
            connection_pool_requests_queued=self._connection_pool_requests_queued,
            connection_pool_errors=self._connection_pool_errors,
            extraction_requests_total=self._extraction_requests_total,
            extraction_success_total=self._extraction_success_total,
            extraction_fallback_total=self._extraction_fallback_total,
            extraction_errors_total=self._extraction_errors_total,
            extraction_provider_usage=dict(self._extraction_provider_used),
            extraction_event_count_total=self._extraction_event_count_total,
        )


metrics_service = MetricsService()
