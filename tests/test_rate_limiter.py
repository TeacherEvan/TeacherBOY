"""Tests for rate limiter service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from src.services.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter."""

    @pytest.fixture
    def limiter(self):
        """Create a RateLimiter instance with short window for testing."""
        return RateLimiter(max_requests=3, time_window_seconds=2)

    def test_allows_requests_under_limit(self, limiter):
        """Test that requests under limit are allowed."""
        chat_id = "test_chat_1"

        # First 3 requests should be allowed
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True

        # 4th request should be blocked
        assert limiter.is_allowed(chat_id) is False

    def test_rate_limit_resets_after_window(self, limiter):
        """Test that rate limit resets after time window."""
        import time

        chat_id = "test_chat_2"

        # Use up the limit
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is False

        # Wait for window to expire
        time.sleep(2.5)

        # Should be allowed again
        assert limiter.is_allowed(chat_id) is True

    def test_different_chats_independent(self, limiter):
        """Test that different chats have independent rate limits."""
        chat_id_1 = "test_chat_3"
        chat_id_2 = "test_chat_4"

        # Use up limit for chat 1
        assert limiter.is_allowed(chat_id_1) is True
        assert limiter.is_allowed(chat_id_1) is True
        assert limiter.is_allowed(chat_id_1) is True
        assert limiter.is_allowed(chat_id_1) is False

        # Chat 2 should still be allowed
        assert limiter.is_allowed(chat_id_2) is True

    def test_get_remaining_requests(self, limiter):
        """Test getting remaining request count."""
        chat_id = "test_chat_5"

        assert limiter.get_remaining_requests(chat_id) == 3

        limiter.is_allowed(chat_id)
        assert limiter.get_remaining_requests(chat_id) == 2

        limiter.is_allowed(chat_id)
        assert limiter.get_remaining_requests(chat_id) == 1

    def test_reset_chat(self, limiter):
        """Test resetting rate limit for a chat."""
        chat_id = "test_chat_6"

        # Use up the limit
        limiter.is_allowed(chat_id)
        limiter.is_allowed(chat_id)
        limiter.is_allowed(chat_id)
        assert limiter.is_allowed(chat_id) is False

        # Reset the chat
        limiter.reset_chat(chat_id)

        # Should be allowed again
        assert limiter.is_allowed(chat_id) is True

    def test_cleanup_old_entries(self, limiter):
        """Test cleanup of old chat entries."""
        import time

        chat_id = "test_chat_7"

        # Make a request
        limiter.is_allowed(chat_id)

        # Wait for window to expire
        time.sleep(2.5)

        # Cleanup
        limiter.cleanup_old_entries()

        # Verify history is cleaned
        assert limiter.get_remaining_requests(chat_id) == 3

    def test_admin_destructive_cleanup_uses_utc_consistently(self):
        """Admin destructive reservations should survive cleanup when UTC expiry has not passed."""

        class FixedDateTime(datetime):
            _utc_now = datetime(2026, 5, 31, 12, 0, 0)
            _local_now = datetime(2026, 5, 31, 19, 0, 0)

            @classmethod
            def utcnow(cls):
                return cls._utc_now

            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return tz.fromutc(cls._local_now.replace(tzinfo=tz))
                return cls._local_now

        limiter = RateLimiter()

        with patch("src.services.rate_limiter.datetime", FixedDateTime):
            reserved, message = limiter.reserve_admin_destructive_request(
                user_id="U-admin",
                target_chat_id="group_C999",
                token="tok-1",
                expires_at=FixedDateTime(2026, 5, 31, 12, 5, 0),
            )

            assert reserved is True
            assert message is None

            limiter.cleanup_old_entries()

            reserved_again, second_message = limiter.reserve_admin_destructive_request(
                user_id="U-admin",
                target_chat_id="group_C999",
                token="tok-2",
                expires_at=FixedDateTime(2026, 5, 31, 12, 5, 0),
            )

        assert reserved_again is False
        assert "already pending" in second_message.lower()

    def test_admin_destructive_cleanup_uses_same_lock_as_reserve_and_release(self):
        """Cleanup should acquire the admin destructive lock before mutating reservations."""

        class CountingLock:
            def __init__(self):
                self.enter_count = 0

            def __enter__(self):
                self.enter_count += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        limiter = RateLimiter()
        counting_lock = CountingLock()
        limiter._admin_destructive_lock = counting_lock  # type: ignore[assignment]

        limiter.cleanup_old_entries()

        assert counting_lock.enter_count == 1
