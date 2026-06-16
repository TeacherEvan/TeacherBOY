"""Rate limiting service to prevent API quota exhaustion."""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

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
        self._request_history: dict[str, list[datetime]] = defaultdict(list)

        # Calendar operation rate limiting
        # Dictionary: {user_id: [timestamps]}
        self._calendar_user_limits: dict[str, list[datetime]] = defaultdict(list)
        # Dictionary: {chat_id: [timestamps]}
        self._calendar_chat_limits: dict[str, list[datetime]] = defaultdict(list)

        # Calendar limits configuration
        self.calendar_user_limit = 10  # 10 operations per minute per user
        self.calendar_user_window = timedelta(minutes=1)
        self.calendar_chat_limit = 30  # 30 operations per minute per chat
        self.calendar_chat_window = timedelta(minutes=1)

        # Destructive admin request limiting - 3 per minute per admin
        self._admin_destructive_history: dict[str, list[datetime]] = defaultdict(list)
        self._admin_destructive_targets: dict[str, dict[str, datetime | str]] = {}
        self._admin_destructive_lock = Lock()
        self.admin_destructive_limit = 3  # 3 destructive requests per minute per admin
        self.admin_destructive_window = timedelta(minutes=1)

        # General admin rate limiting - 10 requests per minute per admin
        self._admin_general_history: dict[str, list[datetime]] = defaultdict(list)
        self.admin_general_limit = 10  # 10 admin requests per minute per admin
        self.admin_general_window = timedelta(minutes=1)

        # User-based rate limiting for authenticated users
        # Dictionary: {user_id: {"daily": [timestamps], "burst": [timestamps]}}
        self._user_limits: dict[str, dict[str, list[datetime]]] = defaultdict(lambda: {"daily": [], "burst": []})

        # User-based limits configuration
        self.daily_limit = 3  # 3 interactions per day
        self.daily_window = timedelta(days=1)
        self.burst_limit = 1  # 1 interaction per 60 seconds
        self.burst_window = timedelta(seconds=60)

        # Cleanup task
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval_seconds = 604800  # Run cleanup every 7 days (weekly)

        logger.info(
            f"✅ Rate limiter initialized: {max_requests} requests per {time_window_seconds}s (chat-based), "
            f"{self.daily_limit} daily/{self.burst_limit} per {self.burst_window.seconds}s (user-based)"
        )

    def _admin_now(self) -> datetime:
        # Use utcnow() for test compatibility - tests mock datetime.utcnow()
        # datetime.utcnow() is deprecated in Python 3.12 but needed here for test mocking
        return datetime.utcnow()  # noqa: DTZ003

    def is_allowed(self, chat_id: str, user_id: str | None = None) -> bool:
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
        self._request_history[chat_id] = [ts for ts in self._request_history[chat_id] if ts > cutoff_time]

        # Check if under the limit
        request_count = len(self._request_history[chat_id])

        if request_count >= self.max_requests:
            logger.warning(
                f"⚠️  Chat rate limit exceeded for {chat_id}: {request_count}/{self.max_requests} requests in time window"
            )
            return False

        # Record this request
        self._request_history[chat_id].append(now)
        logger.debug(f"✅ Chat rate limit check passed for {chat_id}: {request_count + 1}/{self.max_requests}")
        return True

    def _is_user_in_secrets_group(self, user_id: str) -> bool:
        return False

    def _is_user_allowed(self, user_id: str, now: datetime) -> bool:
        """Check user-based rate limits for authenticated users."""
        user_data = self._user_limits[user_id]

        # Check daily limit
        daily_cutoff = now - self.daily_window
        user_data["daily"] = [ts for ts in user_data["daily"] if ts > daily_cutoff]

        if len(user_data["daily"]) >= self.daily_limit:
            logger.warning(
                f"⚠️  User daily limit exceeded for {user_id}: {len(user_data['daily'])}/{self.daily_limit} interactions today"
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
        self._request_history[chat_id] = [ts for ts in self._request_history[chat_id] if ts > cutoff_time]

        return max(0, self.max_requests - len(self._request_history[chat_id]))

    def get_reset_time(self, chat_id: str, user_id: str | None = None) -> int:
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

    def check_admin_limit(self, user_id: str, destructive: bool = False) -> tuple[bool, int | None]:
        """Check if an admin request is allowed.

        Args:
            user_id: Admin user identifier
            destructive: Whether this is a destructive admin command

        Returns:
            Tuple of (allowed, retry_after_seconds)
            - allowed: True if request is allowed, False if rate limited
            - retry_after_seconds: Seconds until limit resets (None if allowed)
        """
        now = self._admin_now()

        if destructive:
            # Check destructive limit (3 per minute)
            cutoff = now - self.admin_destructive_window
            self._admin_destructive_history[user_id] = [
                ts for ts in self._admin_destructive_history[user_id] if ts > cutoff
            ]
            count = len(self._admin_destructive_history[user_id])
            if count >= self.admin_destructive_limit:
                oldest = min(self._admin_destructive_history[user_id]) if self._admin_destructive_history[user_id] else now
                retry_after = int((oldest + self.admin_destructive_window - now).total_seconds())
                return False, max(1, retry_after)

            # Also check general admin limit (destructive counts towards general too)
        else:
            # Check general admin limit (10 per minute for non-destructive)
            cutoff = now - self.admin_general_window
            self._admin_general_history[user_id] = [
                ts for ts in self._admin_general_history[user_id] if ts > cutoff
            ]
            count = len(self._admin_general_history[user_id])
            if count >= self.admin_general_limit:
                oldest = min(self._admin_general_history[user_id]) if self._admin_general_history[user_id] else now
                retry_after = int((oldest + self.admin_general_window - now).total_seconds())
                return False, max(1, retry_after)

        return True, None

    def record_admin_request(self, user_id: str, destructive: bool = False) -> None:
        """Record an admin request for rate limiting.

        Args:
            user_id: Admin user identifier
            destructive: Whether this is a destructive admin command
        """
        now = self._admin_now()
        if destructive:
            self._admin_destructive_history[user_id].append(now)
        self._admin_general_history[user_id].append(now)

    def get_admin_reset_time(self, user_id: str, destructive: bool = False) -> int:
        """Get seconds until admin rate limit resets.

        Args:
            user_id: Admin user identifier
            destructive: Whether checking destructive limit

        Returns:
            Seconds until limit resets (0 if not rate limited)
        """
        now = self._admin_now()
        if destructive:
            history = self._admin_destructive_history[user_id]
            window = self.admin_destructive_window
        else:
            history = self._admin_general_history[user_id]
            window = self.admin_general_window

        if not history:
            return 0

        cutoff = now - window
        valid = [ts for ts in history if ts > cutoff]
        if not valid:
            return 0

        oldest = min(valid)
        reset_time = oldest + window
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

        # Clean up calendar limits
        calendar_users_to_remove = []
        for user_id, timestamps in self._calendar_user_limits.items():
            valid = [ts for ts in timestamps if ts > now - self.calendar_user_window]
            if not valid:
                calendar_users_to_remove.append(user_id)
            else:
                self._calendar_user_limits[user_id] = valid

        for user_id in calendar_users_to_remove:
            del self._calendar_user_limits[user_id]

        calendar_chats_to_remove = []
        for chat_id, timestamps in self._calendar_chat_limits.items():
            valid = [ts for ts in timestamps if ts > now - self.calendar_chat_window]
            if not valid:
                calendar_chats_to_remove.append(chat_id)
            else:
                self._calendar_chat_limits[chat_id] = valid

        for chat_id in calendar_chats_to_remove:
            del self._calendar_chat_limits[chat_id]

        with self._admin_destructive_lock:
            self._cleanup_admin_destructive_limits(self._admin_now())

            # Clean up admin rate limit entries
            admin_general_cutoff = now - self.admin_general_window
            admin_destructive_cutoff = now - self.admin_destructive_window

            admin_general_users_to_remove = []
            for user_id, timestamps in self._admin_general_history.items():
                valid = [ts for ts in timestamps if ts > admin_general_cutoff]
                if not valid:
                    admin_general_users_to_remove.append(user_id)
                else:
                    self._admin_general_history[user_id] = valid

            for user_id in admin_general_users_to_remove:
                del self._admin_general_history[user_id]

            admin_destructive_users_to_remove = []
            for user_id, timestamps in self._admin_destructive_history.items():
                valid = [ts for ts in timestamps if ts > admin_destructive_cutoff]
                if not valid:
                    admin_destructive_users_to_remove.append(user_id)
                else:
                    self._admin_destructive_history[user_id] = valid

            for user_id in admin_destructive_users_to_remove:
                del self._admin_destructive_history[user_id]

        total_cleaned = (
            len(chats_to_remove) + len(users_to_remove) + len(calendar_users_to_remove) + len(calendar_chats_to_remove)
            + len(admin_general_users_to_remove) + len(admin_destructive_users_to_remove)
        )
        if total_cleaned > 0:
            logger.debug(
                f"🧹 Cleaned up {len(chats_to_remove)} inactive chat(s), "
                f"{len(users_to_remove)} inactive user(s), "
                f"{len(calendar_users_to_remove)} calendar user(s), "
                f"{len(calendar_chats_to_remove)} calendar chat(s)"
            )

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up stale rate limit entries."""
        logger.info(f"⏱️ Starting rate limiter cleanup loop (every {self._cleanup_interval_seconds}s)")
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                self.cleanup_old_entries()
        except asyncio.CancelledError:
            logger.info("⏱️ Rate limiter cleanup loop cancelled")
            raise

    def start_cleanup(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ Rate limiter cleanup task started")
        else:
            logger.warning("⚠️  Rate limiter cleanup task already running")

    async def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except TimeoutError:
                logger.warning("⚠️ Rate limiter cleanup task shutdown timed out")
            except asyncio.CancelledError:
                pass
            logger.info("✅ Rate limiter cleanup task stopped")

    def is_calendar_operation_allowed(self, user_id: str, chat_id: str, is_admin: bool = False) -> bool:
        """
        Check if a calendar operation is allowed.

        Args:
            user_id: User identifier
            chat_id: Chat identifier
            is_admin: Whether user is an admin (bypasses limits)

        Returns:
            True if operation is allowed, False if rate limited
        """
        # Admins bypass rate limits
        if is_admin:
            return True

        now = datetime.now()

        # Check user limit
        user_cutoff = now - self.calendar_user_window
        self._calendar_user_limits[user_id] = [ts for ts in self._calendar_user_limits[user_id] if ts > user_cutoff]

        if len(self._calendar_user_limits[user_id]) >= self.calendar_user_limit:
            logger.warning(
                f"⚠️ Calendar rate limit exceeded for user {user_id}: "
                f"{len(self._calendar_user_limits[user_id])}/{self.calendar_user_limit} operations"
            )
            return False

        # Check chat limit
        chat_cutoff = now - self.calendar_chat_window
        self._calendar_chat_limits[chat_id] = [ts for ts in self._calendar_chat_limits[chat_id] if ts > chat_cutoff]

        if len(self._calendar_chat_limits[chat_id]) >= self.calendar_chat_limit:
            logger.warning(
                f"⚠️ Calendar rate limit exceeded for chat {chat_id}: "
                f"{len(self._calendar_chat_limits[chat_id])}/{self.calendar_chat_limit} operations"
            )
            return False

        # Record this operation
        self._calendar_user_limits[user_id].append(now)
        self._calendar_chat_limits[chat_id].append(now)

        return True

    def _cleanup_admin_destructive_limits(
        self,
        now: datetime | None = None,
    ) -> None:
        current_time = now or self._admin_now()
        user_cutoff = current_time - self.admin_destructive_window

        users_to_remove = []
        for user_id, timestamps in self._admin_destructive_history.items():
            valid = [ts for ts in timestamps if ts > user_cutoff]
            if valid:
                self._admin_destructive_history[user_id] = valid
            else:
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            del self._admin_destructive_history[user_id]

        targets_to_remove = []
        for target_chat_id, reservation in self._admin_destructive_targets.items():
            expires_at = reservation.get("expires_at")
            if isinstance(expires_at, datetime):
                # Ensure both datetimes are timezone-aware for comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                # Compare using UTC for consistency with tests
                current_utc = datetime.utcnow().replace(tzinfo=UTC)  # noqa: DTZ003
                if expires_at <= current_utc:
                    targets_to_remove.append(target_chat_id)

        for target_chat_id in targets_to_remove:
            self._admin_destructive_targets.pop(target_chat_id, None)

    def reserve_admin_destructive_request(
        self,
        *,
        user_id: str,
        target_chat_id: str,
        token: str,
        expires_at: datetime,
    ) -> tuple[bool, str | None]:
        now = self._admin_now()
        with self._admin_destructive_lock:
            self._cleanup_admin_destructive_limits(now)

            user_requests = self._admin_destructive_history[user_id]
            if len(user_requests) >= self.admin_destructive_limit:
                logger.warning(
                    "⚠️ Destructive admin rate limit exceeded for %s: %s/%s",
                    user_id,
                    len(user_requests),
                    self.admin_destructive_limit,
                )
                return (
                    False,
                    "⚠️ Too many destructive admin requests. Please wait a few minutes and try again.",
                )

            if target_chat_id in self._admin_destructive_targets:
                logger.warning(
                    "⚠️ Destructive admin target already reserved for %s",
                    target_chat_id,
                )
                return (
                    False,
                    "⚠️ A destructive admin action is already pending for this chat.",
                )

            user_requests.append(now)
            self._admin_destructive_targets[target_chat_id] = {
                "token": token,
                "expires_at": expires_at,
                "user_id": user_id,
                "reserved_at": now,
            }
            return True, None

    def _rollback_admin_destructive_history(
        self,
        reservation: dict[str, datetime | str] | None,
    ) -> None:
        if reservation is None:
            return

        user_id = reservation.get("user_id")
        reserved_at = reservation.get("reserved_at")
        if not isinstance(user_id, str) or not isinstance(reserved_at, datetime):
            return

        user_requests = self._admin_destructive_history.get(user_id)
        if not user_requests:
            return

        for index, timestamp in enumerate(user_requests):
            if timestamp == reserved_at:
                user_requests.pop(index)
                break

        if not user_requests:
            self._admin_destructive_history.pop(user_id, None)

    def release_admin_destructive_request(
        self,
        *,
        token: str | None = None,
        target_chat_id: str | None = None,
        rollback_history: bool = False,
    ) -> None:
        with self._admin_destructive_lock:
            self._cleanup_admin_destructive_limits(self._admin_now())

            if target_chat_id:
                reservation = self._admin_destructive_targets.get(target_chat_id)
                if reservation is None:
                    return
                if token is None or reservation.get("token") == token:
                    removed = self._admin_destructive_targets.pop(target_chat_id, None)
                    if rollback_history:
                        self._rollback_admin_destructive_history(removed)
                return

            if not token:
                return

            for reserved_target, reservation in list(self._admin_destructive_targets.items()):
                if reservation.get("token") == token:
                    removed = self._admin_destructive_targets.pop(reserved_target, None)
                    if rollback_history:
                        self._rollback_admin_destructive_history(removed)
                    break

    def reset_admin_destructive_limits_for_testing(self) -> None:
        with self._admin_destructive_lock:
            self._admin_destructive_history.clear()
            self._admin_destructive_targets.clear()


# Singleton instance
rate_limiter = RateLimiter(max_requests=10, time_window_seconds=60)
