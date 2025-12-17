"""Lightweight in-memory metrics for admin stats.

This is intentionally process-local (no persistence). It tracks basic counters and
recent timestamps useful for operational visibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class MetricsSnapshot:
    started_at: datetime
    translation_requests_total: int
    translation_google_total: int
    translation_libre_total: int
    news_requests_total: int
    last_friend_added_at: Optional[datetime]
    last_friend_added_user_id: Optional[str]


@dataclass
class MetricsService:
    _started_at: datetime = field(default_factory=datetime.utcnow)

    _translation_requests_total: int = 0
    _translation_google_total: int = 0
    _translation_libre_total: int = 0

    _news_requests_total: int = 0

    _last_friend_added_at: Optional[datetime] = None
    _last_friend_added_user_id: Optional[str] = None

    def record_translation(self, provider: str) -> None:
        self._translation_requests_total += 1
        provider_lower = (provider or "").lower()
        if provider_lower == "google":
            self._translation_google_total += 1
        elif provider_lower == "libre":
            self._translation_libre_total += 1

    def record_news_request(self) -> None:
        self._news_requests_total += 1

    def record_friend_added(self, user_id: Optional[str]) -> None:
        self._last_friend_added_at = datetime.utcnow()
        self._last_friend_added_user_id = user_id

    def get_started_at(self) -> datetime:
        return self._started_at

    def get_uptime(self) -> timedelta:
        return datetime.utcnow() - self._started_at

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            started_at=self._started_at,
            translation_requests_total=self._translation_requests_total,
            translation_google_total=self._translation_google_total,
            translation_libre_total=self._translation_libre_total,
            news_requests_total=self._news_requests_total,
            last_friend_added_at=self._last_friend_added_at,
            last_friend_added_user_id=self._last_friend_added_user_id,
        )


metrics_service = MetricsService()
