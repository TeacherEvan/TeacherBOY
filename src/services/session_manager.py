"""Session state management for tracking active translation sessions."""

import logging
import hashlib
from typing import Dict, Set, List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages translation session state for chats with deduplication."""

    def __init__(self, dedup_window_seconds: int = 60, max_history_size: int = 50):
        """
        Initialize session manager.
        
        Args:
            dedup_window_seconds: Time window for duplicate detection (default: 60s)
            max_history_size: Maximum messages to track per chat (default: 50)
        """
        # Dictionary: {chat_id: {user_id, started_at, message_count}}
        self._active_sessions: Dict[str, dict] = {}
        # Set of chat IDs where translation is always on
        self._always_on_chats: Set[str] = set()
        # Message deduplication: {chat_id: [(message_hash, timestamp), ...]}
        self._message_history: Dict[str, List[Tuple[str, datetime]]] = {}
        # Configuration
        self._max_history_size = max_history_size
        self._dedup_window_seconds = dedup_window_seconds

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

    def _hash_message(self, text: str) -> str:
        """
        Create a hash of message text for deduplication.
        
        Args:
            text: Message text to hash
            
        Returns:
            SHA256 hash of the message (first 16 chars for efficiency)
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

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
            (hash_val, ts) 
            for hash_val, ts in self._message_history[chat_id] 
            if ts > cutoff_time
        ]
        
        # Check for duplicate
        for hash_val, timestamp in self._message_history[chat_id]:
            if hash_val == message_hash:
                age_seconds = (now - timestamp).total_seconds()
                logger.warning(
                    f"🔁 Duplicate message detected in chat {chat_id} "
                    f"(last seen {age_seconds:.1f}s ago)"
                )
                return True
        
        # Not a duplicate - record this message
        self._message_history[chat_id].append((message_hash, now))
        
        # Trim history to max size (keep most recent)
        if len(self._message_history[chat_id]) > self._max_history_size:
            self._message_history[chat_id] = self._message_history[chat_id][-self._max_history_size:]
        
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


# Singleton instance
session_manager = SessionManager()
