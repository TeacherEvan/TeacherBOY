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
import hashlib
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

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
        self.image_data: str | None = None  # Base64 encoded image
        self.last_image_data: str | None = None  # Most recently analyzed image
        self.question: str | None = None
        self.detected_dates: list[dict[str, str]] = []  # Dates found in image
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def set_image(self, image_data: str) -> None:
        """Store image data and advance to question state."""
        self.image_data = image_data
        self.last_image_data = image_data
        self.state = AnalyzerState.WAITING_FOR_QUESTION
        self.updated_at = datetime.now(UTC)

    def set_analysis_choice(self) -> None:
        """Mark the session as waiting for a New/Last selection."""
        self.state = AnalyzerState.WAITING_FOR_ANALYSIS_CHOICE
        self.updated_at = datetime.now(UTC)

    def set_question(self, question: str) -> None:
        """Store the user's question."""
        self.question = question
        self.updated_at = datetime.now(UTC)

    def set_detected_dates(self, dates: list[dict[str, str]]) -> None:
        """Store detected dates and set state to waiting for calendar confirmation."""
        self.detected_dates = dates
        self.state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION
        self.updated_at = datetime.now(UTC)

    def is_expired(self, ttl_seconds: int = 60) -> bool:
        """Check if session has expired based on last update."""
        age = (datetime.now(UTC) - self.updated_at).total_seconds()
        return age > ttl_seconds


