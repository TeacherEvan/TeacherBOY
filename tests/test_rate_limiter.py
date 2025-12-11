"""Unit tests for rate limiter service."""

import pytest
from datetime import datetime, timedelta
from src.services.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter class."""

    def test_init_default_values(self):
        """Test rate limiter initialization with default values."""
        limiter = RateLimiter()
        assert limiter.max_requests == 10
        assert limiter.window == timedelta(seconds=60)

    def test_init_custom_values(self):
        """Test rate limiter initialization with custom values."""
        limiter = RateLimiter(max_requests=5, window_seconds=30)
        assert limiter.max_requests == 5
        assert limiter.window == timedelta(seconds=30)

    def test_is_allowed_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        chat_id = "test_chat_1"

        # First 3 requests should be allowed
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True

    def test_is_allowed_exceeds_limit(self):
        """Test that requests exceeding limit are rejected."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        chat_id = "test_chat_2"

        # First 2 requests allowed
        assert limiter.is_allowed(chat_id) is True
        assert limiter.is_allowed(chat_id) is True

        # Third request should be rejected
        assert limiter.is_allowed(chat_id) is False

    def test_different_chats_independent(self):
        """Test that different chats have independent rate limits."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        chat_id_1 = "chat_1"
        chat_id_2 = "chat_2"

        # Both chats should have their own limits
        assert limiter.is_allowed(chat_id_1) is True
        assert limiter.is_allowed(chat_id_1) is True
        assert limiter.is_allowed(chat_id_1) is False  # Limit reached for chat_1

        # chat_2 should still be allowed
        assert limiter.is_allowed(chat_id_2) is True
        assert limiter.is_allowed(chat_id_2) is True

    def test_get_remaining_requests(self):
        """Test getting remaining request count."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        chat_id = "test_chat_3"

        assert limiter.get_remaining_requests(chat_id) == 5
        limiter.is_allowed(chat_id)
        assert limiter.get_remaining_requests(chat_id) == 4
        limiter.is_allowed(chat_id)
        assert limiter.get_remaining_requests(chat_id) == 3

    def test_reset_chat(self):
        """Test resetting rate limit for a specific chat."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        chat_id = "test_chat_4"

        # Use up the limit
        limiter.is_allowed(chat_id)
        limiter.is_allowed(chat_id)
        assert limiter.is_allowed(chat_id) is False

        # Reset and verify
        limiter.reset_chat(chat_id)
        assert limiter.is_allowed(chat_id) is True

    def test_window_cleanup(self):
        """Test that old requests are cleaned up properly."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)  # 1 second window
        chat_id = "test_chat_5"

        # Use up the limit
        limiter.is_allowed(chat_id)
        limiter.is_allowed(chat_id)
        assert limiter.is_allowed(chat_id) is False

        # Wait for window to expire
        import time

        time.sleep(1.1)

        # Should be allowed again after window expires
        assert limiter.is_allowed(chat_id) is True

    def test_singleton_import(self):
        """Test that singleton instance can be imported."""
        from src.services.rate_limiter import rate_limiter

        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)
        assert rate_limiter.max_requests == 10
        assert rate_limiter.window == timedelta(seconds=60)
