"""Rate limiting service to prevent API abuse and excessive translation requests."""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket-style rate limiter for controlling translation request frequency.

    This prevents abuse and controls API costs by limiting the number of
    translation requests per chat within a sliding time window.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter with configurable limits.

        Args:
            max_requests: Maximum number of requests allowed per window
            window_seconds: Time window duration in seconds
        """
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests: Dict[str, List[datetime]] = defaultdict(list)

    def is_allowed(self, chat_id: str) -> bool:
        """
        Check if a request is allowed for the given chat.

        This method implements a sliding window algorithm that:
        1. Removes expired timestamps outside the window
        2. Checks if request count is below limit
        3. Records the current request timestamp if allowed

        Args:
            chat_id: Unique identifier for the chat/group

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = datetime.now()

        # Clean up old requests outside the time window
        self.requests[chat_id] = [
            timestamp
            for timestamp in self.requests[chat_id]
            if now - timestamp < self.window
        ]

        # Check if limit exceeded
        if len(self.requests[chat_id]) >= self.max_requests:
            logger.warning(
                f"🚨 Rate limit exceeded for chat {chat_id}: "
                f"{len(self.requests[chat_id])}/{self.max_requests} "
                f"requests in {self.window.seconds}s"
            )
            return False

        # Record this request
        self.requests[chat_id].append(now)
        logger.debug(
            f"✅ Rate limit check passed for chat {chat_id}: "
            f"{len(self.requests[chat_id])}/{self.max_requests} requests"
        )
        return True

    def get_remaining_requests(self, chat_id: str) -> int:
        """
        Get number of remaining requests for a chat.

        Args:
            chat_id: Unique identifier for the chat/group

        Returns:
            Number of requests remaining before rate limit
        """
        now = datetime.now()
        self.requests[chat_id] = [
            timestamp
            for timestamp in self.requests[chat_id]
            if now - timestamp < self.window
        ]
        return max(0, self.max_requests - len(self.requests[chat_id]))

    def reset_chat(self, chat_id: str):
        """
        Reset rate limit for a specific chat.

        Useful for manual override or testing purposes.

        Args:
            chat_id: Unique identifier for the chat/group
        """
        if chat_id in self.requests:
            del self.requests[chat_id]
            logger.info(f"🔄 Rate limit reset for chat {chat_id}")


# Singleton instance with configurable defaults from settings
# This is initialized here, but can be reconfigured in main.py if needed
from src.config import settings

rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