class ImageAnalyzerSessionManager:
    """Manages multi-step image analysis sessions."""

    def __init__(
        self,
        hf_token: str | None = None,
        hf_repo_id: str | None = None,
    ):
        """Initialize image analyzer session manager.

        Args:
            hf_token: Hugging Face token for HF Hub persistence
            hf_repo_id: Hugging Face repo ID for image persistence (e.g., "EvilEvan/teacherboy-images")
        """
        self._sessions: dict[str, ImageAnalyzerSession] = {}
        self._last_images: dict[str, str] = {}
        self._last_images_timestamps: dict[str, datetime] = {}  # Track when each image was stored
        self._session_ttl_seconds = 60  # Each step has 60 seconds
        self._last_images_ttl_seconds = 3600  # Last images expire after 1 hour
        self._max_last_images = 100  # Maximum number of last images to store
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval_seconds = 30  # Cleanup every 30 seconds
        # Locks for thread-safe access to shared dictionaries
        self._sessions_lock = asyncio.Lock()
        self._last_images_lock = asyncio.Lock()
        # Image persistence fields
        self._images_lock = asyncio.Lock()
        self._images_hf_enabled = bool(hf_token and hf_repo_id)
        self._images_hf_token = hf_token
        self._images_hf_repo_id = hf_repo_id
        self._images_hf_api: Any | None = None
        self._images_commit_scheduler: Any | None = None
        self._images_local_path = Path("./data/images")
        if self._images_hf_enabled:
            self._setup_images_hf_storage()

    async def start_session(
        self,
        chat_id: str,
        user_id: str | None = None,
        analysis_mode: str = "standard",
    ) -> None:
        """
        Start a new image analysis session.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier
            analysis_mode: Prompt mode to use when the image arrives
        """
        async with self._sessions_lock:
            self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
            self._sessions[chat_id].mode = analysis_mode
            logger.info(f"🖼️ Image analysis session started for chat {chat_id} (mode={analysis_mode})")

    async def start_session_with_image(
        self,
        chat_id: str,
        user_id: str | None = None,
        image_data: str | None = None,
        analysis_mode: str = "standard",
    ) -> None:
        """Start a session that already has an image available."""
        async with self._sessions_lock:
            self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
            self._sessions[chat_id].mode = analysis_mode
            if image_data:
                self._sessions[chat_id].image_data = image_data
                self._sessions[chat_id].last_image_data = image_data
                self._sessions[chat_id].state = AnalyzerState.WAITING_FOR_QUESTION
            logger.info(f"🖼️ Image analysis session started for chat {chat_id} with preloaded image (mode={analysis_mode})")

    async def start_analysis_choice(self, chat_id: str, user_id: str | None = None) -> None:
        """Start a session that asks the user whether to analyze a new or last image."""
        async with self._sessions_lock:
            self._sessions[chat_id] = ImageAnalyzerSession(user_id or "unknown")
            self._sessions[chat_id].set_analysis_choice()
            logger.info(f"🖼️ Image analysis choice session started for chat {chat_id}")

    async def get_session(self, chat_id: str) -> ImageAnalyzerSession | None:
        """
        Get session for a chat if it exists and hasn't expired.

        Args:
            chat_id: Chat identifier

        Returns:
            ImageAnalyzerSession or None
        """
        async with self._sessions_lock:
            if chat_id not in self._sessions:
                return None

            session = self._sessions[chat_id]

            # Check expiration
            if session.is_expired(self._session_ttl_seconds):
                logger.info(f"🖼️ Image analysis session expired for chat {chat_id}")
                del self._sessions[chat_id]
                return None

            return session

    async def is_waiting_for_image(self, chat_id: str, user_id: str | None = None) -> bool:
        """
        Check if session is in WAITING_FOR_IMAGE state.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for image
        """
        session = await self.get_session(chat_id)
        if not session:
            return False

        # Check user match (in groups, ensure same user)
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(f"🖼️ User mismatch: session owner {session.user_id}, image from {user_id}")
            return False

        return session.state == AnalyzerState.WAITING_FOR_IMAGE

    async def is_waiting_for_analysis_choice(self, chat_id: str, user_id: str | None = None) -> bool:
        """Check if session is waiting for a New/Last selection."""
        session = await self.get_session(chat_id)
        if not session:
            return False

        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(f"🖼️ User mismatch: session owner {session.user_id}, choice from {user_id}")
            return False

        return session.state == AnalyzerState.WAITING_FOR_ANALYSIS_CHOICE

    async def is_waiting_for_question(self, chat_id: str, user_id: str | None = None) -> bool:
        """
        Check if session is in WAITING_FOR_QUESTION state.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for question
        """
        session = await self.get_session(chat_id)
        if not session:
            return False

        # Check user match
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            logger.debug(f"🖼️ User mismatch: session owner {session.user_id}, question from {user_id}")
            return False

        return session.state == AnalyzerState.WAITING_FOR_QUESTION

    async def store_image(self, chat_id: str, image_data: str) -> bool:
        """
        Store image data and advance to question state.

        Args:
            chat_id: Chat identifier
            image_data: Base64 encoded image

        Returns:
            True if successful
        """
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if not session:
                return False

            # Check expiration manually since we're already holding the lock
            if session.is_expired(self._session_ttl_seconds):
                logger.info(f"🖼️ Image analysis session expired for chat {chat_id}")
                del self._sessions[chat_id]
                return False

            session.set_image(image_data)

        # Update last_images with its own lock
        async with self._last_images_lock:
            self._last_images[chat_id] = image_data
            self._last_images_timestamps[chat_id] = datetime.now(UTC)

            # Enforce size limit on _last_images
            if len(self._last_images) > self._max_last_images:
                await self._purge_oldest_last_images()

        logger.info(f"🖼️ Image stored for chat {chat_id}, waiting for question")
        return True

    async def get_image_and_question(self, chat_id: str, question: str) -> tuple[str | None, str | None, str]:
        """
        Get stored image and set question, then clear session.

        Args:
            chat_id: Chat identifier
            question: User's question about the image

        Returns:
            Tuple of (image_data, question, analysis_mode) or (None, None, "standard") if session invalid
        """
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if not session or not session.image_data:
                return None, None, "standard"

            # Check expiration manually since we're already holding the lock
            if session.is_expired(self._session_ttl_seconds):
                logger.info(f"🖼️ Image analysis session expired for chat {chat_id}")
                del self._sessions[chat_id]
                return None, None, "standard"

            session.set_question(question)
            image_data = session.image_data
            analysis_mode = getattr(session, "mode", "standard")

            # Clear session after retrieving data
            del self._sessions[chat_id]
            logger.info(f"🖼️ Image analysis session completed for chat {chat_id}")

            return image_data, question, analysis_mode

    async def get_last_image(self, chat_id: str) -> str | None:
        """Get the most recently analyzed image for this chat, if available."""
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if not session:
                return None
            return session.last_image_data

    async def clear_session(self, chat_id: str) -> None:
        """
        Clear session for a chat.

        Args:
            chat_id: Chat identifier
        """
        async with self._sessions_lock:
            if chat_id in self._sessions:
                del self._sessions[chat_id]
                logger.info(f"🖼️ Cleared image analysis session for chat {chat_id}")

    async def store_detected_dates(self, chat_id: str, dates: list[dict[str, str]]) -> bool:
        """
        Store detected dates from image analysis.

        Only stores dates in an existing valid session. Does NOT create new sessions
        to prevent session fixation attacks.

        Args:
            chat_id: Chat identifier
            dates: List of date dicts with 'date', 'title', 'description'

        Returns:
            True if stored successfully, False if no valid session exists
        """
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if not session:
                logger.warning(f"🖼️ Attempted to store dates for non-existent session: {chat_id}")
                return False

            # Check expiration manually since we're already holding the lock
            if session.is_expired(self._session_ttl_seconds):
                logger.info(f"🖼️ Image analysis session expired for chat {chat_id}")
                del self._sessions[chat_id]
                return False

            session.set_detected_dates(dates)
            logger.info(f"📅 Stored {len(dates)} detected dates for chat {chat_id}")
            return True

    async def get_detected_dates(self, chat_id: str) -> list[dict[str, str]]:
        """
        Get stored detected dates for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            List of date dicts, or empty list if none
        """
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if not session:
                return []
            return session.detected_dates

    async def is_waiting_for_calendar_confirmation(self, chat_id: str, user_id: str | None = None) -> bool:
        """
        Check if session is waiting for calendar confirmation.

        Args:
            chat_id: Chat identifier
            user_id: Optional user identifier (must match)

        Returns:
            True if waiting for calendar confirmation
        """
        session = await self.get_session(chat_id)
        if not session:
            return False

        # Check user match
        if user_id and session.user_id != "unknown" and user_id != session.user_id:
            return False

        return session.state == AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

    async def cleanup_expired(self) -> None:
        """Remove expired sessions and expired last images."""
        now = datetime.now(UTC)

        # Clean up expired sessions
        async with self._sessions_lock:
            expired_sessions = [
                chat_id for chat_id, session in self._sessions.items() if session.is_expired(self._session_ttl_seconds)
            ]

            for chat_id in expired_sessions:
                del self._sessions[chat_id]

        # Clean up expired last images (TTL-based)
        async with self._last_images_lock:
            expired_last_images = [
                chat_id
                for chat_id, timestamp in self._last_images_timestamps.items()
                if (now - timestamp).total_seconds() > self._last_images_ttl_seconds
            ]

            for chat_id in expired_last_images:
                self._last_images.pop(chat_id, None)
                self._last_images_timestamps.pop(chat_id, None)

        total_cleaned = len(expired_sessions) + len(expired_last_images)
        if total_cleaned:
            logger.info(
                f"🖼️ Cleaned up {len(expired_sessions)} expired sessions and {len(expired_last_images)} expired last images"
            )

    async def _purge_oldest_last_images(self) -> None:
        """Remove oldest last images when size limit is exceeded."""
        async with self._last_images_lock:
            if not self._last_images_timestamps:
                return

            # Sort by timestamp and remove oldest entries to get back under limit
            sorted_chats = sorted(self._last_images_timestamps.items(), key=lambda x: x[1])
            to_remove = len(self._last_images) - self._max_last_images  # Remove exactly what's needed

            for chat_id, _ in sorted_chats[:to_remove]:
                self._last_images.pop(chat_id, None)
                self._last_images_timestamps.pop(chat_id, None)

            if to_remove > 0:
                logger.info(f"🖼️ Purged {to_remove} oldest last images due to size limit")

    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired sessions."""
        logger.info(f"🖼️ Starting image analyzer session cleanup loop (every {self._cleanup_interval_seconds}s)")
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self.cleanup_expired()
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

    def _setup_images_hf_storage(self):
        """Initialize HF Hub storage for images."""
        if not self._images_hf_token or not self._images_hf_repo_id:
            self._images_hf_enabled = False
            return
        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            HfApi = hf.HfApi
            CommitScheduler = hf.CommitScheduler
            hf_api = HfApi(token=self._images_hf_token)
            self._images_hf_api = hf_api
            self._images_local_path.mkdir(parents=True, exist_ok=True)
            hf_api.create_repo(
                repo_id=self._images_hf_repo_id,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
            self._images_commit_scheduler = CommitScheduler(
                repo_id=self._images_hf_repo_id,
                repo_type="dataset",
                folder_path=str(self._images_local_path),
                every=5,  # 5 minutes
                token=self._images_hf_token,
                private=True,
                squash_history=True,
            )
            logger.info(f"🖼️ Image analysis HF storage ready: {self._images_hf_repo_id}")
        except Exception as e:
            logger.warning(f"⚠️ Image HF storage init failed: {e}")
            self._images_hf_enabled = False

    def _hash_chat_id(self, chat_id: str) -> str:
        return hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]

    async def save_image_metadata(
        self,
        chat_id: str,
        image_base64: str,
        prompt: str,
        response: str,
        analysis_mode: str,
        duration_ms: int,
        image_size_bytes: int,
        model_used: str,
    ) -> str:
        """Save image analysis result to local storage for HF sync."""
        image_id = hashlib.sha256((chat_id + prompt + str(datetime.now(UTC))).encode()).hexdigest()[:32]
        hashed_chat = self._hash_chat_id(chat_id)
        chat_dir = self._images_local_path / hashed_chat
        chat_dir.mkdir(parents=True, exist_ok=True)
        file_path = chat_dir / f"{image_id}.json"

        metadata = {
            "id": image_id,
            "chat_id": chat_id,
            "hashed_chat_id": hashed_chat,
            "timestamp": datetime.now(UTC).isoformat(),
            "image_base64": image_base64,
            "prompt": prompt,
            "response": response,
            "analysis_mode": analysis_mode,
            "duration_ms": duration_ms,
            "image_size_bytes": image_size_bytes,
            "model_used": model_used,
        }

        async with self._images_lock:
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            temp_path.rename(file_path)

        logger.info(f"🖼️ Saved image metadata for {hashed_chat[:8]}... ({image_id[:8]})")
        return image_id


# Singleton instance
image_analyzer_session_manager = ImageAnalyzerSessionManager()
