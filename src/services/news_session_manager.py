"""Session state management for multi-step news conversations."""

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

    def start_news_flow(self, chat_id: str):
        """
        Initialize news conversation flow.

        Args:
            chat_id: Chat identifier
        """
        self._news_sessions[chat_id] = {
            "step": "main_menu",  # Skip language selection, go straight to menu
            "language": None,  # Will be set by caller
            "selected_headline": None,
            "cached_data": None,
            "started_at": datetime.now(),
            "last_activity": datetime.now(),
        }
        logger.info(f"📰 Started news flow for chat {chat_id}")

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


# Global singleton instance
news_session_manager = NewsSessionManager()
