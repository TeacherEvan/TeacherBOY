"""Session state management for tracking active translation sessions."""

import logging
from typing import Dict, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages translation session state for chats."""

    def __init__(self):
        # Dictionary: {chat_id: {user_id, started_at, message_count}}
        self._active_sessions: Dict[str, dict] = {}
        # Set of chat IDs where translation is always on
        self._always_on_chats: Set[str] = set()

    def is_session_active(self, chat_id: str) -> bool:
        """Check if translation session is active for a chat."""
        return chat_id in self._active_sessions or chat_id in self._always_on_chats

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
            logger.info(
                f"Ended translation session for chat {chat_id}. Messages translated: {session['message_count']}"
            )
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


# Singleton instance
session_manager = SessionManager()
