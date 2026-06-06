"""Session state management for tracking active translation sessions."""

import hashlib
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages translation session state for chats with deduplication and sleep mode."""

    def __init__(
        self,
        dedup_window_seconds: int = 60,
        max_history_size: int = 50,
        default_sleep_hours: int = 24,
        echo_window_seconds: int = 2,
    ):
        """
        Initialize session manager.

        Args:
            dedup_window_seconds: Time window for duplicate detection (default: 60s)
            max_history_size: Maximum messages to track per chat (default: 50)
            default_sleep_hours: Default sleep duration in hours (default: 24)
            echo_window_seconds: Time window for cross-language echo suppression (default: 2s)
        """
        # Dictionary: {chat_id: {user_id, started_at, message_count}}
        self._active_sessions: dict[str, dict] = {}
        # Set of chat IDs where translation is always on
        self._always_on_chats: set[str] = set()
        # Message deduplication: {chat_id: [(message_hash, timestamp), ...]}
        self._message_history: dict[str, list[tuple[str, datetime]]] = {}
        # Sleep mode: {chat_id: wake_at_datetime}
        self._sleeping_chats: dict[str, datetime] = {}
        # Recent language messages for echo suppression: {chat_id: (language, timestamp)}
        self._recent_language_messages: dict[str, tuple[str, datetime]] = {}
        # Configuration
        self._max_history_size = max_history_size
        self._dedup_window_seconds = dedup_window_seconds
        self._default_sleep_hours = default_sleep_hours
        self._echo_window_seconds = echo_window_seconds

    def is_session_active(self, chat_id: str) -> bool:
        """Check if translation session is active for a chat (not sleeping)."""
        # Check if chat is sleeping
        if self.is_sleeping(chat_id):
            return False
        return chat_id in self._active_sessions or chat_id in self._always_on_chats

    def is_sleeping(self, chat_id: str) -> bool:
        """
        Check if chat is in sleep mode.

        Args:
            chat_id: Chat identifier

        Returns:
            True if chat is sleeping, False otherwise
        """
        if chat_id not in self._sleeping_chats:
            return False

        wake_at = self._sleeping_chats[chat_id]
        if datetime.now() >= wake_at:
            # Sleep period has expired, auto-wake
            del self._sleeping_chats[chat_id]
            logger.info(f"😴 Chat {chat_id} auto-woke (sleep period expired)")
            return False
        return True

    def get_sleep_remaining(self, chat_id: str) -> int:
        """
        Get remaining sleep time in hours.

        Args:
            chat_id: Chat identifier

        Returns:
            Hours remaining until wake, or 0 if not sleeping
        """
        if chat_id not in self._sleeping_chats:
            return 0

        wake_at = self._sleeping_chats[chat_id]
        remaining = wake_at - datetime.now()
        if remaining.total_seconds() <= 0:
            return 0
        return int(remaining.total_seconds() / 3600) + 1  # Round up

    def sleep_chat(self, chat_id: str, hours: int = None):
        """
        Put a chat to sleep for specified hours.

        Args:
            chat_id: Chat identifier
            hours: Sleep duration in hours (default: 24)
        """
        if hours is None:
            hours = self._default_sleep_hours

        wake_at = datetime.now() + timedelta(hours=hours)
        self._sleeping_chats[chat_id] = wake_at

        # Also end any active session
        if chat_id in self._active_sessions:
            self._active_sessions.pop(chat_id)

        logger.info(f"😴 Chat {chat_id} put to sleep for {hours} hours (wake at {wake_at})")

    def wake_chat(self, chat_id: str) -> bool:
        """
        Wake a sleeping chat.

        Args:
            chat_id: Chat identifier

        Returns:
            True if chat was sleeping and is now awake, False otherwise
        """
        if chat_id in self._sleeping_chats:
            del self._sleeping_chats[chat_id]
            logger.info(f"☀️ Chat {chat_id} manually woken up")
            return True
        return False

    def start_session(self, chat_id: str, user_id: str):
        """Start a new translation session for a chat."""
        self._active_sessions[chat_id] = {
            "user_id": user_id,
            "started_at": datetime.now(),
            "message_count": 0,
        }
        logger.info(f"Started translation session for chat {chat_id} by user {user_id}")

    def end_session(self, chat_id: str) -> bool:
        """End translation session for a chat. Returns True if session existed."""
        if chat_id in self._active_sessions:
            session = self._active_sessions.pop(chat_id)
            logger.info(f"Ended translation session for chat {chat_id}. Messages translated: {session['message_count']}")
            return True
        return False

    def increment_message_count(self, chat_id: str):
        """Increment message counter for a session."""
        if chat_id in self._active_sessions:
            self._active_sessions[chat_id]["message_count"] += 1

    def get_session_info(self, chat_id: str) -> dict:
        """Get session information for a chat."""
        return self._active_sessions.get(chat_id, {})

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove sessions older than max_age_hours."""
        now = datetime.now()
        to_remove = []

        for chat_id, session in self._active_sessions.items():
            age = now - session["started_at"]
            if age > timedelta(hours=max_age_hours):
                to_remove.append(chat_id)

        for chat_id in to_remove:
            self.end_session(chat_id)
            logger.info(f"Cleaned up old session for chat {chat_id}")

    def set_always_on(self, chat_id: str):
        """Set a chat to always translate (no need for trigger)."""
        self._always_on_chats.add(chat_id)
        logger.info(f"Set chat {chat_id} to always-on translation mode")

    def remove_always_on(self, chat_id: str):
        """Remove always-on status from a chat."""
        self._always_on_chats.discard(chat_id)
        logger.info(f"Removed always-on status from chat {chat_id}")

    def _hash_message(self, text: str) -> str:
        """
        Create a hash of message text for deduplication.

        Args:
            text: Message text to hash

        Returns:
            SHA256 hash of the message (first 16 chars for efficiency)
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def is_duplicate_message(self, chat_id: str, text: str) -> bool:
        """
        Check if message is a duplicate (same content within dedup window).

        Args:
            chat_id: Chat identifier
            text: Message text to check

        Returns:
            True if message is a duplicate, False otherwise
        """
        now = datetime.now()
        message_hash = self._hash_message(text)

        # Initialize history for new chats
        if chat_id not in self._message_history:
            self._message_history[chat_id] = []

        # Clean up old messages outside dedup window
        cutoff_time = now - timedelta(seconds=self._dedup_window_seconds)
        self._message_history[chat_id] = [
            (hash_val, ts) for hash_val, ts in self._message_history[chat_id] if ts > cutoff_time
        ]

        # Check for duplicate
        for hash_val, timestamp in self._message_history[chat_id]:
            if hash_val == message_hash:
                age_seconds = (now - timestamp).total_seconds()
                logger.warning(f"🔁 Duplicate message detected in chat {chat_id} (last seen {age_seconds:.1f}s ago)")
                return True

        # Not a duplicate - record this message
        self._message_history[chat_id].append((message_hash, now))

        # Trim history to max size (keep most recent)
        if len(self._message_history[chat_id]) > self._max_history_size:
            self._message_history[chat_id] = self._message_history[chat_id][-self._max_history_size :]

        return False

    def clear_message_history(self, chat_id: str):
        """
        Clear message history for a chat.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._message_history:
            del self._message_history[chat_id]
            logger.info(f"🧹 Cleared message history for chat {chat_id}")

    def get_active_sessions(self) -> dict:
        """
        Get all active translation sessions.

        Returns:
            Dictionary of active sessions {chat_id: session_info}
        """
        return self._active_sessions.copy()

    def get_sleeping_chats(self) -> dict:
        """
        Get all sleeping chats.

        Returns:
            Dictionary of sleeping chats {chat_id: wake_at_datetime}
        """
        return self._sleeping_chats.copy()

    def _detect_message_language(self, text: str) -> str:
        # Simple heuristic: detect Thai characters vs others
        return "th" if bool(re.search(r"[\u0E00-\u0E7F]", text)) else "en"

    def should_ignore_cross_language_echo(
        self,
        chat_id: str,
        text: str,
        *,
        now: datetime | None = None,
        now_offset_seconds: int | None = None,
    ) -> bool:
        """Return True if the message should be ignored as a cross-language echo.

        If a message in a different language than the previous message in the same chat
        arrives within the echo window, treat it as an echo and ignore it.
        """
        current_time = now or datetime.now()
        if now_offset_seconds is not None:
            current_time = datetime.now() + timedelta(seconds=now_offset_seconds)

        language = self._detect_message_language(text)
        previous = self._recent_language_messages.get(chat_id)
        # Record current message language and time
        self._recent_language_messages[chat_id] = (language, current_time)

        if previous is None:
            return False

        previous_language, previous_time = previous
        age_seconds = (current_time - previous_time).total_seconds()
        return previous_language != language and age_seconds < self._echo_window_seconds


# Singleton instance
session_manager = SessionManager()
