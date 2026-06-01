"""Image Analyzer session manager - tracks multi-step image Q&A sessions.

Flow:
1. User: "Zeus analyze this" / "analyze image"
2. Zeus: "Provide me with thy image to examine (60 seconds)"
3. User: [sends image]
4. Zeus: "What is thy question about this image?"
5. User: "What would be most enjoyable on this menu to a westerner?"
6. Zeus: [analyzes image and answers question]

Calendar Integration:
When dates are detected in images, the session manager stores them
for potential calendar integration.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AnalyzerState(Enum):
    """States for the image analyzer session."""

    WAITING_FOR_IMAGE = "waiting_for_image"
    WAITING_FOR_ANALYSIS_CHOICE = "waiting_for_analysis_choice"
    WAITING_FOR_QUESTION = "waiting_for_question"
    WAITING_FOR_CALENDAR_CONFIRMATION = "waiting_for_calendar_confirmation"


class ImageAnalyzerSession:
    """Session data for image analysis."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state = AnalyzerState.WAITING_FOR_IMAGE
        self.mode = "standard"
        self.image_data: Optional[str] = None  # Base64 encoded image
        self.last_image_data: Optional[str] = None  # Most recently analyzed image
        self.question: Optional[str] = None
        self.detected_dates: List[Dict[str, str]] = []  # Dates found in image
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def set_image(self, image_data: str) -> None:
        """Store image data and advance to question state."""
        self.image_data = image_data
        self.last_image_data = image_data
        self.state = AnalyzerState.WAITING_FOR_QUESTION
        self.updated_at = datetime.now()

    def set_analysis_choice(self) -> None:
        """Mark the session as waiting for a New/Last selection."""
        self.state = AnalyzerState.WAITING_FOR_ANALYSIS_CHOICE
        self.updated_at = datetime.now()

    def set_question(self, question: str) -> None:
        """Store the user's question."""
        self.question = question
        self.updated_at = datetime.now()

    def set_detected_dates(self, dates: List[Dict[str, str]]) -> None:
        """Store detected dates and set state to waiting for calendar confirmation."""
        self.detected_dates = dates
        self.state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION
        self.updated_at = datetime.now()

    def is_expired(self, ttl_seconds: int = 60) -> bool:
        """Check if session has expired based on last update."""
        age = (datetime.now() - self.updated_at).total_seconds()
        return age > ttl_seconds


