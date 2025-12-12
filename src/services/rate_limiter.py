"""Rate limiting service to prevent API quota exhaustion."""

import logging
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for translation requests.

    Prevents API quota exhaustion by limiting the number of translations
    per chat within a time window.
    """

    def __init__(self, max_requests: int = 10, time_window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window
            time_window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = timedelta(seconds=time_window_seconds)
        # Dictionary: {chat_id: [timestamp1, timestamp2, ...]}
        self._request_history: Dict[str, List[datetime]] = defaultdict(list)
        logger.info(
            f"✅ Rate limiter initialized: {max_requests} requests per {time_window_seconds}s"
        )

    def is_allowed(self, chat_id: str) -> bool:
        """
        Check if a request is allowed for the given chat.

        Args:
            chat_id: Chat identifier

        Returns:
            True if request is allowed, False if rate limited
        """
        now = datetime.now()

        # Clean up old timestamps outside the time window
        cutoff_time = now - self.time_window
        self._request_history[chat_id] = [
            ts for ts in self._request_history[chat_id] if ts > cutoff_time
        ]

        # Check if under the limit
        request_count = len(self._request_history[chat_id])

        if request_count >= self.max_requests:
            logger.warning(
                f"⚠️  Rate limit exceeded for chat {chat_id}: "
                f"{request_count}/{self.max_requests} requests in time window"
            )
            return False

        # Record this request
        self._request_history[chat_id].append(now)
        logger.debug(
            f"✅ Rate limit check passed for chat {chat_id}: {request_count + 1}/{self.max_requests}"
        )
        return True

    def get_remaining_requests(self, chat_id: str) -> int:
        """
        Get number of remaining requests for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            Number of remaining requests in current window
        """
        now = datetime.now()
        cutoff_time = now - self.time_window

        # Clean up old timestamps
        self._request_history[chat_id] = [
            ts for ts in self._request_history[chat_id] if ts > cutoff_time
        ]

        return max(0, self.max_requests - len(self._request_history[chat_id]))

    def get_reset_time(self, chat_id: str) -> int:
        """
        Get seconds until rate limit resets for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            Seconds until oldest request expires (0 if not rate limited)
        """
        if not self._request_history[chat_id]:
            return 0

        oldest_request = min(self._request_history[chat_id])
        reset_time = oldest_request + self.time_window
        now = datetime.now()

        if reset_time > now:
            return int((reset_time - now).total_seconds())
        return 0

    def reset_chat(self, chat_id: str):
        """
        Reset rate limit for a specific chat.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._request_history:
            del self._request_history[chat_id]
            logger.info(f"🔄 Rate limit reset for chat {chat_id}")

    def cleanup_old_entries(self):
        """Remove entries for chats with no recent activity."""
        now = datetime.now()
        cutoff_time = now - self.time_window

        chats_to_remove = []
        for chat_id, timestamps in self._request_history.items():
            # Remove old timestamps
            valid_timestamps = [ts for ts in timestamps if ts > cutoff_time]

            if not valid_timestamps:
                chats_to_remove.append(chat_id)
            else:
                self._request_history[chat_id] = valid_timestamps

        # Clean up empty chats
        for chat_id in chats_to_remove:
            del self._request_history[chat_id]

        if chats_to_remove:
            logger.debug(f"🧹 Cleaned up {len(chats_to_remove)} inactive chat(s)")


# Singleton instance
rate_limiter = RateLimiter(max_requests=10, time_window_seconds=60)
