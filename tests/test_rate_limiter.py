"""Tests for rate limiter service."""

import pytest
from datetime import datetime, timedelta
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
