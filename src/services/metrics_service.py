"""Lightweight in-memory metrics for admin stats.

This is intentionally process-local (no persistence). It tracks basic counters and
recent timestamps useful for operational visibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Set
from collections import defaultdict


@dataclass
class MetricsSnapshot:
    started_at: datetime
    translation_requests_total: int
    translation_google_total: int
    translation_libre_total: int
    news_requests_total: int
    last_friend_added_at: Optional[datetime]
    last_friend_added_user_id: Optional[str]
    friends_follow_events_total: int
    friends_unfollow_events_total: int
    # New metrics
    rate_limited_requests: int
    failed_translations: int
    admin_commands_total: int
    unique_users_count: int
    unique_groups_count: int
    peak_hour: Optional[int]
    peak_hour_requests: int
    cache_hits_total: int
    cache_misses_total: int


@dataclass
class MetricsService:
    _started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    _translation_requests_total: int = 0
    _translation_google_total: int = 0
    _translation_libre_total: int = 0

    _news_requests_total: int = 0

    _last_friend_added_at: Optional[datetime] = None
    _last_friend_added_user_id: Optional[str] = None

    _friends_follow_events_total: int = 0
    _friends_unfollow_events_total: int = 0

    # New metrics tracking
    _rate_limited_requests: int = 0
    _failed_translations: int = 0
    _admin_commands_total: int = 0
    _unique_users: Set[str] = field(default_factory=set)
    _unique_groups: Set[str] = field(default_factory=set)
    _hourly_requests: dict = field(default_factory=lambda: defaultdict(int))
    _cache_hits_total: int = 0
    _cache_misses_total: int = 0

    def record_translation(self, provider: str, chat_id: Optional[str] = None) -> None:
        self._translation_requests_total += 1
        provider_lower = (provider or "").lower()
        if provider_lower == "google":
            self._translation_google_total += 1
        elif provider_lower == "libre":
            self._translation_libre_total += 1

        # Track hourly usage
        current_hour = datetime.now(timezone.utc).hour
        self._hourly_requests[current_hour] += 1

        # Track unique users/groups
        if chat_id:
            if chat_id.startswith("user_"):
                self._unique_users.add(chat_id)
            elif chat_id.startswith("group_"):
                self._unique_groups.add(chat_id)

    def record_news_request(self, chat_id: Optional[str] = None) -> None:
        self._news_requests_total += 1

        # Track hourly usage
        current_hour = datetime.now(timezone.utc).hour
        self._hourly_requests[current_hour] += 1

        # Track unique users/groups
        if chat_id:
            if chat_id.startswith("user_"):
                self._unique_users.add(chat_id)
            elif chat_id.startswith("group_"):
                self._unique_groups.add(chat_id)

    def record_friend_added(self, user_id: Optional[str]) -> None:
        self._last_friend_added_at = datetime.now(timezone.utc)
        self._last_friend_added_user_id = user_id
        self._friends_follow_events_total += 1

    def record_friend_removed(self, user_id: Optional[str]) -> None:
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

    def get_started_at(self) -> datetime:
        return self._started_at

    def get_uptime(self) -> timedelta:
        return datetime.now(timezone.utc) - self._started_at

    def snapshot(self) -> MetricsSnapshot:
        # Calculate peak hour
        peak_hour = None
        peak_hour_requests = 0
        if self._hourly_requests:
            peak_hour = max(self._hourly_requests, key=self._hourly_requests.get)
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
        )


metrics_service = MetricsService()
