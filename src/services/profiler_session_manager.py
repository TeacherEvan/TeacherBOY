"""Profiler session manager - tracks profiling requests."""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProfilerSessionManager:
    """Manages profiler sessions to track when users request image analysis."""

    def __init__(self):
        """Initialize profiler session manager."""
        # {chat_id: (user_id, timestamp, analysis_mode)}
        self._waiting_for_image: dict[str, tuple[str, datetime, str]] = {}
        self._session_ttl_seconds = 60  # Expire after 60 seconds
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval_seconds = 604800  # Run cleanup every 7 days (weekly)

    def request_profiling(
        self,
        chat_id: str,
        user_id: str | None = None,
        analysis_mode: str = "standard",
    ) -> None:
        """
        Mark that user is waiting to send an image for profiling.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier
            analysis_mode: Prompt mode to use when the image arrives
        """
        self._waiting_for_image[chat_id] = (
            user_id or "unknown",
            datetime.now(),
            analysis_mode,
        )
        logger.info(f"🔬 Profiling requested for chat {chat_id} (mode={analysis_mode})")

    def get_analysis_mode(self, chat_id: str) -> str:
        """Return the requested analysis mode for the current session."""
        session = self._waiting_for_image.get(chat_id)
        if not session:
            return "standard"
        return session[2]

    def is_waiting_for_image(self, chat_id: str, user_id: str | None = None) -> bool:
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

        stored_user_id, timestamp, _analysis_mode = self._waiting_for_image[chat_id]

        # Check expiration
        age = (datetime.now() - timestamp).total_seconds()
        if age > self._session_ttl_seconds:
            logger.info(f"🔬 Profiling session expired for chat {chat_id}")
            del self._waiting_for_image[chat_id]
            return False

        # Check user match (in groups, ensure same user sent trigger and image)
        if user_id and stored_user_id != "unknown" and user_id != stored_user_id:
            logger.debug(f"🔬 User mismatch: trigger from {stored_user_id}, image from {user_id}")
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
            for chat_id, (_, timestamp, _) in self._waiting_for_image.items()
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

    async def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except TimeoutError:
                logger.warning("⚠️ Profiler cleanup task shutdown timed out")
            except asyncio.CancelledError:
                pass
            logger.info("✅ Profiler session cleanup task stopped")


# Singleton instance
profiler_session_manager = ProfilerSessionManager()
