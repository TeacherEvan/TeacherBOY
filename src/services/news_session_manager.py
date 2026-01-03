"""Session state management for multi-step news conversations."""

import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NewsSessionManager:
    """Manages multi-step conversation state for news agent."""

    def __init__(self, session_timeout_minutes: int = 5):
        """
        Initialize news session manager.

        Args:
            session_timeout_minutes: Minutes of inactivity before session expires (default: 5)
        """
        # Per-chat conversation state
        # Format: {chat_id: {...}}
        self._news_sessions: Dict[str, dict] = {}
        self._session_timeout_minutes = session_timeout_minutes
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval_seconds = 300  # Run cleanup every 5 minutes

    def is_in_news_flow(self, chat_id: str) -> bool:
        """
        Check if chat is in active news conversation flow.

        Args:
            chat_id: Chat identifier

        Returns:
            True if chat has active news session, False otherwise
        """
        self._cleanup_expired_sessions()
        return chat_id in self._news_sessions

    def get_session_state(self, chat_id: str) -> Optional[dict]:
        """
        Get current session state for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            Session state dict or None if no active session
        """
        self._cleanup_expired_sessions()
        return self._news_sessions.get(chat_id)

    def start_news_flow(self, chat_id: str, user_id: Optional[str] = None):
        """
        Initialize news conversation flow.

        Args:
            chat_id: Chat identifier
            user_id: LINE user ID who started the flow (for user-specific interaction)
        """
        self._news_sessions[chat_id] = {
            "step": "main_menu",  # Skip language selection, go straight to menu
            "language": None,  # Will be set by caller
            "selected_headline": None,
            "cached_data": None,
            "started_at": datetime.now(),
            "last_activity": datetime.now(),
            "user_id": user_id,  # Track who started this flow
        }
        logger.info(f"📰 Started news flow for chat {chat_id} by user {user_id}")

    def set_language(self, chat_id: str, language: str):
        """
        Set language preference and move to main menu.

        Args:
            chat_id: Chat identifier
            language: Language code ('th' or 'en')
        """
        if chat_id in self._news_sessions:
            self._news_sessions[chat_id]["language"] = language
            self._news_sessions[chat_id]["step"] = "main_menu"
            self._news_sessions[chat_id]["last_activity"] = datetime.now()
            logger.info(f"📰 Chat {chat_id} selected language: {language}")

    def set_cached_data(self, chat_id: str, data: dict):
        """
        Cache weather and news data for the session.

        Args:
            chat_id: Chat identifier
            data: Dict containing weather and news information
        """
        if chat_id in self._news_sessions:
            self._news_sessions[chat_id]["cached_data"] = data
            self._news_sessions[chat_id]["last_activity"] = datetime.now()

    def select_headline(self, chat_id: str, headline_index: int):
        """
        Select a headline for detailed view.

        Args:
            chat_id: Chat identifier
            headline_index: Index of selected headline (0-4)
        """
        if chat_id in self._news_sessions:
            self._news_sessions[chat_id]["selected_headline"] = headline_index
            self._news_sessions[chat_id]["step"] = "headline_detail"
            self._news_sessions[chat_id]["last_activity"] = datetime.now()
            logger.info(f"📰 Chat {chat_id} selected headline {headline_index}")

    def return_to_menu(self, chat_id: str):
        """
        Return to main menu from headline detail.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._news_sessions:
            self._news_sessions[chat_id]["step"] = "main_menu"
            self._news_sessions[chat_id]["selected_headline"] = None
            self._news_sessions[chat_id]["last_activity"] = datetime.now()
    def is_session_owner(self, chat_id: str, user_id: Optional[str]) -> bool:
        """
        Check if user is the owner of the news session (started it).

        Args:
            chat_id: Chat identifier
            user_id: LINE user ID to check

        Returns:
            True if user owns the session or no session exists, False otherwise
        """
        if chat_id not in self._news_sessions:
            return True  # No session, anyone can start
        
        session_user = self._news_sessions[chat_id].get("user_id")
        # Allow if no user was tracked or if it matches
        return session_user is None or session_user == user_id
    def end_news_flow(self, chat_id: str):
        """
        Exit news conversation and cleanup session.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._news_sessions:
            del self._news_sessions[chat_id]
            logger.info(f"📰 Ended news flow for chat {chat_id}")

    def _cleanup_expired_sessions(self):
        """Remove sessions that have exceeded timeout period."""
        now = datetime.now()
        timeout = timedelta(minutes=self._session_timeout_minutes)
        expired_chats = [
            chat_id
            for chat_id, session in self._news_sessions.items()
            if now - session["last_activity"] > timeout
        ]

        for chat_id in expired_chats:
            del self._news_sessions[chat_id]
            logger.info(f"📰 Session expired for chat {chat_id} (timeout)")

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired sessions."""
        logger.info(f"📰 Starting news session cleanup loop (every {self._cleanup_interval_seconds}s)")
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                self._cleanup_expired_sessions()
        except asyncio.CancelledError:
            logger.info("📰 News session cleanup loop cancelled")
            raise

    def start_cleanup(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ News session cleanup task started")
        else:
            logger.warning("⚠️  News cleanup task already running")

    def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("✅ News session cleanup task stopped")


# Global singleton instance
news_session_manager = NewsSessionManager()