class ImageAnalyzerSessionManager:
    """Manages multi-step image analysis sessions."""

    def __init__(self):
        """Initialize image analyzer session manager."""
        self._sessions: Dict[str, ImageAnalyzerSession] = {}
        self._last_images: Dict[str, str] = {}
        self._session_ttl_seconds = 60  # Each step has 60 seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval_seconds = 30  # Cleanup every 30 seconds

    def start_session(
        self,
        chat_id: str,
        user_id: Optional[str] = None,
        analysis_mode: str = "standard",
    ) -> None:
        """
        Start a new image analysis session.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier
            analysis_mode: Prompt mode to use when the image arrives
        """
        self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
        self._sessions[chat_id].mode = analysis_mode
        logger.info(
            f"🖼️ Image analysis session started for chat {chat_id} (mode={analysis_mode})"
        )

    def start_session_with_image(
        self,
        chat_id: str,
        user_id: Optional[str] = None,
        image_data: Optional[str] = None,
        analysis_mode: str = "standard",
    ) -> None:
        """Start a session that already has an image available."""
        self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
        self._sessions[chat_id].mode = analysis_mode
        if image_data:
            self._sessions[chat_id].image_data = image_data
            self._sessions[chat_id].last_image_data = image_data
            self._sessions[chat_id].state = AnalyzerState.WAITING_FOR_QUESTION
        logger.info(
            f"🖼️ Image analysis session started for chat {chat_id} with preloaded image (mode={analysis_mode})"
        )

    def start_analysis_choice(
        self, chat_id: str, user_id: Optional[str] = None
    ) -> None:
        """Start a session that asks the user whether to analyze a new or last image."""
        self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
        self._sessions[chat_id].set_analysis_choice()
        logger.info(f"🖼️ Image analysis choice session started for chat {chat_id}")

    def get_session(self, chat_id: str) -> Optional[ImageAnalyzerSession]:
        """
        Get session for a chat if it exists and hasn't expired.

        Args:
            chat_id: Chat identifier

        Returns:
            ImageAnalyzerSession or None
        """
        if chat_id not in self._sessions:
            return None

        session = self._sessions[chat_id]

        # Check expiration
        if session.is_expired(self._session_ttl_seconds):
            logger.info(f"🖼️ Image analysis session expired for chat {chat_id}")
            del self._sessions[chat_id]
            return None

        return session

    def is_waiting_for_image(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        """
        Check if session is in WAITING_FOR_IMAGE state.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for image
        """
        session = self.get_session(chat_id)
        if not session:
            return False

        # Check user match (in groups, ensure same user)
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(
                f"🖼️ User mismatch: session owner {session.user_id}, image from {user_id}"
            )
            return False

        return session.state == AnalyzerState.WAITING_FOR_IMAGE

    def is_waiting_for_analysis_choice(
        self, chat_id: str, user_id: Optional[str] = None
    ) -> bool:
        """Check if session is waiting for a New/Last selection."""
        session = self.get_session(chat_id)
        if not session:
            return False

        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(
                f"🖼️ User mismatch: session owner {session.user_id}, choice from {user_id}"
            )
            return False

        return session.state == AnalyzerState.WAITING_FOR_ANALYSIS_CHOICE

    def is_waiting_for_question(
        self, chat_id: str, user_id: Optional[str] = None
    ) -> bool:
        """
        Check if session is in WAITING_FOR_QUESTION state.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for question
        """
        session = self.get_session(chat_id)
        if not session:
            return False

        # Check user match
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(
                f"🖼️ User mismatch: session owner {session.user_id}, question from {user_id}"
            )
            return False

        return session.state == AnalyzerState.WAITING_FOR_QUESTION

    def store_image(self, chat_id: str, image_data: str) -> bool:
        """
        Store image data and advance to question state.

        Args:
            chat_id: Chat identifier
            image_data: Base64 encoded image

        Returns:
            True if successful
        """
        session = self.get_session(chat_id)
        if not session:
            return False

        session.set_image(image_data)
        self._last_images[chat_id] = image_data
        logger.info(f"🖼️ Image stored for chat {chat_id}, waiting for question")
        return True

    def get_image_and_question(
        self, chat_id: str, question: str
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Get stored image and set question, then clear session.

        Args:
            chat_id: Chat identifier
            question: User's question about the image

        Returns:
            Tuple of (image_data, question, analysis_mode) or (None, None, "standard") if session invalid
        """
        session = self.get_session(chat_id)
        if not session or not session.image_data:
            return None, None, "standard"

        session.set_question(question)
        image_data = session.image_data
        analysis_mode = getattr(session, "mode", "standard")

        # Clear session after retrieving data
        del self._sessions[chat_id]
        logger.info(f"🖼️ Image analysis session completed for chat {chat_id}")

        return image_data, question, analysis_mode

    def get_last_image(self, chat_id: str) -> Optional[str]:
        """Get the most recently analyzed image for this chat, if available."""
        session = self._sessions.get(chat_id)
        if not session:
            return None
        return session.last_image_data

    def clear_session(self, chat_id: str) -> None:
        """
        Clear session for a chat.

        Args:
            chat_id: Chat identifier
        """
        if chat_id in self._sessions:
            del self._sessions[chat_id]
            logger.info(f"🖼️ Cleared image analysis session for chat {chat_id}")

    def store_detected_dates(self, chat_id: str, dates: List[Dict[str, str]]) -> bool:
        """
        Store detected dates from image analysis.

        Creates a new minimal session if one doesn't exist (for calendar integration).

        Args:
            chat_id: Chat identifier
            dates: List of date dicts with 'date', 'title', 'description'

        Returns:
            True if stored successfully
        """
        # Get existing session or create a temporary one for dates
        session = self._sessions.get(chat_id)
        if not session:
            # Create a temporary session just for date storage
            session = ImageAnalyzerSession("unknown")
            self._sessions[chat_id] = session

        session.set_detected_dates(dates)
        logger.info(f"📅 Stored {len(dates)} detected dates for chat {chat_id}")
        return True

    def get_detected_dates(self, chat_id: str) -> List[Dict[str, str]]:
        """
        Get stored detected dates for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            List of date dicts, or empty list if none
        """
        session = self._sessions.get(chat_id)
        if not session:
            return []
        return session.detected_dates

    def is_waiting_for_calendar_confirmation(
        self, chat_id: str, user_id: Optional[str] = None
    ) -> bool:
        """
        Check if session is waiting for calendar confirmation.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for calendar confirmation
        """
        session = self.get_session(chat_id)
        if not session:
            return False

        # Check user match
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            return False

        return session.state == AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

    def cleanup_expired(self) -> None:
        """Remove expired sessions."""
        expired = [
            chat_id
            for chat_id, session in self._sessions.items()
            if session.is_expired(self._session_ttl_seconds)
        ]

        for chat_id in expired:
            del self._sessions[chat_id]

        if expired:
            logger.info(f"🖼️ Cleaned up {len(expired)} expired image analysis sessions")

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired sessions."""
        logger.info(
            f"🖼️ Starting image analyzer session cleanup loop (every {self._cleanup_interval_seconds}s)"
        )
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                self.cleanup_expired()
        except asyncio.CancelledError:
            logger.info("🖼️ Image analyzer session cleanup loop cancelled")
            raise

    def start_cleanup(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ Image analyzer session cleanup task started")
        else:
            logger.warning("⚠️  Image analyzer cleanup task already running")

    def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("✅ Image analyzer session cleanup task stopped")


# Singleton instance
image_analyzer_session_manager = ImageAnalyzerSessionManager()
