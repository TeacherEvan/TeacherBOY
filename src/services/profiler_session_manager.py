"""Profiler session manager - tracks profiling requests."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ProfilerSessionManager:
    """Manages profiler sessions to track when users request image analysis."""

    def __init__(self):
        """Initialize profiler session manager."""
        # {chat_id: (user_id, timestamp)}
        self._waiting_for_image: Dict[str, tuple[str, datetime]] = {}
        self._session_ttl_seconds = 60  # Expire after 60 seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval_seconds = 60  # Run cleanup every 60 seconds

    def request_profiling(self, chat_id: str, user_id: Optional[str] = None) -> None:
        """
        Mark that user is waiting to send an image for profiling.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier
        """
        self._waiting_for_image[chat_id] = (user_id or "unknown", datetime.now())
        logger.info(f"🔬 Profiling requested for chat {chat_id}")

    def is_waiting_for_image(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        """
        Check if this chat is waiting for an image to profile.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match if provided)

        Returns:
            True if waiting for image and session not expired
        """
        if chat_id not in self._waiting_for_image:
            return False

        stored_user_id, timestamp = self._waiting_for_image[chat_id]

        # Check expiration
        age = (datetime.now() - timestamp).total_seconds()
        if age > self._session_ttl_seconds:
            logger.info(f"🔬 Profiling session expired for chat {chat_id}")
            del self._waiting_for_image[chat_id]
            return False

        # Check user match (in groups, ensure same user sent trigger and image)
        if user_id and stored_user_id != "unknown" and user_id != stored_user_id:
            logger.debug(
                f"🔬 User mismatch: trigger from {stored_user_id}, "
                f"image from {user_id}"
            )
            return False

        return True

    def clear_session(self, chat_id: str) -> None:
        """
        Clear profiling session for a chat.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._waiting_for_image:
            del self._waiting_for_image[chat_id]
            logger.info(f"🔬 Cleared profiling session for chat {chat_id}")

    def cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = datetime.now()
        expired = [
            chat_id
            for chat_id, (_, timestamp) in self._waiting_for_image.items()
            if (now - timestamp).total_seconds() > self._session_ttl_seconds
        ]

        for chat_id in expired:
            del self._waiting_for_image[chat_id]

        if expired:
            logger.info(f"🔬 Cleaned up {len(expired)} expired profiling sessions")

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired sessions."""
        logger.info(f"🔬 Starting profiler session cleanup loop (every {self._cleanup_interval_seconds}s)")
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                self.cleanup_expired()
        except asyncio.CancelledError:
            logger.info("🔬 Profiler session cleanup loop cancelled")
            raise

    def start_cleanup(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ Profiler session cleanup task started")
        else:
            logger.warning("⚠️  Profiler cleanup task already running")

    def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("✅ Profiler session cleanup task stopped")


# Singleton instance
profiler_session_manager = ProfilerSessionManager()
