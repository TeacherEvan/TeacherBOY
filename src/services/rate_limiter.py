"""Rate limiting service to prevent API quota exhaustion."""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for translation requests with chat-based and user-based limits.

    Prevents API quota exhaustion by limiting the number of translations
    per chat within a time window, with additional user-based limits for
    authenticated users in the secrets access group.
    """

    def __init__(self, max_requests: int = 10, time_window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window (chat-based)
            time_window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = timedelta(seconds=time_window_seconds)

        # Chat-based rate limiting (existing)
        # Dictionary: {chat_id: [timestamp1, timestamp2, ...]}
        self._request_history: Dict[str, List[datetime]] = defaultdict(list)

        # User-based rate limiting for authenticated users
        # Dictionary: {user_id: {"daily": [timestamps], "burst": [timestamps]}}
        self._user_limits: Dict[str, Dict[str, List[datetime]]] = defaultdict(
            lambda: {"daily": [], "burst": []}
        )

        # User-based limits configuration
        self.daily_limit = 3  # 3 interactions per day
        self.daily_window = timedelta(days=1)
        self.burst_limit = 1  # 1 interaction per 60 seconds
        self.burst_window = timedelta(seconds=60)

        logger.info(
            f"✅ Rate limiter initialized: {max_requests} requests per {time_window_seconds}s (chat-based), "
            f"{self.daily_limit} daily/{self.burst_limit} per {self.burst_window.seconds}s (user-based)"
        )

    def is_allowed(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        """
        Check if a request is allowed for the given chat and user.

        Args:
            chat_id: Chat identifier
            user_id: User identifier (optional, for user-based limits)

        Returns:
            True if request is allowed, False if rate limited
        """
        now = datetime.now()

        # Always check chat-based limits first
        if not self._is_chat_allowed(chat_id, now):
            return False

        # Check user-based limits if user_id provided and in secrets access group
        if user_id and self._is_user_in_secrets_group(user_id):
            if not self._is_user_allowed(user_id, now):
                return False

        return True

    def _is_chat_allowed(self, chat_id: str, now: datetime) -> bool:
        """Check chat-based rate limits."""
        # Clean up old timestamps outside the time window
        cutoff_time = now - self.time_window
        self._request_history[chat_id] = [
            ts for ts in self._request_history[chat_id] if ts > cutoff_time
        ]

        # Check if under the limit
        request_count = len(self._request_history[chat_id])

        if request_count >= self.max_requests:
            logger.warning(
                f"⚠️  Chat rate limit exceeded for {chat_id}: "
                f"{request_count}/{self.max_requests} requests in time window"
            )
            return False

        # Record this request
        self._request_history[chat_id].append(now)
        logger.debug(
            f"✅ Chat rate limit check passed for {chat_id}: {request_count + 1}/{self.max_requests}"
        )
        return True

    def _is_user_in_secrets_group(self, user_id: str) -> bool:
        """Check if user is in the secrets access group (USER_NAME env var)."""
        import os
        user_name = os.getenv("USER_NAME")
        return user_name is not None and user_id == user_name

    def _is_user_allowed(self, user_id: str, now: datetime) -> bool:
        """Check user-based rate limits for authenticated users."""
        user_data = self._user_limits[user_id]

        # Check daily limit
        daily_cutoff = now - self.daily_window
        user_data["daily"] = [ts for ts in user_data["daily"] if ts > daily_cutoff]

        if len(user_data["daily"]) >= self.daily_limit:
            logger.warning(
                f"⚠️  User daily limit exceeded for {user_id}: "
                f"{len(user_data['daily'])}/{self.daily_limit} interactions today"
            )
            return False

        # Check burst limit
        burst_cutoff = now - self.burst_window
        user_data["burst"] = [ts for ts in user_data["burst"] if ts > burst_cutoff]

        if len(user_data["burst"]) >= self.burst_limit:
            logger.warning(
                f"⚠️  User burst limit exceeded for {user_id}: "
                f"{len(user_data['burst'])}/{self.burst_limit} interactions in {self.burst_window.seconds}s"
            )
            return False

        # Record this request for both limits
        user_data["daily"].append(now)
        user_data["burst"].append(now)

        logger.debug(
            f"✅ User rate limit check passed for {user_id}: "
            f"daily {len(user_data['daily'])}/{self.daily_limit}, "
            f"burst {len(user_data['burst'])}/{self.burst_limit}"
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

    def get_reset_time(self, chat_id: str, user_id: Optional[str] = None) -> int:
        """
        Get seconds until rate limit resets for a chat or user.

        Args:
            chat_id: Chat identifier
            user_id: User identifier (optional, for user-based limits)

        Returns:
            Seconds until oldest request expires (0 if not rate limited)
        """
        now = datetime.now()

        # Check user limits first if applicable
        if user_id and self._is_user_in_secrets_group(user_id):
            user_reset = self._get_user_reset_time(user_id, now)
            if user_reset > 0:
                return user_reset

        # Fall back to chat limits
        if not self._request_history[chat_id]:
            return 0

        oldest_request = min(self._request_history[chat_id])
        reset_time = oldest_request + self.time_window

        if reset_time > now:
            return int((reset_time - now).total_seconds())
        return 0

    def _get_user_reset_time(self, user_id: str, now: datetime) -> int:
        """Get reset time for user-based limits."""
        user_data = self._user_limits[user_id]

        # Check burst limit reset time
        if user_data["burst"]:
            oldest_burst = min(user_data["burst"])
            burst_reset = oldest_burst + self.burst_window
            if burst_reset > now:
                return int((burst_reset - now).total_seconds())

        # Check daily limit reset time
        if user_data["daily"]:
            oldest_daily = min(user_data["daily"])
            daily_reset = oldest_daily + self.daily_window
            if daily_reset > now:
                return int((daily_reset - now).total_seconds())

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
        """Remove entries for chats and users with no recent activity."""
        now = datetime.now()
        chat_cutoff = now - self.time_window
        daily_cutoff = now - self.daily_window
        burst_cutoff = now - self.burst_window

        # Clean up chat-based entries
        chats_to_remove = []
        for chat_id, timestamps in self._request_history.items():
            valid_timestamps = [ts for ts in timestamps if ts > chat_cutoff]
            if not valid_timestamps:
                chats_to_remove.append(chat_id)
            else:
                self._request_history[chat_id] = valid_timestamps

        for chat_id in chats_to_remove:
            del self._request_history[chat_id]

        # Clean up user-based entries
        users_to_remove = []
        for user_id, user_data in self._user_limits.items():
            # Clean daily timestamps
            user_data["daily"] = [ts for ts in user_data["daily"] if ts > daily_cutoff]
            # Clean burst timestamps
            user_data["burst"] = [ts for ts in user_data["burst"] if ts > burst_cutoff]

            # Remove user if no active timestamps
            if not user_data["daily"] and not user_data["burst"]:
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            del self._user_limits[user_id]

        total_cleaned = len(chats_to_remove) + len(users_to_remove)
        if total_cleaned > 0:
            logger.debug(f"🧹 Cleaned up {len(chats_to_remove)} inactive chat(s) and {len(users_to_remove)} inactive user(s)")


# Singleton instance
rate_limiter = RateLimiter(max_requests=10, time_window_seconds=60)
